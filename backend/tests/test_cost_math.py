"""Cost math tests: reconciliation, single application of factors, scoping.

All inputs are synthetic; no network or real LLM is used.
"""
from typing import Any

import pytest

from tools.cost_estimator import CostEstimator
from tools.llm_estimator import LLMEstimator
from tools.scoring import calculate_cost, cost_range_for

RATE = 100.0


@pytest.fixture
def estimator(monkeypatch: pytest.MonkeyPatch) -> CostEstimator:
    """CostEstimator with hybrid LLM disabled (no LLM construction)."""
    monkeypatch.setenv("HYBRID_ESTIMATION_ENABLED", "false")
    return CostEstimator()


def _llm_result(
    hours: float = 2.0, sev_score: int = 5, confidence: str = "high",
    source: str = "llm",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "realistic_hours": hours,
        "severity_score": sev_score,
        "business_risk_score": 5,
        "fix_complexity_score": 5,
        "confidence": confidence,
        "estimation_source": source,
    }
    if source == "fallback":
        result["estimation_error"] = "LLM not configured"
    return result


def _item(file: str = "src/app.py", cost: float = 100.0, hours: float = 1.0,
          category: str = "code_quality", **extra: Any) -> dict[str, Any]:
    return {"file": file, "category": category, "cost_usd": cost,
            "remediation_hours": hours, "severity": "medium", **extra}


def test_reconciliation_categories_hours_total(estimator: CostEstimator) -> None:
    items = [
        _item("a.py", 123.45, 1.23, "code_quality"),
        _item("b.py", 200.11, 2.01, "security"),
        _item("c.py", 50.5, 0.5, "documentation"),
        _item("d.py", 77.77, 0.77, "dependency"),
    ]
    estimator.tag_principal(items)
    totals = estimator._aggregate_costs(items, 2.7)
    cat_cost = sum(c["cost_usd"] for c in totals["cost_by_category"].values())
    cat_hours = sum(c["hours"] for c in totals["cost_by_category"].values())
    assert abs(cat_cost - totals["total_cost_usd"]) < 1
    assert abs(cat_hours - totals["total_remediation_hours"]) <= 0.1
    assert totals["total_cost_range"]["p50"] == totals["total_cost_usd"]


def test_repo_factor_applied_once(estimator: CostEstimator) -> None:
    items = [_item("a.py", 100.0, 1.0), _item("b.py", 300.0, 3.0, "security")]
    estimator.tag_principal(items)
    one = estimator._aggregate_costs(items, 1.0)
    two = estimator._aggregate_costs(items, 2.0)
    assert one["total_cost_usd"] == pytest.approx(400.0)
    assert two["total_cost_usd"] == pytest.approx(2 * one["total_cost_usd"])
    assert two["total_remediation_hours"] == pytest.approx(
        2 * one["total_remediation_hours"], abs=0.01
    )
    # Items themselves are not scaled by the repo factor.
    assert items[0]["cost_usd"] == 100.0


def test_apply_formula_has_no_repo_multiplier(estimator: CostEstimator) -> None:
    out = estimator._apply_formula(_item(), _llm_result(2.0, 5), {}, RATE)
    assert "repo_multiplier" not in out
    assert out["cost_usd"] == pytest.approx(2.0 * RATE)
    assert out["combined_multiplier"] == pytest.approx(1.0)


def test_lower_confidence_keeps_p50_widens_range() -> None:
    high = cost_range_for(1000.0, 0.9)
    low = cost_range_for(1000.0, 0.3)
    assert high["p50"] == low["p50"] == 1000.0
    assert (low["p90"] - low["p10"]) > (high["p90"] - high["p10"])
    assert calculate_cost(effort_hours=10, hourly_rate=100, confidence=0.1) == \
        calculate_cost(effort_hours=10, hourly_rate=100, confidence=1.0)


def test_cost_range_formula() -> None:
    rng = cost_range_for(100.0, 0.5)
    assert rng == {"p10": 50.0, "p50": 100.0, "p90": 200.0}
    clamped = cost_range_for(100.0, 0.0)  # w clamps to 0.75
    assert clamped["p10"] == 25.0 and clamped["p90"] == 250.0


def test_severity_applied_once(estimator: CostEstimator) -> None:
    crit = estimator._apply_formula(_item(), _llm_result(2.0, 9), {}, RATE)
    low = estimator._apply_formula(_item(), _llm_result(2.0, 3), {}, RATE)
    expected = (1.0 + (9 - 5) * 0.08) / (1.0 + (3 - 5) * 0.08)
    assert crit["cost_usd"] / low["cost_usd"] == pytest.approx(expected, rel=1e-3)


def test_fallback_hours_do_not_include_severity() -> None:
    crit = LLMEstimator._fallback_estimates("code_quality", "critical")
    low = LLMEstimator._fallback_estimates("code_quality", "low")
    assert crit["realistic_hours"] == low["realistic_hours"]


