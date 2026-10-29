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

ESTIMATION_SOURCE_LLM = "llm"
ESTIMATION_SOURCE_FALLBACK = "fallback"

# Errors that mean the LLM replied but the payload was unusable.
_PARSE_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    json.JSONDecodeError,
)


def _format_error(exc: BaseException) -> str:
    """Return ``"<ExceptionClass>: <first 200 chars of message>"``."""
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def _strip_reasoning(raw: str) -> str:
    """Drop code fences and reasoning-model ``<think>`` output before JSON parsing.

    Reasoning models (e.g. Nemotron) may omit the opening ``<think>`` tag, so
    everything up to the last ``</think>`` is discarded; an unclosed trailing
    ``<think>`` (truncated reasoning) is dropped too.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw)
    cleaned = cleaned.rsplit("</think>", 1)[-1]
    cleaned = re.sub(r"<think>.*\Z", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


class LLMEstimator:
    """Uses the configured LLM (via llm_factory) to produce realistic effort
    estimates for individual debt items.

    Every returned estimate carries ``estimation_source`` ("llm" | "fallback");
    fallback estimates also carry ``estimation_error``. The most recent error
    (or None after a success) is kept on ``last_error``.
    """

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm
        self.last_error: str | None = None

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
        """Ask the LLM to estimate realistic remediation effort.

        Returns:
            Estimate dict with ``estimation_source`` "llm", or a formula
            fallback with ``estimation_source`` "fallback" and
            ``estimation_error`` when the LLM call or parsing fails.
        """
        prompt = self._build_estimation_prompt(
            file_path, category, severity, description,
            code_snippet, function_name, language,
        )

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
        except Exception as e:  # noqa: BLE001 - provider SDKs raise many types
            error = _format_error(e)
            self.last_error = error
            logger.warning(
                "LLM call failed for %s (%s). Falling back to formula defaults.",
                file_path, error, exc_info=True,
            )
            return self._fallback_estimates(category, severity, error=error)

        raw = response.content if hasattr(response, "content") else str(response)
        try:
            estimate = self._parse_estimation_response(raw)
        except _PARSE_ERRORS as e:
            error = _format_error(e)
            self.last_error = error
            logger.warning(
                "Unparseable LLM estimate for %s (%s). Falling back to formula "
                "defaults.",
                file_path, error, exc_info=True,
            )
            return self._fallback_estimates(category, severity, error=error)

        self.last_error = None
        return estimate

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
        cleaned = _strip_reasoning(raw)
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
            "estimation_source": ESTIMATION_SOURCE_LLM,
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
        batch_error: str | None = None
        parsed: list[dict[str, Any] | None] = []
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
        except Exception as e:  # noqa: BLE001 - provider SDKs raise many types
            batch_error = _format_error(e)
            logger.warning(
                "Batch LLM call failed for %d items (%s). Falling back to formula "
                "defaults.",
                len(items), batch_error, exc_info=True,
            )
        else:
            raw = response.content if hasattr(response, "content") else str(response)
            try:
                parsed = self._parse_batch_response(raw, len(items))
            except _PARSE_ERRORS as e:
                batch_error = _format_error(e)
                logger.warning(
                    "Unparseable batch LLM response for %d items (%s). Falling "
                    "back to formula defaults.",
                    len(items), batch_error, exc_info=True,
                )

        results: list[dict[str, Any]] = []
        item_error: str | None = None
        for i, item in enumerate(items):
            est = parsed[i] if i < len(parsed) else None
            if est is None:
                item_error = batch_error or (
                    f"MissingEstimate: LLM returned no valid estimate for item {i + 1}"
                    f" of {len(items)}"
                )
                est = self._fallback_estimates(
                    item.get("category", "code_quality"),
                    item.get("severity", "medium"),
                    error=item_error,
                )
            results.append(est)
        self.last_error = batch_error or item_error
        return results

    def estimate_debt_items_batch_strict(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any] | None]:
        """Estimate a batch in ONE call, surfacing failures instead of hiding them.

        Unlike ``estimate_debt_items_batch`` this never substitutes fallbacks:
        the caller (``LLMPool``) decides how to retry/fail over.

        Args:
            items: Debt item input dicts (same shape as the non-strict method).

        Returns:
            One entry per input, in order: a normalized estimate, or None when
            the LLM omitted or mangled that element.

        Raises:
            Exception: Whatever the provider SDK raises (rate limit, timeout,
                HTTP error), or ``ValueError``/``json.JSONDecodeError`` when
                the whole reply is unparseable.
        """
        if not items:
            return []
        response = self.llm.invoke(
            [HumanMessage(content=self._build_batch_prompt(items))]
        )
        raw = response.content if hasattr(response, "content") else str(response)
        if not isinstance(raw, str):
            raw = str(raw)
        parsed = self._parse_batch_response(raw, len(items))
        padded: list[dict[str, Any] | None] = list(parsed[: len(items)])
        padded.extend([None] * (len(items) - len(padded)))
        # Routers (OpenRouter) may serve a different model than requested;
        # report the one that actually answered.
        metadata = getattr(response, "response_metadata", None)
        used_model = None
        if isinstance(metadata, dict):
            used_model = metadata.get("model_name") or metadata.get("model")
        if used_model:
            for est in padded:
                if est is not None:
                    est["estimation_model"] = str(used_model)
        return padded

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
        cleaned = _strip_reasoning(raw)
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
            except _PARSE_ERRORS:
                logger.debug("Dropping malformed batch element", exc_info=True)
                results.append(None)
        return results

    @staticmethod
    def _fallback_estimates(
        category: str, severity: str, error: str | None = None
    ) -> dict[str, Any]:
        """Formula-only fallback when LLM is unavailable.

        Hours depend on category only; severity is NOT applied here (it is
        applied once downstream by the cost formula). Severity still drives
        ``severity_score`` / ``business_risk_score``.

        Args:
            category: Debt category.
            severity: Debt severity (critical/high/medium/low).
            error: Why the LLM estimate was unavailable, if known.

        Returns:
            Estimate dict with ``estimation_source`` "fallback" and
            ``estimation_error`` (str; "LLM not configured" when unknown).
        """
        base_hours: dict[str, float] = {
            "security": 4.0, "code_quality": 1.5, "documentation": 0.5,
            "test_debt": 2.0, "dependency": 1.0, "architecture": 3.0,
            "reliability": 2.0, "performance": 1.5, "duplication": 1.0,
            "dead_code": 0.5,
        }
        severity_scores: dict[str, int] = {
            "critical": 9, "high": 7, "medium": 5, "low": 3,
        }
        risk_scores: dict[str, int] = {
            "critical": 8, "high": 6, "medium": 4, "low": 2,
        }

        cat_key = (category or "code_quality").lower().replace(" ", "_")
        sev_key = (severity or "medium").lower()
        hours = base_hours.get(cat_key, 1.5)

        return {
            "realistic_hours": hours,
            "severity_score": severity_scores.get(sev_key, 5),
            "business_risk_score": risk_scores.get(sev_key, 4),
            "fix_complexity_score": 5,
            "confidence": "low",
            "primary_risk": f"Unresolved {category} debt may increase future costs.",
            "fix_summary": f"Standard {category} remediation required.",
            "cost_rationale": (
                f"Estimated using category defaults: {hours:.1f}h for {cat_key} "
                f"(severity {sev_key} applied downstream)."
            ),
            "estimation_source": ESTIMATION_SOURCE_FALLBACK,
            "estimation_error": error or "LLM not configured",
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
        except _PARSE_ERRORS as e:
            result = self._fallback_estimates(
                category, severity, error=_format_error(e)
            )
            result["source"] = "fallback"
            return result