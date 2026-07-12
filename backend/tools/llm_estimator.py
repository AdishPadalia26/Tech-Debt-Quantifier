"""LLM-based effort estimator for tech debt items.

Uses the configured LLM provider (Groq, NVIDIA NIM, etc. via llm_factory)
to produce realistic effort estimates for individual debt items. The LLM
estimates inputs to the cost formula — it does NOT compute final dollar values.
"""

import json
import logging
import re
from typing import Any

from langchain_core.language_models import BaseLLM
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


class LLMEstimator:
    """Uses the configured LLM (via llm_factory) to produce realistic effort
    estimates for individual debt items."""

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

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
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = response.content if hasattr(response, "content") else str(response)
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
        """Extract a single JSON estimate object from an LLM response."""
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON found in LLM response")

        return self._normalize_estimate(json.loads(match.group()))

    @staticmethod
    def _normalize_estimate(data: dict[str, Any]) -> dict[str, Any]:
        """Clamp/coerce a raw estimate dict into the canonical schema."""
        if not isinstance(data, dict):
            raise ValueError("Estimate is not a JSON object")
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

    def estimate_debt_items_batch(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Estimate a batch of debt items in a SINGLE LLM call.

        Each item dict may carry: file_path, category, severity, description,
        code_snippet, function_name, language. Returns one estimate dict per
        input item, in the same order. Any item the LLM omits or mangles falls
        back to formula defaults, so the output length always matches the input.
        """
        if not items:
            return []

        prompt = self._build_batch_prompt(items)
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_batch_response(raw, len(items))
        except Exception as e:
            logger.warning(
                "Batch LLM estimation failed for %d items: %s. Falling back to formula defaults.",
                len(items), e,
            )
            parsed = [None] * len(items)

        results: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            est = parsed[i] if i < len(parsed) else None
            if est is None:
                est = self._fallback_estimates(
                    item.get("category", "code_quality"),
                    item.get("severity", "medium"),
                )
            results.append(est)
        return results

    def _build_batch_prompt(self, items: list[dict[str, Any]]) -> str:
        """Build a single prompt asking for estimates of every item in the batch."""
        lines: list[str] = []
        for idx, item in enumerate(items, start=1):
            snippet = (item.get("code_snippet") or "").strip()
            snippet_block = ""
            if len(snippet) > 10:
                # Keep batch snippets short to stay within token/rate limits.
                snippet_block = f"\n  Code: {snippet[:300].replace(chr(10), ' ')}"
            lines.append(
                f"[{idx}] File: {item.get('file_path', '')}; "
                f"Function/class: {item.get('function_name') or 'N/A'}; "
                f"Category: {item.get('category', '')}; "
                f"Severity: {item.get('severity', '')}; "
                f"Description: {item.get('description', '')}{snippet_block}"
            )
        items_block = "\n".join(lines)

        return f"""You are a senior software engineer estimating tech debt remediation effort.

Estimate the remediation effort for EACH of the {len(items)} debt items below.

Respond ONLY with a valid JSON array of exactly {len(items)} objects, in the SAME order
as the items. Do not add any prose. Each object must have this exact format:
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

Debt items:
{items_block}
"""

    def _parse_batch_response(
        self, raw: str, expected: int
    ) -> list[dict[str, Any] | None]:
        """Extract a JSON array of estimates; per-element None on parse failure."""
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in batch response")

        arr = json.loads(match.group())
        if not isinstance(arr, list):
            raise ValueError("Batch response is not a JSON array")

        results: list[dict[str, Any] | None] = []
        for element in arr:
            try:
                results.append(self._normalize_estimate(element))
            except Exception:
                results.append(None)
        return results

    @staticmethod
    def _fallback_estimates(category: str, severity: str) -> dict[str, Any]:
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