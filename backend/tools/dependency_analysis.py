"""Local dependency hygiene analysis for free-only deployments."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tools.scoring import build_finding_payload, calculate_confidence

logger = logging.getLogger(__name__)


class DependencyDebtAnalyzer:
    """Detect dependency debt from loose or risky version specifications."""

    REQUIREMENTS_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(.*)$")

    def _requirements_files(self, repo_path: str) -> list[Path]:
        """Return known dependency manifest files inside the repository root."""
        candidates = [
            Path(repo_path) / "requirements.txt",
            Path(repo_path) / "pyproject.toml",
            Path(repo_path) / "package.json",
        ]
        return [path for path in candidates if path.exists()]

    def _analyze_requirements(self, path: Path, hourly_rate: float) -> list[dict[str, Any]]:
        """Analyze pip requirements for loose pinning."""
        findings: list[dict[str, Any]] = []
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            match = self.REQUIREMENTS_PATTERN.match(line)
            if not match:
                continue
            package, spec = match.groups()
            spec = spec.strip()
            severity = None
            issue = None
            if not spec:
                severity = "medium"
                issue = "unbounded_version"
            elif any(token in spec for token in ["*", "latest"]):
                severity = "high"
                issue = "wildcard_version"
            elif spec.startswith((">=", "~=", ">", "<", "^")) and "==" not in spec:
                severity = "medium"
                issue = "range_pinned_version"

            if not severity or not issue:
                continue

            findings.append(
                build_finding_payload(
                    file_path=path.name,
                    category="dependency",
                    severity=severity,
                    remediation_hours=0.75 if severity == "medium" else 1.5,
                    hourly_rate=hourly_rate,
                    confidence=calculate_confidence(category="dependency"),
                    business_impact="medium",
                    extra={
                        "package": package,
                        "line": line_no,
                        "version_specifier": spec,
                        "type": issue,
                    },
                )
            )
        return findings

    def _analyze_package_json(self, path: Path, hourly_rate: float) -> list[dict[str, Any]]:
        """Analyze npm package manifests for loose ranges."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            return []

        findings: list[dict[str, Any]] = []
        for section in ("dependencies", "devDependencies"):
            deps = payload.get(section, {})
            if not isinstance(deps, dict):
                continue
            for package, version in deps.items():
                severity = None
                issue = None
                if version in ("latest", "*"):
                    severity = "high"
                    issue = "wildcard_version"
                elif str(version).startswith(("^", "~", ">", "<")):
                    severity = "medium"
                    issue = "range_pinned_version"

                if not severity or not issue:
                    continue

                findings.append(
                    build_finding_payload(
                        file_path=path.name,
                        category="dependency",
                        severity=severity,
                        remediation_hours=0.75 if severity == "medium" else 1.5,
                        hourly_rate=hourly_rate,
                        confidence=calculate_confidence(category="dependency"),
                        business_impact="medium",
                        extra={
                            "package": package,
                            "dependency_section": section,
                            "version_specifier": version,
                            "type": issue,
                        },
                    )
                )
        return findings

    def analyze(self, repo_path: str, hourly_rate: float) -> list[dict[str, Any]]:
        """Return local dependency debt findings from manifest hygiene."""
        findings: list[dict[str, Any]] = []
        for manifest in self._requirements_files(repo_path):
            if manifest.name == "requirements.txt":
                findings.extend(self._analyze_requirements(manifest, hourly_rate))
            elif manifest.name == "package.json":
                findings.extend(self._analyze_package_json(manifest, hourly_rate))

        findings.sort(key=lambda item: item["cost_usd"], reverse=True)
        logger.info("Dependency debt analysis found %s findings", len(findings))
        return findings
