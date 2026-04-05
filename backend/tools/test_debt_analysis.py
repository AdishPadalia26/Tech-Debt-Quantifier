"""Analyze missing and weak test coverage signals."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from constants import SKIP_DIRS, TEST_DIR_NAMES, TEST_FILE_PATTERNS
from tools.scoring import build_finding_payload, calculate_confidence


class TestDebtAnalyzer:
    """Detect source files that appear to lack corresponding tests."""

    SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}

    def _is_test_file(self, file_path: str) -> bool:
        """Return whether a path looks like a test file."""
        normalized = file_path.replace("\\", "/").lower()
        filename = os.path.basename(normalized)

        if any(part in TEST_DIR_NAMES for part in Path(normalized).parts):
            return True
        return any(pattern in filename for pattern in TEST_FILE_PATTERNS)

    def _is_source_file(self, file_path: str) -> bool:
        """Return whether a path should be considered source code."""
        path = Path(file_path)
        if path.suffix.lower() not in self.SOURCE_EXTENSIONS:
            return False
        return not self._is_test_file(file_path)

    def _iter_source_and_test_files(self, repo_path: str) -> tuple[list[str], list[str]]:
        """Collect source and test files from the repository."""
        source_files: list[str] = []
        test_files: list[str] = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for file_name in files:
                file_path = os.path.join(root, file_name)
                relative_path = str(Path(os.path.relpath(file_path, repo_path)).as_posix())

                if self._is_test_file(relative_path):
                    test_files.append(relative_path)
                elif self._is_source_file(relative_path):
                    source_files.append(relative_path)

        return source_files, test_files

    def _has_matching_test(self, source_file: str, test_files: list[str]) -> bool:
        """Check whether a source file appears to have a corresponding test file."""
        stem = Path(source_file).stem.lower()
        normalized_tests = [t.lower() for t in test_files]

        candidates = {
            f"test_{stem}.py",
            f"{stem}_test.py",
            f"{stem}.test.ts",
            f"{stem}.test.tsx",
            f"{stem}.test.js",
            f"{stem}.spec.ts",
            f"{stem}.spec.tsx",
            f"{stem}.spec.js",
        }

        return any(
            test.endswith(candidate) or f"/{stem}/" in test
            for test in normalized_tests
            for candidate in candidates
        )

    def find_test_gaps(
        self,
        repo_path: str,
        hotspot_files: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Identify likely test debt, prioritizing hotspot files."""
        source_files, test_files = self._iter_source_and_test_files(repo_path)
        hotspot_set = {str(Path(path).as_posix()) for path in (hotspot_files or [])}
        findings: list[dict[str, Any]] = []

        for source_file in source_files:
            if self._has_matching_test(source_file, test_files):
                continue

            is_hotspot = source_file in hotspot_set
            severity = "high" if is_hotspot else "medium"
            remediation_hours = 4.0 if is_hotspot else 2.0
            confidence = calculate_confidence(category="test_debt")
            finding = build_finding_payload(
                file_path=source_file,
                category="test_debt",
                severity=severity,
                remediation_hours=remediation_hours,
                hourly_rate=84.55,
                confidence=confidence,
                business_impact="high" if is_hotspot else "medium",
                extra={
                    "type": "missing_tests",
                    "test_gap_type": "hotspot_without_tests" if is_hotspot else "source_without_tests",
                    "is_hotspot": is_hotspot,
                },
            )
            findings.append(finding)

        findings.sort(key=lambda item: (item.get("is_hotspot", False), item["cost_usd"]), reverse=True)
        return findings
