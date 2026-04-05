"""Ownership analytics derived from local git history."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydriller import Repository

from constants import SKIP_DIRS

logger = logging.getLogger(__name__)


class OwnershipAnalyzer:
    """Analyze contributor concentration and ownership risk from git history."""

    def _normalize_repo_path(self, file_path: str) -> str:
        """Normalize repository file paths across platforms."""
        return str(Path(file_path).as_posix()).lstrip("./")

    def _module_name(self, file_path: str) -> str:
        """Return the module bucket for a normalized file path."""
        parent = str(Path(file_path).parent).replace("\\", "/")
        return "." if parent in ("", ".") else parent

    def _should_skip_file(self, file_path: str) -> bool:
        """Return whether a file path should be excluded from ownership analysis."""
        path_parts = Path(file_path).parts
        return any(skip_dir in path_parts for skip_dir in SKIP_DIRS)

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
        max_commits: int = 250,
    ) -> dict[str, Any]:
        """Analyze repository ownership at repo, module, and file level."""
        hotspot_set = {
            self._normalize_repo_path(path)
            for path in (hotspot_files or [])
            if path
        }

        file_counts: dict[str, Counter[str]] = defaultdict(Counter)
        module_counts: dict[str, Counter[str]] = defaultdict(Counter)
        repo_counts: Counter[str] = Counter()
        file_last_changed: dict[str, str | None] = {}
        active_contributors: set[str] = set()
        commits_seen = 0
        cutoff = datetime.now() - timedelta(days=90)

        try:
            repo = Repository(repo_path, num_workers=1)
            for commit in repo.traverse_commits():
                if commits_seen >= max_commits:
                    break

                author_email = (commit.author.email or "").strip().lower()
                if not author_email:
                    commits_seen += 1
                    continue

                repo_counts[author_email] += 1
                commit_date = commit.author_date.replace(tzinfo=None)
                if commit_date > cutoff:
                    active_contributors.add(author_email)

                touched_files: set[str] = set()
                for modified_file in commit.modified_files:
                    file_path = (
                        modified_file.new_path
                        or modified_file.old_path
                        or modified_file.filename
                    )
                    if not file_path or self._should_skip_file(file_path):
                        continue

                    normalized = self._normalize_repo_path(file_path)
                    touched_files.add(normalized)
                    file_counts[normalized][author_email] += 1
                    file_last_changed[normalized] = commit.author_date.isoformat()

                for normalized in touched_files:
                    module_counts[self._module_name(normalized)][author_email] += 1

                commits_seen += 1
        except Exception as exc:
            logger.warning("Ownership analysis failed for %s: %s", repo_path, exc)
            return {
                "summary": {
                    "commit_sample_size": 0,
                    "unique_contributors": 0,
                    "active_contributors_90d": 0,
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
            profile = {
                "file_path": file_path,
                "owner_count": owner_count,
                "top_contributor_share": top_share,
                "bus_factor": self._bus_factor(counts),
                "ownership_risk": ownership_risk,
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
                "unique_contributors": len(repo_counts),
                "active_contributors_90d": len(active_contributors),
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
