"""Analysis result normalization helpers."""

from __future__ import annotations

from typing import Any


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def normalize_analysis_result(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure analysis results always match the frontend's expected shape."""
    payload = raw if isinstance(raw, dict) else {}

    debt_items = payload.get("debt_items") or []
    if not isinstance(debt_items, list):
        debt_items = []

    normalized_items: list[dict[str, Any]] = []
    for item in debt_items:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "file": str(item.get("file") or "unknown"),
                "category": str(item.get("category") or "code_quality"),
                "severity": str(item.get("severity") or "medium").lower(),
                "cost_usd": _safe_float(item.get("cost_usd")),
                "base_cost_usd": _safe_float(item.get("base_cost_usd")),
                "base_minutes": _safe_float(item.get("base_minutes")),
                "adjusted_minutes": _safe_float(item.get("adjusted_minutes")),
                "hourly_rate": _safe_float(item.get("hourly_rate"), 85.0),
                "combined_multiplier": _safe_float(item.get("combined_multiplier"), 1.0),
                "complexity": item.get("complexity"),
                "function": item.get("function"),
                "cost_factors": item.get("cost_factors") or [],
                "cost_explanation": item.get("cost_explanation") or "",
                "estimation_confidence": item.get("estimation_confidence") or "",
                "severity_score": item.get("severity_score"),
                "business_risk_score": item.get("business_risk_score"),
                "fix_complexity_score": item.get("fix_complexity_score"),
                "primary_risk": item.get("primary_risk") or "",
                "fix_summary": item.get("fix_summary") or "",
                "hours_by_level": item.get("hours_by_level") or {
                    "junior": 0.0,
                    "mid": 0.0,
                    "senior": 0.0,
                },
            }
        )

    raw_cats = payload.get("cost_by_category") or {}
    if not isinstance(raw_cats, dict):
        raw_cats = {}

    normalized_cats: dict[str, dict[str, Any]] = {}
    for key, value in raw_cats.items():
        if isinstance(value, dict):
            normalized_cats[key] = {
                "cost_usd": _safe_float(value.get("cost_usd")),
                "count": _safe_int(value.get("count") or value.get("item_count")),
                "hours": _safe_float(value.get("hours")),
                "item_count": _safe_int(value.get("item_count") or value.get("count")),
            }
        elif isinstance(value, (int, float)):
            normalized_cats[key] = {
                "cost_usd": float(value),
                "count": 0,
                "hours": 0.0,
                "item_count": 0,
            }

    total_cost = _safe_float(payload.get("total_cost_usd"))
    if total_cost == 0 and normalized_items:
        total_cost = sum(item["cost_usd"] for item in normalized_items)

    total_hours = _safe_float(payload.get("total_remediation_hours"))
    if total_hours == 0 and normalized_items:
        total_hours = sum(item["adjusted_minutes"] for item in normalized_items) / 60

    return {
        **payload,
        "debt_score": _safe_float(payload.get("debt_score")),
        "total_cost_usd": total_cost,
        "total_remediation_hours": total_hours,
        "total_remediation_sprints": _safe_float(payload.get("total_remediation_sprints")),
        "debt_items": normalized_items,
        "cost_by_category": normalized_cats,
        "executive_summary": str(payload.get("executive_summary") or ""),
        "recommendations": payload.get("recommendations") or [],
        "priority_actions": payload.get("priority_actions") or [],
        "roi_analysis": payload.get("roi_analysis") or {},
        "repo_profile": payload.get("repo_profile") or {},
        "hourly_rates": payload.get("hourly_rates") or {},
        "sanity_check": payload.get("sanity_check") or {},
        "data_sources_used": payload.get("data_sources_used") or [],
        "findings": payload.get("findings") if isinstance(payload.get("findings"), list) else [],
        "module_summaries": (
            payload.get("module_summaries")
            if isinstance(payload.get("module_summaries"), list)
            else []
        ),
        "roadmap": payload.get("roadmap") if isinstance(payload.get("roadmap"), dict) else {},
        "estimation_method": payload.get("estimation_method") or "formula_only",
        "llm_model": payload.get("llm_model"),
        "items_estimated_by_llm": _safe_int(payload.get("items_estimated_by_llm")),
        "items_estimated_by_formula": _safe_int(payload.get("items_estimated_by_formula")),
        "total_hours_by_level": payload.get("total_hours_by_level") or {
            "junior": 0.0,
            "mid": 0.0,
            "senior": 0.0,
        },
    }
