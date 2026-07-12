"""Static analysis tools using Radon and Lizard.

Analyzes code complexity, finds missing docstrings, and runs security scans.
All numeric values are imported from constants.py.
"""

import ast
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import lizard
import radon
from radon.complexity import cc_visit
from tqdm import tqdm

from constants import (
    BANDIT_REMEDIATION_HOURS,
    COMPLEXITY_THRESHOLDS,
    MAX_WORKERS,
    SKIP_DIRS,
    SKIP_FILE_PATTERNS,
    SONAR_SEVERITY_MINUTES,
)

logger = logging.getLogger(__name__)

MAX_FILES = 200
MAX_FILE_SIZE_KB = 500
MAX_NOTEBOOK_SIZE_KB = 15_000
HARD_SKIP_PATTERNS = [
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    "coverage",
    ".pytest_cache",
    ".min.js",
    ".min.css",
    ".lock",
    "package-lock.json",
    "yarn.lock",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
]


class StaticAnalyzer:
    """Analyzes code for technical debt using static analysis tools.
    
    Uses Radon for Python complexity, Lizard for multi-language complexity,
    AST parsing for docstring detection, and Bandit for security scanning.
    """

    def __init__(self) -> None:
        self._files_scanned = 0
        self._sampled_files: list[str] = []  # populated by get_summary(), reused by run_security_scan()

    def _should_skip_file(self, file_path: str) -> bool:
        """Check if file should be skipped based on patterns."""
        file_name = os.path.basename(file_path)
        normalized_path = file_path.replace("\\", "/")
        for pattern in HARD_SKIP_PATTERNS:
            if pattern in file_name or pattern in normalized_path:
                return True
        for pattern in SKIP_FILE_PATTERNS:
            if pattern.startswith("*"):
                if file_name.endswith(pattern[1:]):
                    return True
            elif pattern in file_name:
                return True
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            max_size_kb = (
                MAX_NOTEBOOK_SIZE_KB
                if file_ext == ".ipynb"
                else MAX_FILE_SIZE_KB
            )
            if os.path.getsize(file_path) > max_size_kb * 1024:
                return True
        except OSError:
            return True
        return False

    def _should_skip_dir(self, dir_path: str) -> bool:
        """Check if directory should be skipped."""
        dir_name = os.path.basename(dir_path)
        return dir_name in SKIP_DIRS

    def _get_severity(self, complexity: int) -> str:
        """Map cyclomatic complexity to severity level.
        
        Args:
            complexity: Cyclomatic complexity score
            
        Returns:
            Severity: 'low', 'medium', 'high', or 'critical'
        """
        for severity, (min_cx, max_cx) in COMPLEXITY_THRESHOLDS.items():
            if min_cx <= complexity <= max_cx:
                return severity
        return "critical"

    def analyze_file(self, file_path: str, repo_path: str) -> list[dict[str, Any]]:
        """Analyze a single file for complexity.
        
        Uses Radon for Python files and Lizard for other languages.
        
        Args:
            file_path: Absolute path to the file
            repo_path: Root path of the repository
            
        Returns:
            List of function-level complexity findings
        """
        results = []

        try:
            relative_path = os.path.relpath(file_path, repo_path)
            file_ext = os.path.splitext(file_path)[1].lower()

            if file_ext == ".ipynb":
                results = self._analyze_notebook_file(file_path, relative_path)
            elif file_ext == ".py":
                results = self._analyze_python_file(file_path, relative_path)
            else:
                results = self._analyze_lizard_file(file_path, relative_path)

        except Exception as e:
            logger.warning(f"Error analyzing {file_path}: {e}", exc_info=True)

        return results

    def _analyze_notebook_file(
        self, file_path: str, relative_path: str
    ) -> list[dict[str, Any]]:
        """Analyze Python code cells in a Jupyter notebook."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                notebook = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("Could not read notebook %s: %s", file_path, exc)
            return []

        code_blocks: list[str] = []
        for cell in notebook.get("cells", []):
            if not isinstance(cell, dict) or cell.get("cell_type") != "code":
                continue
            source = cell.get("source", [])
            if isinstance(source, list):
                code = "".join(str(part) for part in source)
            else:
                code = str(source)
            if code.strip():
                code_blocks.append(code)

        if not code_blocks:
            return []

        content = self._sanitize_notebook_code("\n\n".join(code_blocks))
        try:
            tree = ast.parse(content, filename=relative_path)
        except SyntaxError as exc:
            logger.debug("Could not parse notebook code %s: %s", file_path, exc)
            return []

        valid_lines = self._get_top_level_and_method_lines(tree)
        results = []
        try:
            functions = cc_visit(content)
        except SyntaxError as exc:
            logger.debug("Radon could not parse notebook %s: %s", file_path, exc)
            return []

        for func in functions:
            if func.lineno not in valid_lines:
                continue
            severity = self._get_severity(func.complexity)
            results.append(
                {
                    "file": relative_path,
                    "function": func.name,
                    "complexity": func.complexity,
                    "severity": severity,
                    "language": "python-notebook",
                    "line_number": func.lineno,
                    "full_name": f"{relative_path}:{func.lineno}",
                }
            )

        return results

    def _sanitize_notebook_code(self, content: str) -> str:
        """Remove notebook magic/shell lines that are not valid Python syntax."""
        cleaned_lines = []
        for line in content.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("%", "!", "?")):
                cleaned_lines.append("")
            else:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    def _analyze_python_file(self, file_path: str, relative_path: str) -> list[dict[str, Any]]:
        """Analyze Python file using Radon with AST filtering.
        
        Only counts:
        - Top-level functions (col_offset == 0)
        - Class methods (inside ClassDef nodes)
        
        Excludes:
        - Nested functions (inside other functions)
        
        Args:
            file_path: Path to Python file
            relative_path: Relative path for reporting
            
        Returns:
            List of complexity findings
        """
        results = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)
            
            # Get lines of class methods and top-level functions using AST
            top_level_and_method_lines = self._get_top_level_and_method_lines(tree)
            
            functions = cc_visit(content)

            for func in functions:
                # Filter: only include top-level functions or class methods
                if func.lineno not in top_level_and_method_lines:
                    continue
                    
                complexity = func.complexity
                severity = self._get_severity(complexity)
                full_name = f"{relative_path}:{func.lineno}"

                result = {
                    "file": relative_path,
                    "function": func.name,
                    "complexity": complexity,
                    "severity": severity,
                    "language": "python",
                    "line_number": func.lineno,
                    "full_name": full_name,
                }
                results.append(result)

        except (IOError, SyntaxError) as e:
            logger.warning(f"Error reading Python file {file_path}: {e}")

        return results

    def _get_top_level_and_method_lines(self, tree: ast.AST) -> set[int]:
        """Get line numbers of top-level functions and class methods.
        
        Args:
            tree: AST tree of Python file
            
        Returns:
            Set of line numbers that are top-level functions or class methods
        """
        valid_lines = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # All methods inside a class are valid
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        valid_lines.add(item.lineno)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Top-level functions have col_offset == 0
                if node.col_offset == 0:
                    valid_lines.add(node.lineno)
        
        return valid_lines

    def _analyze_lizard_file(self, file_path: str, relative_path: str) -> list[dict[str, Any]]:
        """Analyze non-Python file using Lizard.
        
        Args:
            file_path: Path to file
            relative_path: Relative path for reporting
            
        Returns:
            List of complexity findings
        """
        results = []

        try:
            result = lizard.analyze_file(file_path)
            file_ext = os.path.splitext(file_path)[1].lstrip(".") or "unknown"

            for func in result.function_list:
                complexity = func.cyclomatic_complexity
                severity = self._get_severity(complexity)

                result_dict = {
                    "file": relative_path,
                    "function": func.name,
                    "complexity": complexity,
                    "severity": severity,
                    "language": file_ext,
                    "line_number": func.start_line,
                    "full_name": f"{relative_path}:{func.start_line}",
                }
                results.append(result_dict)

        except Exception as e:
            logger.warning(f"Error analyzing with Lizard: {e}", exc_info=True)

        return results

    def find_missing_docstrings(self, repo_path: str) -> list[dict[str, Any]]:
        """Find Python functions without docstrings.
        
        Uses AST parsing to detect functions missing documentation.
        Skips private functions (starting with _) and __init__.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            List of functions missing docstrings
        """
        findings = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]

            for file in files:
                if not file.endswith((".py", ".ipynb")):
                    continue
                if self._should_skip_file(os.path.join(root, file)):
                    continue

                file_path = os.path.join(root, file)
                findings.extend(self._check_file_docstrings(file_path, repo_path))

        logger.info(f"Found {len(findings)} functions missing docstrings")
        return findings

    def _check_file_docstrings(
        self, file_path: str, repo_path: str
    ) -> list[dict[str, Any]]:
        """Check a single file for missing docstrings.
        
        Detects missing docstrings for:
        - Classes (not just functions)
        - Top-level functions (including single underscore _ prefixed)
        - Class methods (including _ prefixed, but not __dunder__ methods)
        
        Skips:
        - __init__ methods if their class has a docstring
        - Dunder methods like __str__, __repr__, __len__, etc.
        
        Args:
            file_path: Path to Python file
            repo_path: Root path for relative paths
            
        Returns:
            List of missing docstring findings
        """
        findings = []

        try:
            if file_path.endswith(".ipynb"):
                content = self._notebook_code_content(file_path)
            else:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            if not content.strip():
                return findings

            tree = ast.parse(content, filename=file_path)
            relative_path = os.path.relpath(file_path, repo_path)

            # Track which classes have docstrings (to decide whether to skip __init__)
            class_docstrings: dict[int, bool] = {}

            # First pass: check classes for docstrings
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    has_docstring = ast.get_docstring(node) is not None
                    class_docstrings[node.lineno] = has_docstring

            # Second pass: check functions and classes for missing docstrings
            for node in ast.walk(tree):
                # Check for missing class docstrings
                if isinstance(node, ast.ClassDef):
                    if ast.get_docstring(node) is None:
                        findings.append({
                            "file": relative_path,
                            "function": node.name,
                            "line": node.lineno,
                            "category": "documentation",
                            "severity": "low",
                            "remediation_minutes": 10.0,
                            "type": "missing_class_docstring",
                        })
                    continue

                # Check for missing function docstrings
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Skip dunder methods like __str__, __repr__, __len__
                    if node.name.startswith("__") and node.name.endswith("__"):
                        continue
                    
                    # Skip __init__ only if the class has a docstring
                    if node.name == "__init__":
                        class_lineno = self._get_parent_class_lineno(node, tree)
                        if class_lineno and class_docstrings.get(class_lineno, False):
                            continue
                    
                    # Check for missing docstring
                    if ast.get_docstring(node) is None:
                        findings.append({
                            "file": relative_path,
                            "function": node.name,
                            "line": node.lineno,
                            "category": "documentation",
                            "severity": "low",
                            "remediation_minutes": float(
                                SONAR_SEVERITY_MINUTES["MINOR"]
                            ),
                            "type": "missing_docstring",
                        })

        except (SyntaxError, IOError) as e:
            logger.debug(f"Could not parse {file_path}: {e}")

        return findings

    def _notebook_code_content(self, file_path: str) -> str:
        """Return concatenated code cell content from a notebook."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                notebook = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return ""

        blocks: list[str] = []
        for cell in notebook.get("cells", []):
            if not isinstance(cell, dict) or cell.get("cell_type") != "code":
                continue
            source = cell.get("source", [])
            if isinstance(source, list):
                code = "".join(str(part) for part in source)
            else:
                code = str(source)
            if code.strip():
                blocks.append(code)
        return self._sanitize_notebook_code("\n\n".join(blocks))

    def _get_parent_class_lineno(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef, tree: ast.AST) -> int | None:
        """Find the lineno of the parent class for a function node."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if item is func_node:
                        return node.lineno
        return None

    def run_security_scan(self, repo_path: str) -> list[dict[str, Any]]:
        """Run Bandit security scan on repository.
        
        Filters results to only include significant findings:
        - HIGH severity (any confidence)
        - MEDIUM severity + MEDIUM/HIGH confidence
        
        Discards noise:
        - LOW severity + LOW/MEDIUM confidence
        
        Args:
            repo_path: Path to repository
            
        Returns:
            List of security findings with remediation estimates
        """
        findings = []
        total_found = 0

        # Scan the repository RECURSIVELY (`bandit -r <repo>`) instead of passing
        # every file path as a command-line argument. Passing a file list breaks
        # on large repos like Django/Flask: 2,900+ paths overflow the Windows
        # 32,767-char command-line limit, raising WinError 206 (FileNotFoundError)
        # which was previously misreported as "Bandit not installed" and silently
        # returned zero findings. Recursive mode also covers 100% of files (not a
        # 200-file sample) and stays fast (~10s on the full Django tree).
        exclude_arg = self._bandit_exclude_arg()
        cmd = [
            sys.executable, "-m", "bandit",
            "-r", repo_path,
            "-f", "json", "-q",
            "--exclude", exclude_arg,
        ]
        logger.info("[BANDIT] Recursively scanning %s (excludes: %s)", repo_path, exclude_arg)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            try:
                bandit_output = json.loads(result.stdout)
            except json.JSONDecodeError:
                # Empty stdout with a usage/error message means bandit could not
                # run (bad args, no targets). Surface stderr so it is debuggable
                # instead of silently returning zero findings.
                stderr_head = (result.stderr or "").strip()[:300]
                logger.warning(
                    "[BANDIT] Non-JSON output (rc=%s). stderr: %s",
                    result.returncode, stderr_head or "<empty>",
                )
                return findings

            for issue in bandit_output.get("results", []):
                total_found += 1
                severity = issue.get("issue_severity", "LOW")
                confidence = issue.get("issue_confidence", "LOW")
                test_id = issue.get("test_id", "unknown")

                # Filter: keep significant issues only
                # Keep:
                # - HIGH severity (any confidence)
                # - MEDIUM severity + MEDIUM/HIGH confidence
                # Remove: LOW severity or LOW confidence
                is_high = severity == "HIGH"
                is_medium_with_confidence = (
                    severity == "MEDIUM" and confidence in ("MEDIUM", "HIGH")
                )
                
                if not (is_high or is_medium_with_confidence):
                    continue  # Skip noise: LOW severity or LOW confidence

                remediation_hours = BANDIT_REMEDIATION_HOURS.get(
                    severity, BANDIT_REMEDIATION_HOURS["LOW"]
                )

                findings.append({
                    "file": issue.get("filename", "unknown"),
                    "line": issue.get("line_number", 0),
                    "issue_text": issue.get("issue_text", ""),
                    "severity": severity,
                    "confidence": confidence,
                    "bandit_test_id": test_id,
                    "remediation_hours": remediation_hours,
                    "category": "security",
                    "type": "security_hotspot",
                })

        except subprocess.TimeoutExpired:
            logger.warning("[BANDIT] Scan timed out after 300s")
        except OSError as e:
            # WinError 206 (command line too long) and a genuinely missing
            # interpreter both surface here. With recursive scanning the command
            # line is tiny, so this almost always means bandit is not installed —
            # but log the real error instead of guessing.
            logger.error("[BANDIT] Could not launch bandit: %s", e)
        except Exception as e:
            logger.warning(f"[BANDIT] Scan failed: {e}", exc_info=True)

        logger.info(f"[BANDIT] Total found: {total_found}, After filtering: {len(findings)}")
        return findings

    def _bandit_exclude_arg(self) -> str:
        """Build bandit's comma-separated --exclude glob list.

        Derives directory excludes from SKIP_DIRS (build artifacts, vendored
        deps, virtualenvs) plus common test directories, since test files
        generate high-volume low-signal findings (asserts, fixture passwords).
        """
        from constants import SKIP_DIRS

        # NB: do NOT add ".cache" here — cloned repos live under backend/.cache/,
        # and bandit matches --exclude globs against the full absolute path, so
        # "*/.cache/*" would match the entire repo and exclude every file.
        dir_names = set(SKIP_DIRS) | {"tests", "test", "testing", "migrations"}
        patterns = [f"*/{name}/*" for name in sorted(dir_names)]
        # Also exclude noisy generated/minified files.
        patterns += ["*_pb2.py", "*.min.js"]
        return ",".join(patterns)

    def get_summary(self, repo_path: str) -> dict[str, Any]:
        """Get comprehensive analysis summary for a repository.
        
        Scans all files in parallel using ThreadPoolExecutor.
        Shows progress bar with tqdm.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Summary dictionary with metrics and findings
        """
        _CODE_EXTENSIONS = {
            ".py", ".js", ".ts", ".tsx", ".jsx",
            ".ipynb",
            ".java", ".go", ".rs", ".cpp", ".c", ".cc", ".cxx",
            ".cs", ".rb", ".php", ".swift", ".kt", ".scala",
        }

        start_time = time.time()
        all_functions = []
        file_list = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]

            for file in files:
                file_path = os.path.join(root, file)
                if self._should_skip_file(file_path):
                    continue
                if os.path.splitext(file)[1].lower() not in _CODE_EXTENSIONS:
                    continue
                file_list.append(file_path)

        total_files = len(file_list)
        if total_files > MAX_FILES:
            logger.info(
                "Sampling %s files out of %s (stratified shuffle for coverage)",
                MAX_FILES, total_files,
            )
            import random
            random.Random(42).shuffle(file_list)
            file_list = file_list[:MAX_FILES]
            total_files = len(file_list)
        self._sampled_files = file_list  # share with run_security_scan()
        logger.info(f"Starting analysis of {total_files} files")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self.analyze_file, fp, repo_path): fp
                for fp in file_list
            }

            with tqdm(total=total_files, desc="Scanning files") as pbar:
                for future in as_completed(futures):
                    try:
                        results = future.result()
                        all_functions.extend(results)
                        self._files_scanned += 1

                        if self._files_scanned % 100 == 0:
                            pct = (self._files_scanned / total_files) * 100
                            logger.info(
                                f"Scanned {self._files_scanned}/{total_files} files ({pct:.1f}%)"
                            )

                    except Exception as e:
                        logger.warning(f"Error processing file: {e}", exc_info=True)
                    pbar.update(1)

        total_complexity = sum(f["complexity"] for f in all_functions)
        avg_complexity = total_complexity / len(all_functions) if all_functions else 0

        complexity_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for func in all_functions:
            severity = func["severity"]
            if severity in complexity_dist:
                complexity_dist[severity] += 1

        file_complexity: dict[str, list[int]] = {}
        for func in all_functions:
            file_path = func["file"]
            if file_path not in file_complexity:
                file_complexity[file_path] = []
            file_complexity[file_path].append(func["complexity"])

        worst_files = sorted(
            [
                {"file": fp, "max_complexity": max(cplx_list)}
                for fp, cplx_list in file_complexity.items()
            ],
            key=lambda x: x["max_complexity"],
            reverse=True,
        )[:5]

        high_risk = [f for f in all_functions if f["severity"] in ("high", "critical")]

        duration = time.time() - start_time

        summary = {
            "total_files_scanned": self._files_scanned,
            "total_functions": len(all_functions),
            "avg_complexity": round(avg_complexity, 2),
            "complexity_distribution": complexity_dist,
            "worst_files": worst_files,
            "high_risk_functions": high_risk,
            "scan_duration_seconds": round(duration, 2),
            "all_functions": all_functions,
        }

        logger.info(
            f"Analysis complete: {len(all_functions)} functions in "
            f"{self._files_scanned} files in {duration:.2f}s"
        )

        return summary
