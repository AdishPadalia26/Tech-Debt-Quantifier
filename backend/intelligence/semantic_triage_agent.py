"""Semantic triage for top findings using the local LLM."""

from __future__ import annotations

from typing import Any

from intelligence.local_llm_service import LocalLLMService


class SemanticTriageAgent:
    """Review the highest-risk findings with bounded local-LLM prompts."""

    def __init__(self, llm_service: LocalLLMService | None = None) -> None:
        self.llm_service = llm_service or LocalLLMService()

    async def triage(self, findings: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
        """Return semantic triage for the top findings, with deterministic fallback."""
        selected = findings[:limit]
        if not selected:
            return []

        prompt = self._build_prompt(selected)
        parsed = await self.llm_service.invoke_json(prompt)
        if isinstance(parsed, list):
            return [self._normalize_item(item, selected) for item in parsed if isinstance(item, dict)]
        return [self._fallback_item(finding) for finding in selected]

    def _build_prompt(self, findings: list[dict[str, Any]]) -> str:
        """Create a strict JSON-only semantic triage prompt."""
        return (
            "You are reviewing technical debt findings. "
            "Return ONLY a JSON array. Each item must include: "
            "finding_id, debt_type, justified, remediation_scope, action_hint, confidence_note. "
            "Use only the provided data. Do not invent files or metrics.\n\n"
            f"Findings:\n{findings}"
        )

    def _normalize_item(
        self, item: dict[str, Any], findings: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Normalize a parsed model item with conservative defaults."""
        matching = next(
            (finding for finding in findings if finding.get("id") == item.get("finding_id")),
            None,
        )
        if not matching:
            return {
                "finding_id": item.get("finding_id"),
                "debt_type": item.get("debt_type", "unknown"),
                "justified": bool(item.get("justified", False)),
                "remediation_scope": item.get("remediation_scope", "file"),
                "action_hint": item.get("action_hint", "Review finding"),
                "confidence_note": item.get("confidence_note", "Model-assisted review"),
            }
        return {
            "finding_id": matching.get("id"),
            "debt_type": item.get("debt_type", matching.get("category", "unknown")),
            "justified": bool(item.get("justified", False)),
            "remediation_scope": item.get("remediation_scope", "file"),
            "action_hint": item.get("action_hint", self._fallback_action(matching)),
            "confidence_note": item.get("confidence_note", "Model-assisted review"),
        }

    def _fallback_item(self, finding: dict[str, Any]) -> dict[str, Any]:
        """Return deterministic triage when the LLM is unavailable."""
        return {
            "finding_id": finding.get("id"),
            "debt_type": finding.get("category", "unknown"),
            "justified": False,
            "remediation_scope": "module" if finding.get("category") == "architecture" else "file",
            "action_hint": self._fallback_action(finding),
            "confidence_note": "Fallback heuristic review",
        }

    def _fallback_action(self, finding: dict[str, Any]) -> str:
        """Return a concise remediation hint from the finding category."""
        category = finding.get("category", "code_quality")
        if category == "architecture":
            return "Split responsibilities or break module coupling"
        if category == "test_debt":
            return "Add focused behavior tests around the hotspot"
        if category == "security":
            return "Patch the vulnerable code path and add a regression test"
        if category == "dependency":
            return "Pin and upgrade the dependency safely"
        return "Refactor the hotspot and simplify the code path"
