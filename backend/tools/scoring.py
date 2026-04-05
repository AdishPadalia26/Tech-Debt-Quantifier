"""Shared scoring helpers for technical debt analysis."""

from typing import Any

from constants import (
    BUSINESS_IMPACT_WEIGHTS,
    CONFIDENCE_DEFAULTS,
    DEBT_SCORE_MAX,
    SEVERITY_RANK,
)


def severity_rank(severity: str) -> int:
    """Return numeric severity rank for stable comparisons."""
    return SEVERITY_RANK.get(str(severity).lower(), 0)


def max_severity(severities: list[str]) -> str:
    """Return the highest severity from a list."""
    if not severities:
        return "low"
    return max(severities, key=severity_rank)


def calculate_confidence(
    *,
    used_fallback: bool = False,
    has_git_history: bool = True,
    category: str = "static_analysis",
) -> float:
    """Estimate confidence for a finding based on evidence quality."""
    if used_fallback or not has_git_history:
        return CONFIDENCE_DEFAULTS["fallback"]
    return CONFIDENCE_DEFAULTS.get(category, CONFIDENCE_DEFAULTS["static_analysis"])


def classify_business_impact(
    *,
    severity: str,
    churn_multiplier: float = 1.0,
    change_count: int = 0,
) -> str:
    """Classify likely business impact from severity and maintenance pressure."""
    severity_value = severity_rank(severity)

    if severity_value >= SEVERITY_RANK["critical"] or churn_multiplier >= 2.2:
        return "critical"
    if severity_value >= SEVERITY_RANK["high"] or change_count >= 6:
        return "high"
    if severity_value >= SEVERITY_RANK["medium"] or change_count >= 3:
        return "medium"
    return "low"


def calculate_cost(
    *,
    effort_hours: float,
    hourly_rate: float,
    business_impact: str = "medium",
    confidence: float = 1.0,
) -> float:
    """Calculate a confidence-adjusted engineering cost."""
    impact_weight = BUSINESS_IMPACT_WEIGHTS.get(
        business_impact.lower(), BUSINESS_IMPACT_WEIGHTS["medium"]
    )
    bounded_confidence = max(0.25, min(confidence, 1.0))
    return round(effort_hours * hourly_rate * impact_weight * bounded_confidence, 2)


def aggregate_repo_score(
    *,
    total_cost: float,
    function_count: int,
    cisq_per_function: float,
) -> float:
    """Aggregate cost into the public 0-10 debt score."""
    if function_count <= 0 or cisq_per_function <= 0:
        return 0.0
    cost_per_function = total_cost / function_count
    return round(min(DEBT_SCORE_MAX, (cost_per_function / cisq_per_function) * 10), 2)


def build_finding_payload(
    *,
    file_path: str,
    category: str,
    severity: str,
    remediation_hours: float,
    hourly_rate: float,
    confidence: float,
    business_impact: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a normalized finding payload used across analyzers."""
    payload: dict[str, Any] = {
        "file": file_path,
        "category": category,
        "severity": severity,
        "remediation_hours": remediation_hours,
        "confidence": round(confidence, 2),
        "business_impact": business_impact,
        "cost_usd": calculate_cost(
            effort_hours=remediation_hours,
            hourly_rate=hourly_rate,
            business_impact=business_impact,
            confidence=confidence,
        ),
    }
    if extra:
        payload.update(extra)
    return payload