def test_non_principal_excluded_and_counted(estimator: CostEstimator) -> None:
    items = [
        _item("src/app.py", 100.0, 1.0),
        _item("docs_src/tutorial.py", 40.0, 0.4),
        _item("tests/test_app.py", 60.0, 0.6),
    ]
    estimator.tag_principal(items)
    assert [i["principal"] for i in items] == [True, False, False]
    totals = estimator._aggregate_costs(items, 2.0)
    assert totals["total_cost_usd"] == pytest.approx(200.0)
    assert totals["cost_by_category"]["code_quality"]["item_count"] == 1
    assert totals["non_principal_cost"]["docs"] == pytest.approx(80.0)
    assert totals["non_principal_cost"]["test"] == pytest.approx(120.0)
    assert totals["non_principal_cost"]["example"] == 0.0
    assert totals["non_principal_cost"]["generated"] == 0.0


def test_degenerate_analysis_raises(estimator: CostEstimator) -> None:
    with pytest.raises(ValueError, match="Degenerate analysis"):
        estimator._check_degenerate(files_scanned=50, functions_analyzed=0)
    assert "Low function count" in estimator._check_degenerate(
        files_scanned=50, functions_analyzed=10
    )
    assert estimator._check_degenerate(files_scanned=50, functions_analyzed=500) is None
    assert estimator._check_degenerate(files_scanned=10, functions_analyzed=0) is None


def test_no_ai_premium_in_source() -> None:
    import inspect

    import tools.cost_estimator as module

    source = inspect.getsource(module)
    assert "ai_premium" not in source
    assert "1.5 if" not in source


class _StubLLM:
    """Stub estimator returning fixed fallback/llm results per item."""

    last_error = None

    def __init__(self, source: str = "llm") -> None:
        self.source = source

    def estimate_debt_items_batch(self, inputs: list[dict[str, Any]]) -> list[dict]:
        return [
            _llm_result(10.0, 9, "low" if self.source == "fallback" else "high",
                        self.source)
            for _ in inputs
        ]


def test_hybrid_does_not_overwrite_security_cost(estimator: CostEstimator) -> None:
    estimator.llm_estimator = _StubLLM("llm")  # type: ignore[assignment]
    security = _item("src/auth.py", 777.0, 4.0, "security", type="security_hotspot")
    osv = _item("requirements.txt", 321.0, 2.0, "dependency", type="vulnerability")
    plain = _item("src/app.py", 100.0, 1.0)
    out = estimator._estimate_all_items([security, osv, plain], {}, RATE)
    assert out[0]["cost_usd"] == 777.0
    assert out[0]["remediation_hours"] == 4.0
    assert out[0]["llm_hours"] == 10.0
    assert out[0]["estimation_source"] == "llm"
    assert out[1]["cost_usd"] == 321.0
    assert out[2]["cost_usd"] != 100.0  # formula item is recomputed


def test_fallback_ratio_warning(estimator: CostEstimator) -> None:
    estimator.llm_estimator = _StubLLM("fallback")  # type: ignore[assignment]
    items = estimator._estimate_all_items(
        [_item(f"f{i}.py") for i in range(5)], {}, RATE
    )
    stats = estimator._estimation_stats(items)
    assert stats["fallback"] == 5 and stats["llm"] == 0
    assert stats["fallback_ratio"] == 1.0
    assert stats["llm_error"] == "LLM not configured"
    warnings = estimator._build_warnings(stats, {"live": True}, {"live": True})
    assert len(warnings) == 1
    assert "5 of 5" in warnings[0] and "LLM not configured" in warnings[0]


def test_no_warning_when_llm_healthy(estimator: CostEstimator) -> None:
    estimator.llm_estimator = _StubLLM("llm")  # type: ignore[assignment]
    items = estimator._estimate_all_items([_item("a.py"), _item("b.py")], {}, RATE)
    stats = estimator._estimation_stats(items)
    assert stats["fallback_ratio"] == 0.0
    assert estimator._build_warnings(stats, {"live": True}, {"live": True}) == []


def test_live_false_warns(estimator: CostEstimator) -> None:
    stats = estimator._estimation_stats([])
    warnings = estimator._build_warnings(stats, {"live": False}, {"live": False})
    assert "Rates from reference table (live lookup failed)" in warnings
    assert any("Benchmarks" in w for w in warnings)


def test_waterfall_sums_to_total(estimator: CostEstimator) -> None:
    items = [
        estimator._apply_formula(_item("a.py"), _llm_result(2.0, 9), {"a.py": 12}, RATE),
        estimator._apply_formula(_item("b.py"), _llm_result(3.0, 3), {"b.py": 3}, RATE),
        _item("c.py", 55.5, 0.5, "security", type="security_hotspot"),
    ]
    estimator.tag_principal(items)
    wf = estimator._aggregate_costs(items, 2.3)["waterfall"]
    parts = wf["base"] + wf["churn"] + wf["severity"] + wf["repo"]
    assert parts == pytest.approx(wf["total"], abs=0.02)
    assert wf["repo"] > 0 and wf["churn"] > 0
