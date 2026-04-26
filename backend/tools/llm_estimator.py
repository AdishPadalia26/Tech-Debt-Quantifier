"""LLM-based effort estimator for tech debt items.

Uses the local Ollama model to produce realistic effort estimates
for individual debt items. The LLM estimates inputs to the cost
formula — it does NOT compute final dollar values.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class LLMEstimator:
    """Uses the local Ollama model to produce realistic effort estimates
    for individual debt items."""

    def __init__(self, ollama_client: Any, model: str) -> None:
        """Initialize with an existing Ollama client and model name."""
        self.client = ollama_client
        self.model = model

    def estimate_debt_item(
        self,
        file_path: str,
        category: str,
        severity: str,
        description: str,
        code_snippet: str = "",
        function_name: str = "",
        language: str = "",
    ) -> dict[str, Any]:
        """Ask the LLM to estimate realistic remediation effort."""
        prompt = self._build_estimation_prompt(
            file_path, category, severity, description,
            code_snippet, function_name, language,
        )

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2},
            )
            raw = response["message"]["content"]
            return self._parse_estimation_response(raw)
        except Exception as e:
            logger.warning(
                "LLM estimation failed for %s: %s. Falling back to formula defaults.",
                file_path, e,
            )
            return self._fallback_estimates(category, severity)

    def _build_estimation_prompt(
        self,
        file_path: str,
        category: str,
        severity: str,
        description: str,
        code_snippet: str,
        function_name: str,
        language: str,
    ) -> str:
        """Build the structured prompt sent to the LLM."""
        snippet_block = ""
        if code_snippet and len(code_snippet.strip()) > 10:
            truncated = code_snippet[:800]
            snippet_block = f"""
Code context:
```{language or ''}
{truncated}
 ```"""

        return f"""You are a senior software engineer estimating tech debt remediation effort.

Debt item details:
- File: {file_path}
- Function/class: {function_name or 'N/A'}
- Category: {category}
- Severity: {severity}
- Description: {description}
{snippet_block}

Respond ONLY with valid JSON in this exact format:
{{
  "realistic_hours": <float>,
  "severity_score": <integer 1-10>,
  "business_risk_score": <integer 1-10>,
  "fix_complexity_score": <integer 1-10>,
  "confidence": "high|medium|low",
  "primary_risk": <one sentence>,
  "fix_summary": <one sentence>,
  "cost_rationale": <2-3 sentences>
}}
"""

    def _parse_estimation_response(self, raw: str) -> dict[str, Any]:
        """Extract JSON from LLM response."""
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON found in LLM response")

        data = json.loads(match.group())

        return {
            "realistic_hours": max(0.05, min(200.0, float(data.get("realistic_hours", 2.0)))),
            "severity_score": max(1, min(10, int(data.get("severity_score", 5)))),
            "business_risk_score": max(1, min(10, int(data.get("business_risk_score", 5)))),
            "fix_complexity_score": max(1, min(10, int(data.get("fix_complexity_score", 5)))),
            "confidence": data.get("confidence", "medium"),
            "primary_risk": str(data.get("primary_risk", "")),
            "fix_summary": str(data.get("fix_summary", "")),
            "cost_rationale": str(data.get("cost_rationale", "")),
        }

    def _fallback_estimates(self, category: str, severity: str) -> dict[str, Any]:
        """Formula-only fallback when LLM is unavailable."""
        base_hours: dict[str, float] = {
            "security": 4.0, "code_quality": 1.5, "documentation": 0.5,
            "test_debt": 2.0, "dependency": 1.0, "architecture": 3.0,
            "reliability": 2.0, "performance": 1.5, "duplication": 1.0,
            "dead_code": 0.5,
        }
        severity_mult: dict[str, float] = {
            "critical": 2.0, "high": 1.5, "medium": 1.0, "low": 0.5,
        }
        severity_scores: dict[str, int] = {
            "critical": 9, "high": 7, "medium": 5, "low": 3,
        }
        risk_scores: dict[str, int] = {
            "critical": 8, "high": 6, "medium": 4, "low": 2,
        }

        cat_key = (category or "code_quality").lower().replace(" ", "_")
        sev_key = (severity or "medium").lower()
        base = base_hours.get(cat_key, 1.5)
        sev_mult = severity_mult.get(sev_key, 1.0)
        hours = base * sev_mult

        return {
            "realistic_hours": hours,
            "severity_score": severity_scores.get(sev_key, 5),
            "business_risk_score": risk_scores.get(sev_key, 4),
            "fix_complexity_score": 5,
            "confidence": "low",
            "primary_risk": f"Unresolved {category} debt may increase future costs.",
            "fix_summary": f"Standard {category} remediation required.",
            "cost_rationale": f"Estimated using defaults: {hours:.1f}h for {cat_key} at {sev_key}.",
        }

    def _fallback(self, category: str, severity: str) -> dict[str, Any]:
        """Static fallback for testing."""
        result = self._fallback_estimates(category, severity)
        result["source"] = "fallback"
        return result

    def _parse_response(self, raw: str, category: str, severity: str) -> dict[str, Any]:
        """Public parse method for testing."""
        try:
            return self._parse_estimation_response(raw)
        except Exception:
            return self._fallback(category, severity)