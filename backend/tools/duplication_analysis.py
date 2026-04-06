"""Local duplication heuristics for technical debt analysis."""

from __future__ import annotations

import ast
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from constants import SKIP_DIRS, SKIP_FILE_PATTERNS
from tools.scoring import build_finding_payload, calculate_confidence

logger = logging.getLogger(__name__)


class DuplicationAnalyzer:
    """Detect duplicated Python function bodies using AST normalization."""

    def _should_skip_dir(self, dir_path: str) -> bool:
        """Return whether a directory should be skipped."""
        return os.path.basename(dir_path) in SKIP_DIRS

    def _should_skip_file(self, file_path: str) -> bool:
        """Return whether a file path should be skipped."""
        file_name = os.path.basename(file_path)
        for pattern in SKIP_FILE_PATTERNS:
            if pattern.startswith("*") and file_name.endswith(pattern[1:]):
                return True
            if not pattern.startswith("*") and pattern in file_name:
                return True
        return False

    def _normalize_body(self, node: ast.AST) -> str:
        """Normalize a function body to a stable duplication fingerprint."""
        clone = ast.fix_missing_locations(ast.Module(body=node.body, type_ignores=[]))
        return ast.dump(clone, annotate_fields=False, include_attributes=False)

    def analyze(self, repo_path: str, hourly_rate: float) -> list[dict[str, Any]]:
        """Return duplication findings for repeated Python function bodies."""
        candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]
            for file_name in files:
                if not file_name.endswith(".py"):
                    continue
                file_path = os.path.join(root, file_name)
                if self._should_skip_file(file_path):
                    continue
                rel_path = os.path.relpath(file_path, repo_path).replace("\\", "/")
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                        content = handle.read()
                    tree = ast.parse(content, filename=file_path)
                except Exception:
                    continue

                for node in ast.walk(tree):
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if len(getattr(node, "body", [])) < 2:
                        continue
                    fingerprint = self._normalize_body(node)
                    candidates[fingerprint].append(
                        {
                            "file": rel_path,
                            "function": node.name,
                            "line": node.lineno,
                            "statement_count": len(node.body),
                        }
                    )

        findings: list[dict[str, Any]] = []
        for duplicates in candidates.values():
            unique_files = {item["file"] for item in duplicates}
            if len(duplicates) < 2 or len(unique_files) < 2:
                continue

            duplication_count = len(duplicates)
            remediation_hours = min(8.0, 1.5 + (duplication_count - 2) * 1.25)
            severity = "high" if duplication_count >= 4 else "medium"

            for item in duplicates:
                findings.append(
                    build_finding_payload(
                        file_path=item["file"],
                        category="code_quality",
                        severity=severity,
                        remediation_hours=remediation_hours,
                        hourly_rate=hourly_rate,
                        confidence=calculate_confidence(category="static_analysis"),
                        business_impact="medium",
                        extra={
                            "function": item["function"],
                            "line": item["line"],
                            "duplication_count": duplication_count,
                            "duplicated_across_files": sorted(unique_files),
                            "statement_count": item["statement_count"],
                            "type": "duplicate_logic",
                        },
                    )
                )

        findings.sort(key=lambda item: item["cost_usd"], reverse=True)
        logger.info("Duplication analysis found %s findings", len(findings))
        return findings
