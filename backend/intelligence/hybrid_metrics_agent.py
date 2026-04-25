"""Bounded local-LLM calibration for core debt metrics."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from intelligence.local_llm_service import LocalLLMService


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class HybridMetricsAgent:
    """Apply bounded LLM-assisted calibration to deterministic core metrics."""

    MIN_MULTIPLIER = 0.85
    MAX_MULTIPLIER = 1.20
    MIN_SCORE_DELTA = -1.0
    MAX_SCORE_DELTA = 1.0

    def __init__(self, llm_service: LocalLLMService | None = None) -> None:
        self.llm_service = llm_service or LocalLLMService()

    async def calibrate(
        self,
        analysis: dict[str, Any],
        triage_items: list[dict[str, Any]],
        architecture_review: dict[str, Any],
        test_gap_review: dict[str, Any],
    ) -> dict[str, Any]:
        """Return normalized hybrid calibration instructions."""
        prompt = self._build_prompt(
            analysis,
            triage_items,
            architecture_review,
            test_gap_review,
        )
        parsed = await self.llm_service.invoke_json(prompt)
        if isinstance(parsed, dict):
            return self._normalize_calibration(parsed)
        return self._fallback_calibration()

    def apply(self, analysis: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
        """Apply bounded calibration to a copy of the analysis payload."""
        adjusted = deepcopy(analysis)

        cost_multiplier = _safe_float(calibration.get("cost_multiplier"), 1.0)
        hours_multiplier = _safe_float(calibration.get("hours_multiplier"), 1.0)
        score_delta = _safe_float(calibration.get("score_delta"), 0.0)
        category_adjustments = calibration.get("category_adjustments") or {}
        if not isinstance(category_adjustments, dict):
            category_adjustments = {}

        debt_items = adjusted.get("debt_items")
        if isinstance(debt_items, list):
            for item in debt_items:
                if not isinstance(item, dict):
                    continue
                category = str(item.get("category") or "code_quality").lower()
                category_multiplier = _safe_float(category_adjustments.get(category), 1.0)
                combined_cost_multiplier = _clamp(
                    cost_multiplier * category_multiplier, 0.75, 1.35
                )
                combined_hours_multiplier = _clamp(
                    hours_multiplier * category_multiplier, 0.75, 1.35
                )
                item["cost_usd"] = round(
                    _safe_float(item.get("cost_usd")) * combined_cost_multiplier, 2
                )
                if item.get("base_cost_usd") is not None:
                    item["base_cost_usd"] = round(
                        _safe_float(item.get("base_cost_usd")) * combined_cost_multiplier, 2
                    )
                if item.get("adjusted_minutes") is not None:
                    item["adjusted_minutes"] = round(
                        _safe_float(item.get("adjusted_minutes")) * combined_hours_multiplier, 2
                    )
                if item.get("base_minutes") is not None:
                    item["base_minutes"] = round(
                        _safe_float(item.get("base_minutes")) * combined_hours_multiplier, 2
                    )
                if item.get("remediation_hours") is not None:
                    item["remediation_hours"] = round(
                        _safe_float(item.get("remediation_hours")) * combined_hours_multiplier, 2
                    )

        findings = adjusted.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                category = str(finding.get("category") or "code_quality").lower()
                category_multiplier = _safe_float(category_adjustments.get(category), 1.0)
                combined_cost_multiplier = _clamp(
                    cost_multiplier * category_multiplier, 0.75, 1.35
                )
                combined_hours_multiplier = _clamp(
                    hours_multiplier * category_multiplier, 0.75, 1.35
                )
                finding["cost_usd"] = round(
                    _safe_float(finding.get("cost_usd")) * combined_cost_multiplier, 2
                )
                if finding.get("effort_hours") is not None:
                    finding["effort_hours"] = round(
                        _safe_float(finding.get("effort_hours")) * combined_hours_multiplier, 2
                    )

        cost_by_category = adjusted.get("cost_by_category")
        if isinstance(cost_by_category, dict):
            for category, values in cost_by_category.items():
                if not isinstance(values, dict):
                    continue
                category_multiplier = _safe_float(
                    category_adjustments.get(str(category).lower()), 1.0
                )
                values["cost_usd"] = round(
                    _safe_float(values.get("cost_usd"))
                    * _clamp(cost_multiplier * category_multiplier, 0.75, 1.35),
                    2,
                )
                if values.get("hours") is not None:
                    values["hours"] = round(
                        _safe_float(values.get("hours"))
                        * _clamp(hours_multiplier * category_multiplier, 0.75, 1.35),
                        2,
                    )

        module_summaries = adjusted.get("module_summaries")
        if isinstance(module_summaries, list):
            for module in module_summaries:
                if not isinstance(module, dict):
                    continue
                module["total_cost_usd"] = round(
                    _safe_float(module.get("total_cost_usd")) * cost_multiplier, 2
                )
                if module.get("total_effort_hours") is not None:
                    module["total_effort_hours"] = round(
                        _safe_float(module.get("total_effort_hours")) * hours_multiplier, 2
                    )

        roadmap = adjusted.get("roadmap")
        if isinstance(roadmap, dict):
            for items in roadmap.values():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    category = str(item.get("category") or "code_quality").lower()
                    category_multiplier = _safe_float(category_adjustments.get(category), 1.0)
                    item["cost_usd"] = round(
                        _safe_float(item.get("cost_usd"))
                        * _clamp(cost_multiplier * category_multiplier, 0.75, 1.35),
                        2,
                    )
                    if item.get("effort_hours") is not None:
                        item["effort_hours"] = round(
                            _safe_float(item.get("effort_hours"))
                            * _clamp(hours_multiplier * category_multiplier, 0.75, 1.35),
                            2,
                        )

        adjusted["total_cost_usd"] = round(
            _safe_float(adjusted.get("total_cost_usd")) * cost_multiplier,
            2,
        )
        adjusted["total_remediation_hours"] = round(
            _safe_float(adjusted.get("total_remediation_hours")) * hours_multiplier,
            2,
        )
        adjusted["total_remediation_sprints"] = round(
            _safe_float(adjusted.get("total_remediation_sprints")) * hours_multiplier,
            2,
        )
        adjusted["debt_score"] = round(
            _clamp(_safe_float(adjusted.get("debt_score")) + score_delta, 0.0, 10.0),
            2,
        )
        adjusted["hybrid_metrics"] = calibration
        return adjusted

    def _build_prompt(
        self,
        analysis: dict[str, Any],
        triage_items: list[dict[str, Any]],
        architecture_review: dict[str, Any],
        test_gap_review: dict[str, Any],
    ) -> str:
        """Create a strict JSON prompt for bounded metric calibration."""
        return (
            "You are calibrating technical debt metrics. "
            "Return ONLY a JSON object with keys: "
            "cost_multiplier, hours_multiplier, score_delta, category_adjustments, rationale, confidence. "
            "Rules: keep multipliers between 0.85 and 1.20, keep score_delta between -1.0 and 1.0, "
            "use only the supplied analysis and reviews, do not invent files or counts, "
            "and keep category_adjustments limited to the categories present in the analysis.\n\n"
            f"Analysis summary: total_cost={analysis.get('total_cost_usd')}, "
            f"total_hours={analysis.get('total_remediation_hours')}, "
            f"debt_score={analysis.get('debt_score')}, "
            f"categories={analysis.get('cost_by_category')}, "
            f"top_findings={analysis.get('findings', [])[:5]}, "
            f"top_modules={analysis.get('module_summaries', [])[:5]}\n"
            f"Semantic triage={triage_items}\n"
            f"Architecture review={architecture_review}\n"
            f"Test gap review={test_gap_review}"
        )

    def _normalize_calibration(self, calibration: dict[str, Any]) -> dict[str, Any]:
        """Clamp parsed calibration to safe bounded values."""
        raw_category_adjustments = calibration.get("category_adjustments") or {}
        category_adjustments: dict[str, float] = {}
        if isinstance(raw_category_adjustments, dict):
            for key, value in raw_category_adjustments.items():
                category_adjustments[str(key).lower()] = round(
                    _clamp(_safe_float(value, 1.0), self.MIN_MULTIPLIER, self.MAX_MULTIPLIER),
                    3,
                )

        return {
            "cost_multiplier": round(
                _clamp(
                    _safe_float(calibration.get("cost_multiplier"), 1.0),
                    self.MIN_MULTIPLIER,
                    self.MAX_MULTIPLIER,
                ),
                3,
            ),
            "hours_multiplier": round(
                _clamp(
                    _safe_float(calibration.get("hours_multiplier"), 1.0),
                    self.MIN_MULTIPLIER,
                    self.MAX_MULTIPLIER,
                ),
                3,
            ),
            "score_delta": round(
                _clamp(
                    _safe_float(calibration.get("score_delta"), 0.0),
                    self.MIN_SCORE_DELTA,
                    self.MAX_SCORE_DELTA,
                ),
                3,
            ),
            "category_adjustments": category_adjustments,
            "rationale": str(
                calibration.get("rationale")
                or "Bounded hybrid calibration based on local-LLM review."
            ),
            "confidence": str(calibration.get("confidence") or "medium").lower(),
        }

    def _fallback_calibration(self) -> dict[str, Any]:
        """Return a deterministic neutral calibration."""
        return {
            "cost_multiplier": 1.0,
            "hours_multiplier": 1.0,
            "score_delta": 0.0,
            "category_adjustments": {},
            "rationale": "Fallback deterministic calibration.",
            "confidence": "low",
        }
