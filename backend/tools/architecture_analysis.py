"""Lightweight architectural debt analysis."""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from constants import (
    ARCHITECTURE_IMPORT_FANOUT_THRESHOLD,
    ARCHITECTURE_LOC_THRESHOLD,
    SKIP_DIRS,
)
from tools.scoring import build_finding_payload, calculate_confidence


class ArchitectureAnalyzer:
    """Detect structural maintainability issues with lightweight heuristics."""

    def _iter_python_files(self, repo_path: str) -> list[str]:
        """Return repository-relative Python file paths."""
        files: list[str] = []

        for root, dirs, filenames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                full_path = os.path.join(root, filename)
                relative_path = str(Path(os.path.relpath(full_path, repo_path)).as_posix())
                files.append(relative_path)

        return files

    def _read_ast(self, repo_path: str, relative_path: str) -> tuple[ast.AST | None, str]:
        """Parse a Python file into an AST."""
        full_path = os.path.join(repo_path, relative_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as file_handle:
                content = file_handle.read()
            return ast.parse(content, filename=full_path), content
        except Exception:
            return None, ""

    def _module_name_from_path(self, relative_path: str) -> str:
        """Convert a file path into a local Python module name."""
        path = Path(relative_path)
        module = ".".join(path.with_suffix("").parts)
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        return module

    def _local_imports(self, tree: ast.AST, known_modules: set[str]) -> set[str]:
        """Extract local Python imports from a file AST."""
        imports: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    for idx in range(len(parts), 0, -1):
                        candidate = ".".join(parts[:idx])
                        if candidate in known_modules:
                            imports.add(candidate)
                            break
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    parts = node.module.split(".")
                    for idx in range(len(parts), 0, -1):
                        candidate = ".".join(parts[:idx])
                        if candidate in known_modules:
                            imports.add(candidate)
                            break

        return imports

    def _detect_cycles(self, graph: dict[str, set[str]]) -> list[list[str]]:
        """Detect simple cycles in the module dependency graph."""
        visited: set[str] = set()
        active: set[str] = set()
        stack: list[str] = []
        cycles: set[tuple[str, ...]] = set()

        def walk(node: str) -> None:
            visited.add(node)
            active.add(node)
            stack.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    walk(neighbor)
                elif neighbor in active:
                    try:
                        cycle_start = stack.index(neighbor)
                    except ValueError:
                        continue
                    cycle = tuple(stack[cycle_start:] + [neighbor])
                    cycles.add(cycle)

            stack.pop()
            active.discard(node)

        for node in graph:
            if node not in visited:
                walk(node)

        return [list(cycle) for cycle in cycles]

    def analyze(self, repo_path: str, hourly_rate: float) -> list[dict[str, Any]]:
        """Return architecture findings for a repository."""
        python_files = self._iter_python_files(repo_path)
        known_modules = {self._module_name_from_path(path) for path in python_files}
        module_graph: dict[str, set[str]] = defaultdict(set)
        findings: list[dict[str, Any]] = []

        for relative_path in python_files:
            tree, content = self._read_ast(repo_path, relative_path)
            if tree is None:
                continue

            module_name = self._module_name_from_path(relative_path)
            imports = self._local_imports(tree, known_modules)
            module_graph[module_name] = imports

            line_count = len(content.splitlines())
            function_count = sum(
                1
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            )

            if line_count >= ARCHITECTURE_LOC_THRESHOLD and function_count >= 8:
                findings.append(
                    build_finding_payload(
                        file_path=relative_path,
                        category="architecture",
                        severity="high",
                        remediation_hours=8.0,
                        hourly_rate=hourly_rate,
                        confidence=calculate_confidence(category="static_analysis"),
                        business_impact="high",
                        extra={
                            "type": "oversized_module",
                            "line_count": line_count,
                            "function_count": function_count,
                            "module_name": module_name,
                        },
                    )
                )

            if len(imports) >= ARCHITECTURE_IMPORT_FANOUT_THRESHOLD:
                findings.append(
                    build_finding_payload(
                        file_path=relative_path,
                        category="architecture",
                        severity="medium",
                        remediation_hours=5.0,
                        hourly_rate=hourly_rate,
                        confidence=calculate_confidence(category="static_analysis"),
                        business_impact="medium",
                        extra={
                            "type": "high_fanout_module",
                            "import_fanout": len(imports),
                            "module_name": module_name,
                        },
                    )
                )

        for cycle in self._detect_cycles(module_graph):
            representative = cycle[0]
            file_path = representative.replace(".", "/") + ".py"
            findings.append(
                build_finding_payload(
                    file_path=file_path,
                    category="architecture",
                    severity="high",
                    remediation_hours=10.0,
                    hourly_rate=hourly_rate,
                    confidence=calculate_confidence(category="static_analysis"),
                    business_impact="high",
                    extra={
                        "type": "cyclic_dependency",
                        "cycle": cycle,
                        "module_name": representative,
                    },
                )
            )

        findings.sort(key=lambda item: item["cost_usd"], reverse=True)
        return findings
