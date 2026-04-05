"""Aggregate raw debt items into product-ready findings and summaries."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from tools.scoring import max_severity, severity_rank


class FindingAggregator:
    """Build normalized findings, module summaries, and roadmap items."""

    def _make_finding_id(self, item: dict[str, Any]) -> str:
        """Create a stable identifier for a debt item."""
        raw = "|".join(
            [
                str(item.get("file", "")),
                str(item.get("category", "")),
                str(item.get("type", "")),
                str(item.get("function", "")),
                str(item.get("line", "")),
            ]
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _module_name(self, file_path: str) -> str:
        """Return a stable module bucket for a file path."""
        path = Path(file_path)
        parent = str(path.parent).replace("\\", "/")
        return "." if parent in ("", ".") else parent

    def normalize_findings(
        self, debt_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert debt items into a richer, stable finding format."""
        findings: list[dict[str, Any]] = []

        for item in debt_items:
            file_path = item.get("file", "unknown")
            category = item.get("category", "code_quality")
            severity = str(item.get("severity", "low")).lower()
            finding = {
                "id": self._make_finding_id(item),
                "file_path": file_path,
                "module": self._module_name(file_path),
                "category": category,
                "subcategory": item.get("type"),
                "symbol_name": item.get("function"),
                "line_start": item.get("line", item.get("line_number")),
                "line_end": item.get("line", item.get("line_number")),
                "severity": severity,
                "business_impact": item.get("business_impact", "medium"),
                "effort_hours": round(float(item.get("remediation_hours", 0.0)), 2),
                "cost_usd": round(float(item.get("cost_usd", 0.0)), 2),
                "confidence": round(float(item.get("confidence", 0.5)), 2),
                "source_tool": self._source_tool(item),
                "evidence": self._build_evidence(item),
                "status": "open",
            }
            if item.get("owner_count") is not None:
                finding["owner_count"] = int(item["owner_count"])
            if item.get("top_contributor_share") is not None:
                finding["top_contributor_share"] = round(
                    float(item["top_contributor_share"]), 2
                )
            if item.get("ownership_risk") is not None:
                finding["ownership_risk"] = str(item["ownership_risk"])
            findings.append(finding)

        findings.sort(
            key=lambda f: (
                severity_rank(f["severity"]),
                f["cost_usd"],
                f["confidence"],
            ),
            reverse=True,
        )
        return findings

    def _source_tool(self, item: dict[str, Any]) -> str:
        """Infer the primary source tool for a debt item."""
        category = item.get("category", "code_quality")
        if category == "security":
            return "bandit"
        if category == "dependency":
            return "osv"
        if category == "documentation":
            return "ast"
        if item.get("used_fallback"):
            return "complexity_fallback"
        return "git+static"

    def _build_evidence(self, item: dict[str, Any]) -> list[dict[str, str]]:
        """Build concise evidence records from the raw debt item."""
        evidence: list[dict[str, str]] = []

        if item.get("complexity") is not None:
            evidence.append(
                {
                    "source": "complexity",
                    "summary": f"Complexity score {item['complexity']}",
                }
            )
        if item.get("change_count") is not None:
            evidence.append(
                {
                    "source": "git_history",
                    "summary": f"Changed {item['change_count']} times in sampled history",
                }
            )
        if item.get("issue_text"):
            evidence.append(
                {
                    "source": "security_scan",
                    "summary": str(item["issue_text"])[:160],
                }
            )
        if item.get("doc_type"):
            evidence.append(
                {
                    "source": "documentation",
                    "summary": f"Missing documentation type: {item['doc_type']}",
                }
            )
        if item.get("package"):
            evidence.append(
                {
                    "source": "dependency",
                    "summary": f"Package {item['package']} requires attention",
                }
            )
        if item.get("owner_count") is not None:
            ownership_summary = (
                f"{item['owner_count']} contributors"
                f", top contributor share {float(item.get('top_contributor_share', 0.0)):.0%}"
            )
            evidence.append(
                {
                    "source": "ownership",
                    "summary": ownership_summary,
                }
            )

        if not evidence:
            evidence.append(
                {
                    "source": "analysis",
                    "summary": f"{item.get('category', 'debt')} finding from analysis pipeline",
                }
            )
        return evidence

    def summarize_modules(
        self,
        findings: list[dict[str, Any]],
        ownership_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate findings at the module level."""
        modules: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "module": ".",
                "finding_count": 0,
                "total_cost_usd": 0.0,
                "total_effort_hours": 0.0,
                "severities": [],
                "avg_confidence": 0.0,
            }
        )

        for finding in findings:
            module_name = finding["module"]
            module = modules[module_name]
            module["module"] = module_name
            module["finding_count"] += 1
            module["total_cost_usd"] += finding["cost_usd"]
            module["total_effort_hours"] += finding["effort_hours"]
            module["severities"].append(finding["severity"])
            module["avg_confidence"] += finding["confidence"]

        summaries: list[dict[str, Any]] = []
        module_ownership = (ownership_context or {}).get("modules", {})
        for module in modules.values():
            count = max(module["finding_count"], 1)
            summary = {
                "module": module["module"],
                "finding_count": module["finding_count"],
                "total_cost_usd": round(module["total_cost_usd"], 2),
                "total_effort_hours": round(module["total_effort_hours"], 2),
                "max_severity": max_severity(module["severities"]),
                "avg_confidence": round(module["avg_confidence"] / count, 2),
            }
            ownership = module_ownership.get(module["module"], {})
            if ownership:
                summary["owner_count"] = int(ownership.get("owner_count", 0))
                summary["top_contributor_share"] = round(
                    float(ownership.get("top_contributor_share", 0.0)), 2
                )
                summary["ownership_risk"] = str(
                    ownership.get("ownership_risk", "low")
                )
            summaries.append(summary)

        summaries.sort(
            key=lambda m: (severity_rank(m["max_severity"]), m["total_cost_usd"]),
            reverse=True,
        )
        return summaries

    def build_roadmap(
        self, findings: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Create an initial remediation roadmap from findings."""
        quick_wins: list[dict[str, Any]] = []
        next_up: list[dict[str, Any]] = []
        strategic: list[dict[str, Any]] = []

        for finding in findings:
            roadmap_item = {
                "finding_id": finding["id"],
                "title": f"{finding['category'].replace('_', ' ').title()} in {finding['file_path']}",
                "file_path": finding["file_path"],
                "module": finding["module"],
                "severity": finding["severity"],
                "business_impact": finding["business_impact"],
                "effort_hours": finding["effort_hours"],
                "cost_usd": finding["cost_usd"],
                "confidence": finding["confidence"],
            }

            if (
                finding["effort_hours"] <= 4
                and finding["confidence"] >= 0.6
                and severity_rank(finding["severity"]) >= severity_rank("medium")
            ):
                quick_wins.append(roadmap_item)
            elif (
                finding["effort_hours"] >= 8
                or severity_rank(finding["severity"]) >= severity_rank("critical")
            ):
                strategic.append(roadmap_item)
            else:
                next_up.append(roadmap_item)

        return {
            "quick_wins": quick_wins[:10],
            "next_up": next_up[:10],
            "strategic": strategic[:10],
        }

    def aggregate(
        self,
        debt_items: list[dict[str, Any]],
        ownership_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the full aggregation flow."""
        findings = self.normalize_findings(debt_items)
        module_summaries = self.summarize_modules(
            findings, ownership_context=ownership_context
        )
        roadmap = self.build_roadmap(findings)

        return {
            "findings": findings,
            "module_summaries": module_summaries,
            "roadmap": roadmap,
        }
