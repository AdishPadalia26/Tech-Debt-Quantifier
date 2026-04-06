"""Local dead code analysis using Python AST heuristics."""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

from constants import SKIP_DIRS, SKIP_FILE_PATTERNS
from tools.scoring import build_finding_payload, calculate_confidence

logger = logging.getLogger(__name__)


class DeadCodeAnalyzer:
    """Detect unreachable code and likely-unused private helpers."""

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
        """Return dead-code findings from Python source files."""
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

                findings.extend(self._unreachable_code_findings(rel_path, tree, hourly_rate))
                findings.extend(self._unused_private_function_findings(rel_path, tree, hourly_rate))

        findings.sort(key=lambda item: item["cost_usd"], reverse=True)
        logger.info("Dead code analysis found %s findings", len(findings))
        return findings

    def _unreachable_code_findings(
        self, file_path: str, tree: ast.AST, hourly_rate: float
    ) -> list[dict[str, Any]]:
        """Return findings for statements placed after terminal control flow."""
        findings: list[dict[str, Any]] = []
        terminal_nodes = (ast.Return, ast.Raise, ast.Continue, ast.Break)

        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or len(body) < 2:
                continue

            for index, stmt in enumerate(body[:-1]):
                if isinstance(stmt, terminal_nodes):
                    unreachable_stmt = body[index + 1]
                    findings.append(
                        build_finding_payload(
                            file_path=file_path,
                            category="code_quality",
                            severity="low",
                            remediation_hours=0.5,
                            hourly_rate=hourly_rate,
                            confidence=calculate_confidence(category="static_analysis"),
                            business_impact="low",
                            extra={
                                "line": getattr(unreachable_stmt, "lineno", getattr(stmt, "lineno", 0)),
                                "type": "unreachable_code",
                            },
                        )
                    )
                    break
        return findings

    def _unused_private_function_findings(
        self, file_path: str, tree: ast.AST, hourly_rate: float
    ) -> list[dict[str, Any]]:
        """Return findings for private helpers that are never referenced."""
        findings: list[dict[str, Any]] = []
        private_functions = [
            node
            for node in getattr(tree, "body", [])
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("_")
            and not node.name.startswith("__")
        ]
        if not private_functions:
            return findings

        referenced_names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }

        for func in private_functions:
            if func.name in referenced_names:
                continue
            findings.append(
                build_finding_payload(
                    file_path=file_path,
                    category="code_quality",
                    severity="low",
                    remediation_hours=0.75,
                    hourly_rate=hourly_rate,
                    confidence=calculate_confidence(category="static_analysis"),
                    business_impact="low",
                    extra={
                        "function": func.name,
                        "line": func.lineno,
                        "type": "unused_private_function",
                    },
                )
            )
        return findings
