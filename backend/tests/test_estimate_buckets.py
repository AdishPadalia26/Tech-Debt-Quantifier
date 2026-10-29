"""Bucket estimation tests: keys, buckets, scaling, estimator integration.

All inputs are synthetic; no network or real LLM is used.
"""
import random
from typing import Any

import pytest

from tools.cost_estimator import CostEstimator
from tools.estimate_buckets import (
    SCALE_MAX,
    SCALE_MIN,
    build_buckets,
    bucket_key,
    magnitude,
    scale_factor,
    size_bucket,
)

RATE = 100.0


def _item(
    file: str = "pkg/a.py",
    category: str = "code_quality",
    severity: str = "medium",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "file": file, "category": category, "severity": severity,
        "cost_usd": 50.0, "remediation_hours": 1.0, **extra,
    }


class FakePool:
    """Instant fake LLMPool recording the inputs it was given."""

    providers = ["fake"]

    def __init__(self, fail: bool = False, hours: float = 2.0) -> None:
        self.fail = fail
        self.hours = hours
        self.inputs: list[dict[str, Any]] = []

    def estimate_items(
        self, inputs: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.inputs = list(inputs)
        results: list[dict[str, Any]] = []
        for _ in inputs:
            if self.fail:
                results.append({
                    "realistic_hours": 1.5, "severity_score": 5,
                    "business_risk_score": 4, "fix_complexity_score": 5,
                    "confidence": "low", "estimation_source": "fallback",
                    "estimation_error": "boom: pool down",
                })
            else:
                results.append({
                    "realistic_hours": self.hours, "severity_score": 5,
                    "business_risk_score": 5, "fix_complexity_score": 5,
                    "confidence": "high", "estimation_source": "llm",
                    "estimation_provider": "fake", "estimation_model": "m1",
                    "cached": True,
                })
        return results, {"per_provider": {}, "cache_hits": 0, "elapsed_s": 0.0}


@pytest.fixture
def estimator(monkeypatch: pytest.MonkeyPatch) -> CostEstimator:
    """CostEstimator with hybrid disabled; tests inject a fake pool."""
    monkeypatch.setenv("HYBRID_ESTIMATION_ENABLED", "false")
    est = CostEstimator()
    est._bucketing_enabled = True
    est._max_buckets = 400
    return est


def _use_pool(est: CostEstimator, pool: FakePool) -> FakePool:
    est._pool_factory = lambda: pool
    return pool


# ---------------------------------------------------------------- keys


def test_bucket_key_deterministic_and_discriminating() -> None:
    a = _item(type="complexity_hotspot", complexity=12)
    assert bucket_key(a) == bucket_key(dict(a))
    assert bucket_key(a) == "code_quality|medium|python|complexity_hotspot|11-20"
    assert bucket_key(_item(type="complexity_hotspot", complexity=30)) != bucket_key(a)
    assert bucket_key(_item(severity="high", type="complexity_hotspot", complexity=12)) != bucket_key(a)
    assert bucket_key(_item("x.js", type="complexity_hotspot", complexity=12)) != bucket_key(a)


def test_bucket_key_rule_id_and_missing_metric() -> None:
    b101 = _item(category="security", type="security_hotspot", bandit_test_id="B101")
    b102 = _item(category="security", type="security_hotspot", bandit_test_id="B102")
    assert bucket_key(b101).endswith("security_hotspot:B101|na")
    assert bucket_key(b101) != bucket_key(b102)
    assert bucket_key(_item(type="missing_docstring")).endswith("|na")


@pytest.mark.parametrize(
    "value,label",
    [(None, "na"), (0, "1-2"), (1, "1-2"), (2, "1-2"), (3, "3-5"), (5, "3-5"),
     (6, "6-10"), (10, "6-10"), (11, "11-20"), (20, "11-20"), (21, "21-50"),
     (50, "21-50"), (51, "51+"), (5000, "51+")],
)
def test_size_bucket_edges(value: float | None, label: str) -> None:
    assert size_bucket(value) == label


def test_magnitude_fields() -> None:
    assert magnitude({"complexity": 7}) == 7.0
    assert magnitude({"line_count": 900}) == 900.0
    assert magnitude({"cycle": ["a", "b", "c"]}) == 3.0
    assert magnitude({"complexity": True}) is None
    assert magnitude({}) is None


# ------------------------------------------------------------- buckets


def _synthetic(n: int, seed: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    kinds = ["missing_docstring", "complexity_hotspot", "duplicate_logic",
             "unused_private_function", "nested_loop", "missing_tests"]
    out = []
    for i in range(n):
        kind = rng.choice(kinds)
        extra: dict[str, Any] = {"type": kind, "function": f"f{i}"}
        if kind == "complexity_hotspot":
            extra["complexity"] = rng.randint(1, 80)
        elif kind == "duplicate_logic":
            extra["statement_count"] = rng.randint(2, 60)
        out.append(_item(
            f"pkg/m{rng.randint(0, 300)}{rng.choice(['.py', '.js', '.go'])}",
            rng.choice(["code_quality", "documentation", "test_debt"]),
            rng.choice(["low", "medium", "high"]),
            **extra,
        ))
    return out


def test_build_buckets_deterministic_and_complete() -> None:
    items = _synthetic(300)
    first = build_buckets(items, 400)
    second = build_buckets(list(items), 400)
    assert [(b.key, b.members, b.representative) for b in first] == [
        (b.key, b.members, b.representative) for b in second
    ]
    covered = sorted(m for b in first for m in b.members)
    assert covered == list(range(300))
    for b in first:
        assert b.representative in b.members
        assert len({bucket_key(items[m]) for m in b.members}) == 1


def test_build_buckets_empty() -> None:
    assert build_buckets([], 10) == []


@pytest.mark.parametrize("max_buckets", [1, 2, 5, 12, 40, 100])
def test_coarsening_respects_max_buckets(max_buckets: int) -> None:
    items = _synthetic(1000)
    buckets = build_buckets(items, max_buckets)
    assert 1 <= len(buckets) <= max_buckets
    assert sorted(m for b in buckets for m in b.members) == list(range(1000))


def test_coarsening_drops_language_first() -> None:
    items = [
        _item("a.py", type="missing_docstring"),
        _item("a.js", type="missing_docstring"),
        _item("a.go", type="missing_docstring"),
    ]
    assert len(build_buckets(items, 3)) == 3
    merged = build_buckets(items, 1)
    assert len(merged) == 1 and merged[0].members == [0, 1, 2]


def test_coarsening_merges_adjacent_sizes_before_issue() -> None:
    items = [_item(type="complexity_hotspot", complexity=c) for c in (2, 4, 8, 15)]
    assert len(build_buckets(items, 4)) == 4
    two = build_buckets(items, 2)
    assert len(two) == 2
    assert {b.key.split("|")[3] for b in two} == {"complexity_hotspot"}


def test_representative_is_median_member() -> None:
    items = [_item(type="complexity_hotspot", complexity=c) for c in (11, 12, 13, 19, 20)]
    (bucket,) = build_buckets(items, 5)
    assert bucket.members == [0, 1, 2, 3, 4]
    assert bucket.representative == 2  # complexity 13 == median


def test_representative_tie_prefers_lowest_index() -> None:
    items = [_item(type="complexity_hotspot", complexity=c) for c in (11, 13)]
    (bucket,) = build_buckets(items, 5)
    assert bucket.representative == 0  # median 12; both 1 away


def test_representative_without_metric_is_first() -> None:
    items = [_item(type="missing_docstring") for _ in range(4)]
    (bucket,) = build_buckets(items, 5)
    assert bucket.representative == 0


def test_scale_factor_ratio_clamp_and_missing() -> None:
    rep = _item(complexity=10)
    assert scale_factor(_item(complexity=15), rep) == pytest.approx(1.5)
    assert scale_factor(_item(complexity=1000), rep) == SCALE_MAX
    assert scale_factor(_item(complexity=1), rep) == SCALE_MIN
    assert scale_factor(_item(), rep) == 1.0
    assert scale_factor(_item(complexity=3), _item()) == 1.0
    assert scale_factor(_item(complexity=3), _item(complexity=0)) == 1.0


# ------------------------------------------------- estimator integration


def test_thousand_items_collapse_to_max_buckets(estimator: CostEstimator) -> None:
    estimator._max_buckets = 25
    pool = _use_pool(estimator, FakePool())
    items = _synthetic(1000)
    out = estimator._estimate_all_items(items, {}, RATE)
    assert len(out) == 1000
    assert 0 < len(pool.inputs) <= 25
    stats = estimator._estimation_stats(out)
    assert stats["llm_calls_items"] == len(pool.inputs)
    assert stats["buckets"] <= 25
    assert stats["items_via_bucket"] + (stats["llm_calls_items"] - stats["buckets"]) == 1000
    assert stats["llm"] == 1000 and stats["fallback"] == 0
    assert [o["file"] for o in out] == [i["file"] for i in items]


def test_members_inherit_rep_source_provider_and_scale(
    estimator: CostEstimator,
) -> None:
    pool = _use_pool(estimator, FakePool(hours=2.0))
    items = [
        _item(type="complexity_hotspot", function=f"f{c}", complexity=c)
        for c in (11, 13, 20)
    ]
    out = estimator._estimate_all_items(items, {}, RATE)
    assert len(pool.inputs) == 1
    rep_label = "pkg/a.py:f13"
    for o in out:
        assert o["estimation_method"] == "bucket"
        assert o["bucket_size"] == 3
        assert o["bucket_representative"] == rep_label
        assert o["estimation_source"] == "llm"
        assert o["estimation_provider"] == "fake"
        assert o["estimation_model"] == "m1"
        assert o["cached"] is True
        assert o["bucket_id"] == bucket_key(items[0])
    assert out[1]["bucket_scale"] == 1.0
    assert out[0]["bucket_scale"] == pytest.approx(11 / 13, abs=1e-3)
    assert out[2]["bucket_scale"] == pytest.approx(20 / 13, abs=1e-3)
    assert out[1]["base_hours"] == 2.0
    assert out[2]["base_hours"] == pytest.approx(2.0 * 20 / 13, abs=0.01)


def test_rep_fallback_makes_members_fallback_with_error(
    estimator: CostEstimator,
) -> None:
    _use_pool(estimator, FakePool(fail=True))
    items = [_item(f"f{i}.py", type="missing_docstring") for i in range(6)]
    out = estimator._estimate_all_items(items, {}, RATE)
    assert all(o["estimation_source"] == "fallback" for o in out)
    assert all(o["estimation_error"] == "boom: pool down" for o in out)
    assert not any("estimation_provider" in o for o in out)
    stats = estimator._estimation_stats(out)
    assert stats["fallback"] == 6 and stats["llm"] == 0 and stats["total"] == 6
    assert stats["llm_error"] == "boom: pool down"
    assert stats["llm_calls_items"] == 1


def test_security_and_osv_items_not_bucketed(estimator: CostEstimator) -> None:
    pool = _use_pool(estimator, FakePool())
    sec = [
        _item(f"s{i}.py", "security", "high", type="security_hotspot",
              bandit_test_id="B101", cost_usd=700.0)
        for i in range(5)
    ]
    osv = [
        _item("requirements.txt", "dependency", "high", type="vulnerability",
              cost_usd=300.0)
        for _ in range(3)
    ]
    plain = [_item(f"p{i}.py", type="missing_docstring") for i in range(10)]
    out = estimator._estimate_all_items(plain[:5] + sec + osv + plain[5:], {}, RATE)
    assert len(pool.inputs) == 5 + 3 + 1
    fixed = [o for o in out if o.get("type") in ("security_hotspot", "vulnerability")]
    assert len(fixed) == 8
    assert all(o["estimation_method"] == "individual" for o in fixed)
    assert all("bucket_id" not in o for o in fixed)
    assert {o["cost_usd"] for o in fixed} == {700.0, 300.0}
    docs = [o for o in out if o.get("type") == "missing_docstring"]
    assert all(o["estimation_method"] == "bucket" and o["bucket_size"] == 10 for o in docs)


def test_bucketing_disabled_sends_everything(estimator: CostEstimator) -> None:
    estimator._bucketing_enabled = False
    pool = _use_pool(estimator, FakePool())
    items = [_item(f"f{i}.py", type="missing_docstring") for i in range(8)]
    out = estimator._estimate_all_items(items, {}, RATE)
    assert len(pool.inputs) == 8
    assert all(o["estimation_method"] == "individual" for o in out)
    stats = estimator._estimation_stats(out)
    assert stats["buckets"] == 0 and stats["items_via_bucket"] == 0
    assert stats["llm_calls_items"] == 8


def test_singleton_bucket_is_individual(estimator: CostEstimator) -> None:
    _use_pool(estimator, FakePool())
    out = estimator._estimate_all_items(
        [_item(type="missing_docstring"), _item(type="nested_loop")], {}, RATE
    )
    assert all(o["estimation_method"] == "individual" for o in out)


def test_single_llm_path_is_bucketed(estimator: CostEstimator) -> None:
    class Stub:
        last_error = None
        seen = 0

        def estimate_debt_items_batch(self, inputs: list[dict[str, Any]]) -> list[dict]:
            Stub.seen += len(inputs)
            return [{
                "realistic_hours": 3.0, "severity_score": 5,
                "business_risk_score": 5, "fix_complexity_score": 5,
                "confidence": "high", "estimation_source": "llm",
            } for _ in inputs]

    estimator.llm_estimator = Stub()  # type: ignore[assignment]
    items = [_item(f"f{i}.py", type="missing_docstring") for i in range(30)]
    out = estimator._estimate_all_items(items, {}, RATE)
    assert Stub.seen == 1
    assert len(out) == 30
    assert all(o["estimation_source"] == "llm" and o["base_hours"] == 3.0 for o in out)


def test_severity_and_churn_applied_per_member(estimator: CostEstimator) -> None:
    _use_pool(estimator, FakePool(hours=2.0))
    items = [_item("hot.py", type="missing_docstring"),
             _item("cold.py", type="missing_docstring")]
    out = estimator._estimate_all_items(items, {"hot.py": 25}, RATE)
    hot = next(o for o in out if o["file"] == "hot.py")
    cold = next(o for o in out if o["file"] == "cold.py")
    assert hot["churn_multiplier"] == 2.5 and cold["churn_multiplier"] == 1.0
    assert hot["cost_usd"] == pytest.approx(cold["cost_usd"] * 2.5, rel=1e-2)


def test_reconciliation_holds_with_buckets(estimator: CostEstimator) -> None:
    _use_pool(estimator, FakePool())
    items = _synthetic(400)
    items.append(_item("s.py", "security", "high", type="security_hotspot",
                       cost_usd=777.0))
    estimator.tag_principal(items)
    principal = [i for i in items if i["principal"]]
    others = [i for i in items if not i["principal"]]
    out = estimator._estimate_all_items(principal, {"pkg/m1.py": 12}, RATE) + others
    totals = estimator._aggregate_costs(out, 2.7)
    cat_cost = sum(c["cost_usd"] for c in totals["cost_by_category"].values())
    cat_hours = sum(c["hours"] for c in totals["cost_by_category"].values())
    assert abs(cat_cost - totals["total_cost_usd"]) < 1
    assert abs(cat_hours - totals["total_remediation_hours"]) <= 0.1
