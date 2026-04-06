"""Executive report writing with local-LLM and deterministic fallback."""

from __future__ import annotations

from typing import Any

from intelligence.local_llm_service import LocalLLMService


class ReportWriterAgent:
    """Generate executive summary, priorities, and ROI for a scan."""

    def __init__(self, llm_service: LocalLLMService | None = None) -> None:
        self.llm_service = llm_service or LocalLLMService()

    async def executive_summary(
        self,
        analysis: dict[str, Any],
        insights: dict[str, Any],
    ) -> str:
        """Return a short executive summary with fallback."""
        prompt = (
            "Write a concise 3-sentence executive summary for a technical debt scan. "
            "Use specific numbers and keep it plain. "
            "Return plain text only.\n\n"
            f"Analysis: total_cost={analysis.get('total_cost_usd')}, "
            f"debt_score={analysis.get('debt_score')}, "
            f"hours={analysis.get('total_remediation_hours')}, "
            f"top_modules={analysis.get('module_summaries', [])[:3]}, "
            f"insights={insights}"
        )
        summary = await self.llm_service.invoke_text(prompt)
        if summary:
            return summary.strip()
        return self._fallback_summary(analysis, insights)

    async def priority_actions(
        self,
        findings: list[dict[str, Any]],
        triage_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return a top-3 priority action list, bounded and structured."""
        top_findings = findings[:3]
        if not top_findings:
            return []

        prompt = (
            "Return ONLY a JSON array with up to 3 items. "
            "Each item must have rank, title, file_or_module, why, estimated_hours, "
            "estimated_cost, saves_per_month, sprint. "
            "Base your answer only on the findings and semantic triage below.\n\n"
            f"Findings: {top_findings}\n"
            f"Triage: {triage_items}"
        )
        parsed = await self.llm_service.invoke_json(prompt)
        if isinstance(parsed, list):
            normalized: list[dict[str, Any]] = []
            for index, item in enumerate(parsed[:3], start=1):
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "rank": int(item.get("rank", index)),
                        "title": item.get("title", f"Remediate {top_findings[index - 1].get('category', 'debt')}"),
                        "file_or_module": item.get(
                            "file_or_module",
                            top_findings[index - 1].get("module")
                            or top_findings[index - 1].get("file_path"),
                        ),
                        "why": item.get("why", "High-value remediation opportunity"),
                        "estimated_hours": float(
                            item.get("estimated_hours", top_findings[index - 1].get("effort_hours", 0))
                        ),
                        "estimated_cost": float(
                            item.get("estimated_cost", top_findings[index - 1].get("cost_usd", 0))
                        ),
                        "saves_per_month": float(item.get("saves_per_month", 0)),
                        "sprint": item.get("sprint", f"Sprint {index}"),
                    }
                )
            if normalized:
                return normalized
        return self._fallback_priorities(top_findings, triage_items)

    def roi_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Return deterministic ROI analysis from scan metrics."""
        total_cost = float(analysis.get("total_cost_usd", 0) or 0)
        annual_savings = round(total_cost * 0.40, 2)
        payback_months = round((total_cost / annual_savings) * 12) if annual_savings else 99
        roi_pct = round(((annual_savings * 3 - total_cost) / total_cost) * 100) if total_cost else 0
        recommended_budget = round(total_cost / 4, 2) if total_cost else 0
        recommendation = (
            "Prioritize the top hotspots this quarter for the strongest maintenance ROI."
            if roi_pct > 0
            else "Focus on the highest-severity findings first and defer low-impact cleanup."
        )
        return {
            "total_fix_cost": round(total_cost, 2),
            "annual_maintenance_savings": round(annual_savings, 2),
            "payback_months": payback_months,
            "3_year_roi_pct": roi_pct,
            "recommended_budget": recommended_budget,
            "recommendation": recommendation,
        }

    def _fallback_summary(self, analysis: dict[str, Any], insights: dict[str, Any]) -> str:
        """Return a deterministic executive summary."""
        total_cost = float(analysis.get("total_cost_usd", 0) or 0)
        debt_score = float(analysis.get("debt_score", 0) or 0)
        total_hours = float(analysis.get("total_remediation_hours", 0) or 0)
        top_modules = analysis.get("module_summaries", []) or []
        top_module = top_modules[0]["module"] if top_modules else "the core module"
        architecture_note = insights.get("architecture_review", {}).get("summary", "")
        if architecture_note:
            return (
                f"The repository carries about ${total_cost:,.0f} in estimated technical debt "
                f"with a debt score of {debt_score:.1f}/10 and roughly {total_hours:.0f} remediation hours. "
                f"The highest concentration of risk is in {top_module}. "
                f"{architecture_note}"
            )
        return (
            f"The repository carries about ${total_cost:,.0f} in estimated technical debt "
            f"with a debt score of {debt_score:.1f}/10 and roughly {total_hours:.0f} remediation hours. "
            f"The highest concentration of risk is in {top_module}. "
            f"Start with the top hotspots and their surrounding tests to reduce both change risk and maintenance drag."
        )

    def _fallback_priorities(
        self,
        findings: list[dict[str, Any]],
        triage_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return deterministic priorities derived from findings."""
        triage_by_id = {item.get("finding_id"): item for item in triage_items}
        priorities: list[dict[str, Any]] = []
        for index, finding in enumerate(findings[:3], start=1):
            triage = triage_by_id.get(finding.get("id"), {})
            priorities.append(
                {
                    "rank": index,
                    "title": f"Remediate {finding.get('category', 'debt').replace('_', ' ')} in {finding.get('module') or finding.get('file_path')}",
                    "file_or_module": finding.get("module") or finding.get("file_path"),
                    "why": triage.get(
                        "action_hint",
                        "This is one of the highest-cost unresolved findings in the current scan.",
                    ),
                    "estimated_hours": round(float(finding.get("effort_hours", 0) or 0), 1),
                    "estimated_cost": round(float(finding.get("cost_usd", 0) or 0), 2),
                    "saves_per_month": round(float(finding.get("cost_usd", 0) or 0) * 0.015, 2),
                    "sprint": f"Sprint {index}",
                }
            )
        return priorities
