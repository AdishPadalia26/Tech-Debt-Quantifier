"""Ownership analytics derived from local git history."""

from __future__ import annotations

import logging
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from constants import SKIP_DIRS

logger = logging.getLogger(__name__)

# Extensions considered source code for ownership purposes.
# Files outside this set (docs, assets, config, lock files) are excluded so
# changelog and CI churn don't dominate bus-factor / hotspot calculations.
_SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".cpp", ".c", ".cc", ".cxx", ".h", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".lua",
    ".ex", ".exs", ".clj", ".cljs",
    ".vue", ".svelte",
    ".sh", ".bash",
    ".ipynb",
    ".sql",
})


class OwnershipAnalyzer:
    """Analyze contributor concentration and ownership risk from git history."""

    def _ensure_history_depth(self, repo_path: str, target_depth: int = 500) -> None:
        """Deepen a shallow clone so ownership analysis has enough commit history."""
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "rev-list", "--count", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            current_depth = int(result.stdout.strip()) if result.returncode == 0 else 0
            if current_depth >= target_depth:
                return
            shallow_file = Path(repo_path) / ".git" / "shallow"
            if not shallow_file.exists():
                return
            deepen_by = max(target_depth - current_depth, 100)
            subprocess.run(
                ["git", "-C", repo_path, "fetch", f"--deepen={deepen_by}"],
                capture_output=True, text=True, timeout=120,
            )
        except Exception as exc:
            logger.debug("Could not deepen repo history for %s: %s", repo_path, exc)

    def _git_unique_emails(self, repo_path: str, since_days: int | None = None) -> set[str]:
        """Return unique author emails via git shortlog (fast, full-history scan)."""
        try:
            cmd = ["git", "-C", repo_path, "shortlog", "-sne", "--no-merges"]
            if since_days is not None:
                cmd.append(f"--since={since_days} days ago")
            cmd.append("HEAD")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                return set()
            emails: set[str] = set()
            for line in result.stdout.splitlines():
                if "<" in line and ">" in line:
                    email = line[line.rfind("<") + 1 : line.rfind(">")].strip().lower()
                    if email:
                        emails.add(email)
            return emails
        except Exception as exc:
            logger.debug("git shortlog failed for %s: %s", repo_path, exc)
            return set()

    def _iter_git_history(
        self, repo_path: str, max_commits: int
    ) -> tuple[
        dict[str, Counter[str]],
        dict[str, Counter[str]],
        Counter[str],
        dict[str, str | None],
        dict[str, str],
        int,
    ]:
        """Return ownership counters using fast git-log output."""
        delimiter = "\x1f"
        cmd = [
            "git",
            "-C",
            repo_path,
            "log",
            "--no-merges",
            f"-n{max_commits}",
            f"--format={delimiter}%ae%x00%an%x00%aI",
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
            raise RuntimeError(result.stderr.strip() or "git log failed")

        file_counts: dict[str, Counter[str]] = defaultdict(Counter)
        module_counts: dict[str, Counter[str]] = defaultdict(Counter)
        repo_counts: Counter[str] = Counter()
        file_last_changed: dict[str, str | None] = {}
        author_names: dict[str, str] = {}
        commits_seen = 0

        for block in result.stdout.split(delimiter):
            block = block.strip()
            if not block:
                continue

            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            header = lines[0].split("\x00")
            if len(header) < 3:
                continue

            author_email = header[0].strip().lower()
            author_name = header[1].strip()
            author_date = header[2].strip()
            if not author_email:
                continue

            commits_seen += 1
            if author_name and author_email not in author_names:
                author_names[author_email] = author_name
            repo_counts[author_email] += 1

            touched_files: set[str] = set()
            for file_path in lines[1:]:
                if self._should_skip_file(file_path):
                    continue
                normalized = self._normalize_repo_path(file_path)
                touched_files.add(normalized)
                file_counts[normalized][author_email] += 1
                file_last_changed[normalized] = author_date

            for normalized in touched_files:
                module_counts[self._module_name(normalized)][author_email] += 1

        return (
            file_counts,
            module_counts,
            repo_counts,
            file_last_changed,
            author_names,
            commits_seen,
        )

    def _normalize_repo_path(self, file_path: str) -> str:
        """Normalize repository file paths across platforms."""
        return str(Path(file_path).as_posix()).lstrip("/")

    def _module_name(self, file_path: str) -> str:
        """Return the module bucket for a normalized file path."""
        parent = str(Path(file_path).parent).replace("\\", "/")
        return "." if parent in ("", ".") else parent

    def _should_skip_file(self, file_path: str) -> bool:
        """Return whether a file path should be excluded from ownership analysis."""
        path = Path(file_path)
        if any(part in SKIP_DIRS for part in path.parts):
            return True
        # Only track source-code files; docs, assets, configs, and lock files
        # have unrelated churn (e.g. CHANGES.rst) that distorts bus-factor.
        return path.suffix.lower() not in _SOURCE_EXTENSIONS

    def _counter_share(self, counts: Counter[str]) -> float:
        """Return the top-contributor share for a counter."""
        total = sum(counts.values())
        if total <= 0:
            return 0.0
        return round(max(counts.values()) / total, 2)

    def _bus_factor(self, counts: Counter[str], threshold: float = 0.8) -> int:
        """Return the minimum number of contributors covering a share threshold."""
        total = sum(counts.values())
        if total <= 0:
            return 0

        cumulative = 0
        contributors = 0
        for _, count in counts.most_common():
            cumulative += count
            contributors += 1
            if cumulative / total >= threshold:
                return contributors
        return contributors

    def _ownership_risk(
        self,
        *,
        owner_count: int,
        top_contributor_share: float,
        total_changes: int,
    ) -> str:
        """Classify ownership risk using concentration and contributor spread."""
        if total_changes <= 1:
            return "low"
        if owner_count <= 1 and total_changes >= 3:
            return "critical"
        if top_contributor_share >= 0.85:
            return "critical"
        if owner_count <= 2 or top_contributor_share >= 0.7:
            return "high"
        if owner_count <= 3 or top_contributor_share >= 0.55:
            return "medium"
        return "low"

    def analyze(
        self,
        repo_path: str,
        hotspot_files: list[str] | None = None,
        *,
        max_commits: int | None = None,
    ) -> dict[str, Any]:
        """Analyze repository ownership at repo, module, and file level."""
        if max_commits is None:
            max_commits = int(os.getenv("OWNERSHIP_MAX_COMMITS", "300"))

        hotspot_set = {
            self._normalize_repo_path(path)
            for path in (hotspot_files or [])
            if path
        }

        # Deepen shallow clones before counting contributors.
        self._ensure_history_depth(repo_path)

        # Accurate all-history contributor counts via git shortlog (fast, full-graph).
        all_time_emails = self._git_unique_emails(repo_path)
        active_90d_emails = self._git_unique_emails(repo_path, since_days=90)

        try:
            (
                file_counts,
                module_counts,
                repo_counts,
                file_last_changed,
                author_names,
                commits_seen,
            ) = self._iter_git_history(repo_path, max_commits)
        except Exception as exc:
            logger.warning("Ownership analysis failed for %s: %s", repo_path, exc, exc_info=True)
            return {
                "summary": {
                    "commit_sample_size": 0,
                    "unique_contributors": len(all_time_emails),
                    "active_contributors_90d": len(active_90d_emails),
                    "bus_factor": 0,
                    "top_contributor_share": 0.0,
                    "siloed_hotspots": 0,
                    "handoff_hotspots": 0,
                },
                "files": {},
                "modules": {},
                "hotspots": [],
            }

        files: dict[str, dict[str, Any]] = {}
        hotspot_profiles: list[dict[str, Any]] = []
        siloed_hotspots = 0
        handoff_hotspots = 0

        for file_path, counts in file_counts.items():
            owner_count = len(counts)
            total_changes = sum(counts.values())
            top_share = self._counter_share(counts)
            ownership_risk = self._ownership_risk(
                owner_count=owner_count,
                top_contributor_share=top_share,
                total_changes=total_changes,
            )
            top_email = counts.most_common(1)[0][0] if counts else None
            top_author = author_names.get(top_email or "", top_email or "unknown")
            ownership_confidence = (
                "high" if total_changes >= 5
                else "medium" if total_changes >= 2
                else "low"
            )
            profile = {
                "file_path": file_path,
                "owner_count": owner_count,
                "top_author": top_author,
                "top_contributor_share": top_share,
                "bus_factor": self._bus_factor(counts),
                "ownership_risk": ownership_risk,
                "ownership_confidence": ownership_confidence,
                "total_changes": total_changes,
                "last_changed": file_last_changed.get(file_path),
            }
            files[file_path] = profile

            if file_path in hotspot_set:
                hotspot_profiles.append(profile)
                if owner_count <= 1 or top_share >= 0.8:
                    siloed_hotspots += 1
                if owner_count >= 4:
                    handoff_hotspots += 1

        modules: dict[str, dict[str, Any]] = {}
        for module_name, counts in module_counts.items():
            owner_count = len(counts)
            total_changes = sum(counts.values())
            top_share = self._counter_share(counts)
            modules[module_name] = {
                "module": module_name,
                "owner_count": owner_count,
                "top_contributor_share": top_share,
                "bus_factor": self._bus_factor(counts),
                "ownership_risk": self._ownership_risk(
                    owner_count=owner_count,
                    top_contributor_share=top_share,
                    total_changes=total_changes,
                ),
                "total_changes": total_changes,
            }

        return {
            "summary": {
                "commit_sample_size": commits_seen,
                # Contributors seen in the sampled commits (same window as bus_factor).
                "unique_contributors": len(repo_counts) or len(all_time_emails),
                # All-time unique contributors across full available history.
                "unique_contributors_all_time": len(all_time_emails),
                "active_contributors_90d": len(active_90d_emails),
                "bus_factor": self._bus_factor(repo_counts),
                "top_contributor_share": self._counter_share(repo_counts),
                "siloed_hotspots": siloed_hotspots,
                "handoff_hotspots": handoff_hotspots,
            },
            "files": files,
            "modules": modules,
            "hotspots": sorted(
                hotspot_profiles,
                key=lambda item: (
                    item["ownership_risk"] == "critical",
                    item["ownership_risk"] == "high",
                    item["top_contributor_share"],
                    item["total_changes"],
                ),
                reverse=True,
            ),
        }
