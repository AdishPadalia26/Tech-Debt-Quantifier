"""Test debt explanation service using the local LLM."""

from __future__ import annotations

from typing import Any

from intelligence.local_llm_service import LocalLLMService


class GapReviewAgent:
    """Review the highest-priority test debt findings."""

    def __init__(self, llm_service: LocalLLMService | None = None) -> None:
        self.llm_service = llm_service or LocalLLMService()

    async def review(self, test_findings: list[dict[str, Any]]) -> dict[str, Any]:
        """Return a short test-gap summary with deterministic fallback."""
        selected = test_findings[:3]
        if not selected:
            return {"summary": "", "focus_area": "", "source": "fallback"}

        prompt = (
            "You are reviewing test debt. Return ONLY a JSON object with keys: "
            "summary, focus_area, suggested_test_style. Use only the provided findings.\n\n"
            f"Test findings: {selected}"
        )
        parsed = await self.llm_service.invoke_json(prompt)
        if isinstance(parsed, dict):
            return {
                "summary": parsed.get("summary", ""),
                "focus_area": parsed.get("focus_area", ""),
                "suggested_test_style": parsed.get("suggested_test_style", ""),
                "source": "llm",
            }

        primary = selected[0].get("file_path", selected[0].get("file", "hotspot"))
        return {
            "summary": f"Test coverage is weakest around {primary}, which raises change risk for hotspot code.",
            "focus_area": primary,
            "suggested_test_style": "Add behavior-level tests around core flows and edge cases.",
            "source": "fallback",
        }
