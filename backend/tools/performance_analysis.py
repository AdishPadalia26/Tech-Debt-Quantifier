"""Local performance smell analysis using Python AST heuristics."""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

from constants import SKIP_DIRS, SKIP_FILE_PATTERNS
from tools.scoring import build_finding_payload, calculate_confidence

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Detect local performance smells without external services."""

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

    def analyze(self, repo_path: str, hourly_rate: float) -> list[dict[str, Any]]:
        """Return performance findings for Python source files."""
        findings: list[dict[str, Any]] = []

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
                        tree = ast.parse(handle.read(), filename=file_path)
                except Exception:
                    continue

                findings.extend(self._analyze_tree(rel_path, tree, hourly_rate))

        findings.sort(key=lambda item: item["cost_usd"], reverse=True)
        logger.info("Performance analysis found %s findings", len(findings))
        return findings

    def _analyze_tree(
        self, file_path: str, tree: ast.AST, hourly_rate: float
    ) -> list[dict[str, Any]]:
        """Return performance findings for an AST."""
        findings: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                findings.extend(self._loop_findings(file_path, node, hourly_rate))
        return findings

    def _loop_findings(
        self,
        file_path: str,
        loop_node: ast.For | ast.While,
        hourly_rate: float,
    ) -> list[dict[str, Any]]:
        """Return findings related to expensive loop patterns."""
        findings: list[dict[str, Any]] = []

        for child in ast.walk(loop_node):
            if child is loop_node:
                continue

            if isinstance(child, (ast.For, ast.While)):
                findings.append(
                    build_finding_payload(
                        file_path=file_path,
                        category="performance",
                        severity="medium",
                        remediation_hours=1.5,
                        hourly_rate=hourly_rate,
                        confidence=calculate_confidence(category="static_analysis"),
                        business_impact="medium",
                        extra={
                            "line": child.lineno,
                            "type": "nested_loop",
                        },
                    )
                )
                break

            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == "append" and isinstance(child.func.value, ast.BinOp):
                    findings.append(
                        build_finding_payload(
                            file_path=file_path,
                            category="performance",
                            severity="medium",
                            remediation_hours=1.0,
                            hourly_rate=hourly_rate,
                            confidence=calculate_confidence(category="static_analysis"),
                            business_impact="low",
                            extra={
                                "line": child.lineno,
                                "type": "append_on_expression_in_loop",
                            },
                        )
                    )

            if isinstance(child, ast.AugAssign) and isinstance(child.op, ast.Add):
                if isinstance(child.target, ast.Name):
                    findings.append(
                        build_finding_payload(
                            file_path=file_path,
                            category="performance",
                            severity="medium",
                            remediation_hours=1.25,
                            hourly_rate=hourly_rate,
                            confidence=calculate_confidence(category="static_analysis"),
                            business_impact="medium",
                            extra={
                                "line": child.lineno,
                                "target": child.target.id,
                                "type": "accumulation_in_loop",
                            },
                        )
                    )
        return findings
