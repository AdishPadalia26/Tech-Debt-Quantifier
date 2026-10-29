"""Shared scoring helpers for technical debt analysis."""

import math
from typing import Any

from constants import (
    BUSINESS_IMPACT_WEIGHTS,
    CONFIDENCE_DEFAULTS,
    DEBT_SCORE_LOG_SLOPE,
    DEBT_SCORE_MAX,
    DEBT_SCORE_MIDPOINT,
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


def cost_range_for(p50: float, confidence: float) -> dict[str, float]:
    """Build a cost range around a point estimate from its confidence.

    Lower confidence widens the range; the median (p50) never moves.
    Width ``w = clamp(1 - confidence, 0.1, 0.75)``; ``p10 = p50 * (1 - w)``
    and ``p90 = p50 * (1 + 2w)``.

    Args:
        p50: Point (median) cost estimate in USD.
        confidence: Evidence confidence in 0..1.

    Returns:
        Dict with p10, p50 and p90 in USD.
    """
    width = max(0.1, min(0.75, 1.0 - confidence))
    return {
        "p10": round(p50 * (1.0 - width), 2),
        "p50": round(p50, 2),
        "p90": round(p50 * (1.0 + 2.0 * width), 2),
    }


def calculate_cost(
    *,
    effort_hours: float,
    hourly_rate: float,
    business_impact: str = "medium",
    confidence: float = 1.0,
) -> float:
    """Calculate an engineering cost.

    ``confidence`` does not change the cost (a low-confidence estimate is not a
    cheaper one); it only widens the range via ``cost_range_for``. The
    parameter is kept for call-site compatibility.
    """
    del confidence
    impact_weight = BUSINESS_IMPACT_WEIGHTS.get(
        business_impact.lower(), BUSINESS_IMPACT_WEIGHTS["medium"]
    )
    return round(effort_hours * hourly_rate * impact_weight, 2)


def aggregate_repo_score(
    *,
    total_cost: float,
    function_count: int,
    cisq_per_function: float,
    files_scanned: int = 0,
    doc_function_floor: int = 0,
) -> float:
    """Aggregate cost into a 0-10 debt health grade (higher = more debt).

    The score is a log-scaled comparison of the repo's debt density against the
    industry-average benchmark, anchored so that a repo at the industry-average
    density scores ``DEBT_SCORE_MIDPOINT`` and every 10x change in density moves
    the score by ``DEBT_SCORE_LOG_SLOPE`` points. Log scaling stretches the
    crowded "healthy repo" band (well below the industry average) across 1-4
    instead of compressing every well-run codebase into 0-1, which is what a
    linear (density / benchmark) * 10 mapping did.

    Density is cost per function. The denominator must match the scope of the
    cost numerator, so callers pass the full-repo function estimate
    (``functions_estimated_total``). ``files_scanned`` and
    ``doc_function_floor`` are retained for compatibility and unused.
    """
    if cisq_per_function <= 0:
        return 0.0
    effective_count = max(function_count, 1)
    cost_per_function = total_cost / effective_count
    if cost_per_function <= 0:
        return 0.0
    density_ratio = cost_per_function / cisq_per_function
    score = DEBT_SCORE_MIDPOINT + DEBT_SCORE_LOG_SLOPE * math.log10(density_ratio)
    return round(max(0.0, min(DEBT_SCORE_MAX, score)), 2)


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
    cost_usd = calculate_cost(
        effort_hours=remediation_hours,
        hourly_rate=hourly_rate,
        business_impact=business_impact,
    )
    payload: dict[str, Any] = {
        "file": file_path,
        "category": category,
        "severity": severity,
        "remediation_hours": remediation_hours,
        "confidence": round(confidence, 2),
        "business_impact": business_impact,
        "cost_usd": cost_usd,
        "cost_range": cost_range_for(cost_usd, confidence),
    }
    if extra:
        payload.update(extra)
    return payload
