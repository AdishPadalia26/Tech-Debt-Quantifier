"""Local reliability smell analysis using Python AST heuristics."""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

from constants import SKIP_DIRS, SKIP_FILE_PATTERNS
from tools.scoring import build_finding_payload, calculate_confidence

logger = logging.getLogger(__name__)


class ReliabilityAnalyzer:
    """Detect reliability smells that increase production fragility."""

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
        """Return reliability findings from Python AST scans."""
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

                for node in ast.walk(tree):
                    if isinstance(node, ast.Try):
                        findings.extend(
                            self._reliability_findings_for_try(
                                rel_path, node, hourly_rate
                            )
                        )
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        findings.extend(
                            self._mutable_default_findings(
                                rel_path, node, hourly_rate
                            )
                        )

        findings.sort(key=lambda item: item["cost_usd"], reverse=True)
        logger.info("Reliability analysis found %s findings", len(findings))
        return findings

    def _reliability_findings_for_try(
        self,
        file_path: str,
        node: ast.Try,
        hourly_rate: float,
    ) -> list[dict[str, Any]]:
        """Return reliability findings related to a try/except block."""
        findings: list[dict[str, Any]] = []
        for handler in node.handlers:
            exception_name = ""
            if handler.type is None:
                severity = "high"
                issue_type = "bare_except"
                exception_name = "bare"
                effort = 2.0
            elif isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                severity = "medium"
                issue_type = "broad_exception"
                exception_name = "Exception"
                effort = 1.5
            else:
                severity = ""
                issue_type = ""
                effort = 0.0

            if issue_type:
                findings.append(
                    build_finding_payload(
                        file_path=file_path,
                        category="reliability",
                        severity=severity,
                        remediation_hours=effort,
                        hourly_rate=hourly_rate,
                        confidence=calculate_confidence(category="static_analysis"),
                        business_impact="medium",
                        extra={
                            "line": handler.lineno,
                            "exception": exception_name,
                            "type": issue_type,
                        },
                    )
                )

            if handler.body and all(isinstance(stmt, ast.Pass) for stmt in handler.body):
                findings.append(
                    build_finding_payload(
                        file_path=file_path,
                        category="reliability",
                        severity="high",
                        remediation_hours=2.0,
                        hourly_rate=hourly_rate,
                        confidence=calculate_confidence(category="static_analysis"),
                        business_impact="high",
                        extra={
                            "line": handler.lineno,
                            "type": "silent_exception_handler",
                        },
                    )
                )
        return findings

    def _mutable_default_findings(
        self,
        file_path: str,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        hourly_rate: float,
    ) -> list[dict[str, Any]]:
        """Return findings for mutable default arguments."""
        findings: list[dict[str, Any]] = []
        mutable_defaults = (
            ast.List,
            ast.Dict,
            ast.Set,
        )
        if any(isinstance(default, mutable_defaults) for default in node.args.defaults):
            findings.append(
                build_finding_payload(
                    file_path=file_path,
                    category="reliability",
                    severity="medium",
                    remediation_hours=1.25,
                    hourly_rate=hourly_rate,
                    confidence=calculate_confidence(category="static_analysis"),
                    business_impact="medium",
                    extra={
                        "function": node.name,
                        "line": node.lineno,
                        "type": "mutable_default_argument",
                    },
                )
            )
        return findings
