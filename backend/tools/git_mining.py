"""Git mining tools using git log subprocess.

Analyzes git history to find code hotspots and risky files.
Combines complexity analysis with change frequency to identify high-risk areas.
"""

import logging
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from constants import CHURN_MULTIPLIERS, DEBT_TYPE_TO_ROLE, SKIP_DIRS
from tools.scoring import (
    build_finding_payload,
    calculate_confidence,
    classify_business_impact,
    max_severity,
)

logger = logging.getLogger(__name__)


class GitMiner:
    """Analyzes git history to find code hotspots and risky files."""

    def __init__(self) -> None:
        self._hotspots_cache: dict[str, list[dict[str, Any]]] = {}

    def _should_skip_file(self, file_path: str) -> bool:
        """Check if file should be skipped based on skip dirs."""
        path_parts = Path(file_path).parts
        return any(skip_dir in path_parts for skip_dir in SKIP_DIRS)

    def _normalize_repo_path(self, file_path: str) -> str:
        """Normalize repository paths for matching across tools."""
        return str(Path(file_path).as_posix()).lstrip("./")

    def get_hotspots(
        self, repo_path: str, max_commits: int = 50
    ) -> list[dict[str, Any]]:
        """Find files with the most commits (code hotspots).

        Uses git log --name-only to get file lists per commit without loading
        diffs or fetching blobs — safe for blobless/partial clones of large repos.

        Args:
            repo_path: Path to the git repository
            max_commits: Maximum number of commits to analyze

        Returns:
            List of hotspot files sorted by change count (descending)
        """
        cache_key = f"{repo_path}:{max_commits}"
        if cache_key in self._hotspots_cache:
            logger.info("Using cached hotspots data")
            return self._hotspots_cache[cache_key]

        file_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"change_count": 0, "authors": set(), "last_changed": None}
        )

        try:
            delimiter = "\x1f"
            cmd = [
                "git", "-C", repo_path,
                "log", "--no-merges", f"-n{max_commits}",
                f"--format={delimiter}%ae%x00%aI",
                "--name-only",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                logger.warning("git log failed for %s: %s", repo_path, result.stderr.strip())
                return []

            for block in result.stdout.split(delimiter):
                block = block.strip()
                if not block:
                    continue
                lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
                if not lines:
                    continue
                header = lines[0].split("\x00")
                if len(header) < 2:
                    continue
                author_email = header[0].strip().lower()
                author_date = header[1].strip()

                for file_path in lines[1:]:
                    if self._should_skip_file(file_path):
                        continue
                    normalized = self._normalize_repo_path(file_path)
                    file_stats[normalized]["change_count"] += 1
                    file_stats[normalized]["authors"].add(author_email)
                    if file_stats[normalized]["last_changed"] is None:
                        file_stats[normalized]["last_changed"] = author_date

        except subprocess.TimeoutExpired:
            logger.warning("git log timed out for %s", repo_path)
            return []
        except Exception as e:
            logger.warning("Error mining git history: %s", e, exc_info=True)
            return []

        hotspots = [
            {
                "file": file_path,
                "change_count": stats["change_count"],
                "unique_authors": len(stats["authors"]),
                "last_changed": stats["last_changed"],
            }
            for file_path, stats in file_stats.items()
        ]
        hotspots.sort(key=lambda x: x["change_count"], reverse=True)
        self._hotspots_cache[cache_key] = hotspots

        logger.info("Found %d hotspot files", len(hotspots))
        return hotspots

    def get_churn_multiplier(self, change_count: int) -> float:
        """Get maintenance cost multiplier based on change frequency.
        
        Based on Zazworka et al. "Prioritizing Technical Debt in Large-Scale
        Enterprise Systems" - empirically measured maintenance cost multipliers.
        
        Args:
            change_count: Number of commits to a file
            
        Returns:
            Cost multiplier (1.0 to 3.0)
        """
        for threshold, multiplier in sorted(
            CHURN_MULTIPLIERS, key=lambda x: x[0], reverse=True
        ):
            if change_count >= threshold:
                return multiplier
        return 1.0

    def _get_fallback_hotspots(self, repo_path: str) -> list[dict[str, Any]]:
        """Generate hotspots based on file complexity when git history is unavailable.
        
        Uses complexity analysis to identify high-risk files as a fallback
        when git mining fails (e.g., shallow clone or corrupted history).
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            List of hotspot files based on complexity metrics
        """
        from tools.static_analysis import StaticAnalyzer
        
        static_analyzer = StaticAnalyzer()
        summary = static_analyzer.get_summary(repo_path)
        all_functions = summary.get("all_functions", [])
        
        file_complexity: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total_complexity": 0, "function_count": 0, "max_complexity": 0}
        )
        
        for func in all_functions:
            file_path = self._normalize_repo_path(func["file"])
            complexity = func["complexity"]
            file_complexity[file_path]["total_complexity"] += complexity
            file_complexity[file_path]["function_count"] += 1
            file_complexity[file_path]["max_complexity"] = max(
                file_complexity[file_path]["max_complexity"], complexity
            )
        
        hotspots = []
        for file_path, stats in file_complexity.items():
            hotspots.append({
                "file": file_path,
                "change_count": stats["function_count"] * 2,
                "unique_authors": 1,
                "last_changed": None,
                "fallback": True,
                "complexity_score": stats["total_complexity"],
            })
        
        hotspots.sort(key=lambda x: x["change_count"], reverse=True)
        logger.info(f"[FALLBACK] Generated {len(hotspots)} hotspots based on complexity")
        return hotspots

    def get_risky_files(self, repo_path: str) -> list[dict[str, Any]]:
        """Find risky files by combining complexity and churn data.
        
        Cross-references high complexity files with frequently changed files
        to identify files that are both hard to understand and expensive to maintain.
        
        When git history is unavailable (shallow clone), uses complexity-based
        fallback heuristics.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            List of risky files with cost estimates, sorted by cost (descending)
        """
        from data.rate_fetcher import RateFetcher
        from data.sonarqube_rules import SonarQubeRules
        from tools.static_analysis import StaticAnalyzer

        static_analyzer = StaticAnalyzer()
        summary = static_analyzer.get_summary(repo_path)
        hotspots = self.get_hotspots(repo_path)
        used_fallback = False
        
        if not hotspots:
            logger.warning("[CODE QUALITY] No hotspots from git mining - using complexity fallback")
            hotspots = self._get_fallback_hotspots(repo_path)
            used_fallback = True
        
        all_functions = summary.get("all_functions", [])
        logger.info(f"[CODE QUALITY DEBUG] Files from complexity scan: {len(set(f['file'] for f in all_functions))}")
        logger.info(f"[CODE QUALITY DEBUG] Hotspot files: {len(hotspots)} (fallback={used_fallback})")

        hotspots_by_path: dict[str, dict[str, Any]] = {}
        for h in hotspots:
            normalized_path = self._normalize_repo_path(h["file"])
            hotspots_by_path[normalized_path] = h

        logger.info(f"[CODE QUALITY DEBUG] Unique paths in hotspots: {len(hotspots_by_path)}")

        file_to_functions: dict[str, list[dict]] = defaultdict(list)
        for func in all_functions:
            normalized_path = self._normalize_repo_path(func["file"])
            file_to_functions[normalized_path].append(func)

        risky_files = []
        matched_count = 0
        
        for file_path, functions in file_to_functions.items():
            if file_path not in hotspots_by_path:
                continue

            matched_count += 1
            hotspot = hotspots_by_path[file_path]
            change_count = hotspot["change_count"]

            max_complexity = max(f["complexity"] for f in functions)
            severity = max_severity(
                [
                    f["severity"]
                    for f in functions
                    if f["severity"] in ("critical", "high", "medium", "low")
                ]
            )

            churn_multiplier = self.get_churn_multiplier(change_count)

            sonar_rules = SonarQubeRules()
            base_minutes = sonar_rules.get_minutes_for_complexity(severity)
            adjusted_minutes = base_minutes * churn_multiplier

            role = DEBT_TYPE_TO_ROLE["code_quality"]
            rate_fetcher = RateFetcher()
            hourly_rate = rate_fetcher.get_rate(role)
            remediation_hours = adjusted_minutes / 60
            confidence = calculate_confidence(
                used_fallback=used_fallback,
                has_git_history=not used_fallback,
                category="git_history",
            )
            business_impact = classify_business_impact(
                severity=severity,
                churn_multiplier=churn_multiplier,
                change_count=change_count,
            )

            risky_file = build_finding_payload(
                file_path=file_path,
                category="code_quality",
                severity=severity,
                remediation_hours=remediation_hours,
                hourly_rate=hourly_rate,
                confidence=confidence,
                business_impact=business_impact,
                extra={
                    "basename": os.path.basename(file_path),
                    "max_complexity": max_complexity,
                    "change_count": change_count,
                    "churn_multiplier": churn_multiplier,
                    "base_minutes": round(base_minutes, 2),
                    "adjusted_minutes": round(adjusted_minutes, 2),
                    "hourly_rate": hourly_rate,
                    "hourly_rate_source": rate_fetcher.get_all_rates().get("source", "unknown"),
                    "risk_level": business_impact,
                    "used_fallback": used_fallback,
                    "functions": [
                        {"name": f["function"], "complexity": f["complexity"]}
                        for f in functions
                    ],
                    "type": "complexity_hotspot",
                },
            )
            risky_files.append(risky_file)

        risky_files.sort(key=lambda x: x["cost_usd"], reverse=True)
        logger.info(f"[CODE QUALITY DEBUG] Files matched: {matched_count}")
        logger.info(f"[CODE QUALITY] Identified {len(risky_files)} risky files with total cost ${sum(r['cost_usd'] for r in risky_files):.2f}")
        return risky_files
