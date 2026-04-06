"""Architecture-focused explanation service using the local LLM."""

from __future__ import annotations

from typing import Any

from intelligence.local_llm_service import LocalLLMService


class ArchitectureReviewAgent:
    """Explain the highest-risk architecture issues conservatively."""

    def __init__(self, llm_service: LocalLLMService | None = None) -> None:
        self.llm_service = llm_service or LocalLLMService()

    async def review(
        self,
        architecture_findings: list[dict[str, Any]],
        module_summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a short architecture review with fallback."""
        top_findings = architecture_findings[:3]
        top_modules = module_summaries[:3]
        if not top_findings and not top_modules:
            return {"summary": "", "recommended_boundary": "", "source": "fallback"}

        prompt = (
            "You are reviewing architecture debt. Return ONLY a JSON object with keys: "
            "summary, recommended_boundary, source_rationale. Keep the summary brief and concrete.\n\n"
            f"Architecture findings: {top_findings}\n"
            f"Module summaries: {top_modules}"
        )
        parsed = await self.llm_service.invoke_json(prompt)
        if isinstance(parsed, dict):
            return {
                "summary": parsed.get("summary", ""),
                "recommended_boundary": parsed.get("recommended_boundary", ""),
                "source_rationale": parsed.get("source_rationale", ""),
                "source": "llm",
            }

        highest_module = top_modules[0]["module"] if top_modules else "core module"
        return {
            "summary": f"Architecture risk is concentrated in {highest_module} and related structural hotspots.",
            "recommended_boundary": "Split orchestration, state management, and external integrations into clearer module boundaries.",
            "source_rationale": "Fallback structural summary from architecture findings",
            "source": "fallback",
        }
