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


class StaticAnalyzer:
    """Analyzes code for technical debt using static analysis tools.
    
    Uses Radon for Python complexity, Lizard for multi-language complexity,
    AST parsing for docstring detection, and Bandit for security scanning.
    """

    def __init__(self) -> None:
        self._files_scanned = 0

    def _should_skip_file(self, file_path: str) -> bool:
        """Check if file should be skipped based on patterns."""
        file_name = os.path.basename(file_path)
        for pattern in SKIP_FILE_PATTERNS:
            if pattern.startswith("*"):
                if file_name.endswith(pattern[1:]):
                    return True
            elif pattern in file_name:
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

            if file_ext == ".py":
                results = self._analyze_python_file(file_path, relative_path)
            else:
                results = self._analyze_lizard_file(file_path, relative_path)

        except Exception as e:
            logger.warning(f"Error analyzing {file_path}: {e}")

        return results

    def _analyze_python_file(self, file_path: str, relative_path: str) -> list[dict[str, Any]]:
        """Analyze Python file using Radon.
        
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

            functions = cc_visit(content)

            for func in functions:
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
            logger.warning(f"Error analyzing with Lizard: {e}")

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
                if not file.endswith(".py"):
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
        
        Args:
            file_path: Path to Python file
            repo_path: Root path for relative paths
            
        Returns:
            List of missing docstring findings
        """
        findings = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)
            relative_path = os.path.relpath(file_path, repo_path)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("_") and node.name != "__init__":
                        continue
                    if node.name == "__init__":
                        continue

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

        try:
            result = subprocess.run(
                [sys.executable, "-m", "bandit", "-r", repo_path, "-f", "json", "-q"],
                capture_output=True,
                text=True,
                timeout=300,
            )

            try:
                bandit_output = json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning("Bandit returned non-JSON output")
                return findings

            for issue in bandit_output.get("results", []):
                total_found += 1
                severity = issue.get("issue_severity", "LOW")
                confidence = issue.get("issue_confidence", "LOW")
                test_id = issue.get("test_id", "unknown")

                # Filter: only keep significant issues
                # - HIGH severity (any confidence)
                # - MEDIUM severity + MEDIUM/HIGH confidence
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
            logger.warning("Bandit scan timed out")
        except FileNotFoundError:
            logger.error("Bandit not installed")
        except Exception as e:
            logger.warning(f"Bandit scan failed: {e}")

        logger.info(f"[BANDIT] Total found: {total_found}, After filtering: {len(findings)}")
        return findings

    def get_summary(self, repo_path: str) -> dict[str, Any]:
        """Get comprehensive analysis summary for a repository.
        
        Scans all files in parallel using ThreadPoolExecutor.
        Shows progress bar with tqdm.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Summary dictionary with metrics and findings
        """
        start_time = time.time()
        all_functions = []
        file_list = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]

            for file in files:
                file_path = os.path.join(root, file)
                if self._should_skip_file(file_path):
                    continue
                file_list.append(file_path)

        total_files = len(file_list)
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
                        logger.warning(f"Error processing file: {e}")
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
