"""Tests for the multi-provider LLM pool (fake providers, no network)."""

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from agents.llm_pool import (
    LLMPool,
    classify_error,
    parse_retry_after,
    stable_hash,
)
from tools.cost_estimator import CostEstimator
from tools.llm_estimator import LLMEstimator


def _estimate(hours: float = 1.0) -> dict[str, Any]:
    return {
        "realistic_hours": hours,
        "severity_score": 5,
        "business_risk_score": 5,
        "fix_complexity_score": 5,
        "confidence": "high",
        "primary_risk": "r",
        "fix_summary": "f",
        "cost_rationale": "c",
        "estimation_source": "llm",
    }


class FakeRateLimit(Exception):
    """Mimics an SDK 429 error."""

    status_code = 429


class FakeEstimator:
    """Scriptable stand-in for LLMEstimator (strict batch API)."""

    def __init__(
        self,
        behavior: Callable[["FakeEstimator", list[dict[str, Any]]], Any] | None = None,
    ) -> None:
        self.behavior = behavior
        self.calls: list[list[str]] = []
        self.seen: list[str] = []

    def estimate_debt_items_batch_strict(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any] | None]:
        self.calls.append([it["description"] for it in items])
        self.seen.extend(it["description"] for it in items)
        if self.behavior is not None:
            return self.behavior(self, items)
        return _ok(self, items)


def _ok(_est: FakeEstimator, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # hours encode the item's index so tests can verify input ordering
    return [_estimate(float(it["description"])) for it in items]


def _items(n: int) -> list[dict[str, Any]]:
    return [
        {
            "file_path": f"src/mod{i}.py",
            "function_name": f"fn{i}",
            "category": "code_quality",
            "severity": "medium",
            "description": str(i),
            "code_snippet": f"def fn{i}(): pass  # snippet {i}",
        }
        for i in range(n)
    ]


def _pool(
    estimators: dict[str, FakeEstimator], **kwargs: Any
) -> LLMPool:
    params: dict[str, Any] = {
        "models": {p: f"{p}-model" for p in estimators},
        "concurrency": {p: 2 for p in estimators},
        "batch_size": 2,
        "batch_timeout": 2.0,
        "time_box": 10.0,
        "max_attempts": 4,
        "backoff_base": 0.05,
        "backoff_cap": 0.2,
        "use_cache": False,
    }
    params.update(kwargs)
    return LLMPool(list(estimators), estimators=estimators, **params)


def test_all_items_estimated_in_input_order() -> None:
    ests = {"a": FakeEstimator(), "b": FakeEstimator(), "c": FakeEstimator()}
    results, stats = _pool(ests).estimate_items(_items(23))
    assert len(results) == 23
    assert all(r["estimation_source"] == "llm" for r in results)
    assert [r["realistic_hours"] for r in results] == [float(i) for i in range(23)]
    assert all(r["estimation_provider"] in ests for r in results)
    assert all(r["estimation_model"] == f"{r['estimation_provider']}-model"
               for r in results)
    assert stats["llm"] == 23 and stats["fallback"] == 0
    assert sum(s["items_ok"] for s in stats["per_provider"].values()) == 23
    assert set(stats["per_provider"]["a"]) >= {
        "batches_ok", "items_ok", "rate_limited", "timeouts", "errors", "disabled",
    }


def test_empty_input() -> None:
    results, stats = _pool({"a": FakeEstimator()}).estimate_items([])
    assert results == [] and stats["cache_hits"] == 0


def test_rate_limited_provider_cools_and_others_finish() -> None:
    def limited(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        err = FakeRateLimit("Rate limit reached. Please try again in 0.2s")
        raise err

    ests = {
        "a": FakeEstimator(limited),
        "b": FakeEstimator(),
        "c": FakeEstimator(),
    }
    results, stats = _pool(ests).estimate_items(_items(30))
    assert all(r["estimation_source"] == "llm" for r in results)
    assert all(r["estimation_provider"] in ("b", "c") for r in results)
    assert stats["per_provider"]["a"]["rate_limited"] >= 1
    assert stats["per_provider"]["a"]["items_ok"] == 0
    assert stats["per_provider"]["a"]["disabled"] is False  # cooled, not disabled
    assert stats["fallback"] == 0


def test_cooldown_blocks_provider_until_expiry() -> None:
    calls: list[float] = []

    def limited_once(est: FakeEstimator, items: list[dict[str, Any]]) -> Any:
        calls.append(time.monotonic())
        if len(calls) == 1:
            raise FakeRateLimit("429 Too Many Requests")
        return _ok(est, items)

    ests = {"a": FakeEstimator(limited_once)}
    pool = _pool(ests, concurrency={"a": 1}, batch_size=1, backoff_base=0.4,
                 backoff_cap=0.4)
    results, stats = pool.estimate_items(_items(2))
    assert all(r["estimation_source"] == "llm" for r in results)
    assert stats["per_provider"]["a"]["rate_limited"] == 1
    assert calls[1] - calls[0] >= 0.35  # waited out the cooldown


def test_timeout_splits_batch() -> None:
    def slow_when_big(est: FakeEstimator, items: list[dict[str, Any]]) -> Any:
        if len(items) > 2:
            time.sleep(0.6)
        return _ok(est, items)

    est = FakeEstimator(slow_when_big)
    pool = _pool({"a": est}, batch_size=4, batch_timeout=0.15,
                 concurrency={"a": 1})
    results, stats = pool.estimate_items(_items(4))
    assert all(r["estimation_source"] == "llm" for r in results)
    assert stats["per_provider"]["a"]["timeouts"] == 1
    sizes = sorted(len(c) for c in est.calls)
    assert sizes == [2, 2, 4]


def test_other_error_moves_to_different_provider() -> None:
    def boom(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        raise RuntimeError("boom")

    ests = {"a": FakeEstimator(boom), "b": FakeEstimator()}
    results, stats = _pool(ests, concurrency={"a": 1, "b": 1}).estimate_items(
        _items(8)
    )
    assert all(r["estimation_source"] == "llm" for r in results)
    assert all(r["estimation_provider"] == "b" for r in results)
    assert stats["per_provider"]["a"]["errors"] >= 1


def test_all_providers_failing_falls_back_with_error() -> None:
    def boom(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        raise RuntimeError("provider exploded")

    ests = {"a": FakeEstimator(boom), "b": FakeEstimator(boom)}
    results, stats = _pool(ests, max_attempts=3).estimate_items(_items(6))
    assert len(results) == 6
    for r in results:
        assert r["estimation_source"] == "fallback"
        assert "provider exploded" in r["estimation_error"]
        assert r["estimation_provider"] is None
    assert stats["fallback"] == 6 and stats["llm"] == 0


def test_provider_disabled_after_consecutive_failures() -> None:
    def boom(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        raise RuntimeError("down")

    ests = {"a": FakeEstimator(boom), "b": FakeEstimator()}
    pool = _pool(ests, failure_limit=2, concurrency={"a": 1, "b": 1}, batch_size=1)
    results, stats = pool.estimate_items(_items(12))
    assert stats["per_provider"]["a"]["disabled"] is True
    assert all(r["estimation_source"] == "llm" for r in results)


def test_all_disabled_falls_back_quickly() -> None:
    def boom(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        raise RuntimeError("down")

    ests = {"a": FakeEstimator(boom)}
    pool = _pool(ests, failure_limit=1, max_attempts=10, concurrency={"a": 1})
    results, stats = pool.estimate_items(_items(4))
    assert all(r["estimation_source"] == "fallback" for r in results)
    assert stats["per_provider"]["a"]["disabled"] is True
    assert stats["elapsed_s"] < 3


def test_pinning_is_deterministic_when_healthy() -> None:
    items = _items(30)

    def run() -> dict[str, set[str]]:
        ests = {n: FakeEstimator(lambda e, i: (time.sleep(0.05), _ok(e, i))[1])
                for n in ("a", "b", "c")}
        # one batch per provider -> no queue is ever empty before work starts
        pool = _pool(ests, batch_size=100, concurrency={n: 1 for n in ests})
        pool.estimate_items(items)
        return {n: set(e.seen) for n, e in ests.items()}

    first, second = run(), run()
    assert first == second
    pool = _pool({n: FakeEstimator() for n in ("a", "b", "c")})
    for name, seen in first.items():
        expected = {
            it["description"] for it in items if pool.preferred_provider(it) == name
        }
        assert seen == expected
    assert len({pool.preferred_provider(it) for it in items}) == 3


def test_stable_hash_is_process_independent() -> None:
    item = {"file_path": "x.py", "function_name": "f", "category": "security"}
    assert stable_hash(item) == stable_hash(dict(item))
    assert stable_hash(item) != stable_hash({**item, "category": "dead_code"})


def test_idle_provider_steals_work() -> None:
    def slow(est: FakeEstimator, items: list[dict[str, Any]]) -> Any:
        time.sleep(0.4)
        return _ok(est, items)

    ests = {"a": FakeEstimator(slow), "b": FakeEstimator()}
    pool = _pool(ests, concurrency={"a": 1, "b": 1}, batch_size=1)
    items = _items(20)
    results, stats = pool.estimate_items(items)
    own_b = sum(1 for it in items if pool.preferred_provider(it) == "b")
    assert stats["per_provider"]["b"]["items_ok"] > own_b
    assert all(r["estimation_source"] == "llm" for r in results)


def test_cache_hit_skips_llm(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    items = _items(7)
    ests1 = {"a": FakeEstimator(), "b": FakeEstimator()}
    _, stats1 = _pool(ests1, use_cache=True, cache_path=db).estimate_items(items)
    assert stats1["cache_hits"] == 0

    ests2 = {"a": FakeEstimator(), "b": FakeEstimator()}
    results, stats2 = _pool(ests2, use_cache=True, cache_path=db).estimate_items(items)
    assert stats2["cache_hits"] == 7
    assert all(not e.calls for e in ests2.values())
    assert all(r["cached"] is True and r["estimation_source"] == "llm"
               for r in results)
    assert [r["realistic_hours"] for r in results] == [float(i) for i in range(7)]
    assert all(r["estimation_provider"] in ("a", "b") for r in results)


def test_fallbacks_are_not_cached(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"

    def boom(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        raise RuntimeError("x")

    items = _items(3)
    _pool({"a": FakeEstimator(boom)}, use_cache=True, cache_path=db,
          max_attempts=1).estimate_items(items)
    good = {"a": FakeEstimator()}
    _, stats = _pool(good, use_cache=True, cache_path=db).estimate_items(items)
    assert stats["cache_hits"] == 0 and stats["llm"] == 3


def test_time_box_respected() -> None:
    def hang(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        time.sleep(3)
        return []

    ests = {"a": FakeEstimator(hang), "b": FakeEstimator(hang)}
    pool = _pool(ests, time_box=0.4, batch_timeout=10.0)
    start = time.monotonic()
    results, stats = pool.estimate_items(_items(10))
    assert time.monotonic() - start < 2.0
    assert stats["time_box_expired"] is True
    assert all(r["estimation_source"] == "fallback" for r in results)
    assert all("TimeBoxExpired" in r["estimation_error"] for r in results)


def test_rate_limited_past_time_box_falls_back() -> None:
    def limited(_e: FakeEstimator, _items: list[dict[str, Any]]) -> Any:
        raise FakeRateLimit("rate limited, retry-after 30")

    ests = {"a": FakeEstimator(limited)}
    pool = _pool(ests, time_box=0.5, backoff_base=30, backoff_cap=60)
    start = time.monotonic()
    results, _ = pool.estimate_items(_items(3))
    assert time.monotonic() - start < 2.0
    assert all(r["estimation_source"] == "fallback" for r in results)


def test_reported_model_overrides_requested_and_keys_cache(tmp_path: Path) -> None:
    """OpenRouter-style routing: the model that answered is what we record."""

    class FakeLLM:
        def invoke(self, _messages: Any) -> Any:
            body = json.dumps([_estimate(3.0), _estimate(4.0)])
            return SimpleNamespace(
                content=body, response_metadata={"model_name": "cohere/x:free"}
            )

    db = tmp_path / "c.db"
    items = _items(2)
    ests = {"openrouter": LLMEstimator(llm=FakeLLM())}  # type: ignore[arg-type]
    kwargs: dict[str, Any] = {
        "models": {"openrouter": "google/primary:free"},
        "model_candidates": {
            "openrouter": ["google/primary:free", "cohere/x:free"],
        },
        "use_cache": True,
        "cache_path": db,
    }
    pool = LLMPool(["openrouter"], estimators=ests, batch_size=2,
                   batch_timeout=2.0, time_box=5.0, **kwargs)
    results, stats = pool.estimate_items(items)
    assert [r["estimation_model"] for r in results] == ["cohere/x:free"] * 2
    assert all(r["estimation_provider"] == "openrouter" for r in results)

    # second run: cache keyed by the ACTUAL model is found via the candidates
    pool2 = LLMPool(["openrouter"], estimators={"openrouter": FakeEstimator()},
                    batch_size=2, batch_timeout=2.0, time_box=5.0, **kwargs)
    results2, stats2 = pool2.estimate_items(items)
    assert stats2["cache_hits"] == 2
    assert results2[0]["estimation_model"] == "cohere/x:free"


def test_real_estimator_strict_parses_and_surfaces_errors() -> None:
    class BadLLM:
        def invoke(self, _m: Any) -> Any:
            raise FakeRateLimit("429")

    with pytest.raises(FakeRateLimit):
        LLMEstimator(llm=BadLLM()).estimate_debt_items_batch_strict(  # type: ignore[arg-type]
            [{"category": "x", "severity": "low"}]
        )

    class PartialLLM:
        def invoke(self, _m: Any) -> Any:
            return SimpleNamespace(content="<think>hm</think>" + json.dumps(
                [_estimate(2.0), "garbage"]))

    out = LLMEstimator(llm=PartialLLM()).estimate_debt_items_batch_strict(  # type: ignore[arg-type]
        [{"category": "x"}, {"category": "y"}, {"category": "z"}]
    )
    assert out[0] is not None and out[0]["realistic_hours"] == 2.0
    assert out[1] is None and out[2] is None


def test_partial_response_requeues_missing_items() -> None:
    state = {"n": 0}

    def drop_second(est: FakeEstimator, items: list[dict[str, Any]]) -> Any:
        state["n"] += 1
        out = _ok(est, items)
        if state["n"] == 1 and len(out) > 1:
            out[1] = None  # type: ignore[call-overload]
        return out

    pool = _pool({"a": FakeEstimator(drop_second)}, concurrency={"a": 1},
                 batch_size=3)
    results, _ = pool.estimate_items(_items(3))
    assert all(r["estimation_source"] == "llm" for r in results)
    assert [r["realistic_hours"] for r in results] == [0.0, 1.0, 2.0]


# --- error helpers ---------------------------------------------------------


def test_parse_retry_after_variants() -> None:
    assert parse_retry_after(Exception("Please try again in 7.5s.")) == 7.5
    assert parse_retry_after(Exception("try again in 1m3.5s")) == pytest.approx(63.5)
    assert parse_retry_after(Exception("try again in 250ms")) == pytest.approx(0.25)
    assert parse_retry_after(Exception("nothing here")) is None
    exc = Exception("429")
    exc.response = SimpleNamespace(headers={"retry-after": "12"})  # type: ignore[attr-defined]
    assert parse_retry_after(exc) == 12.0


def test_classify_error() -> None:
    assert classify_error(FakeRateLimit("x"))[0] == "rate_limit"
    assert classify_error(Exception("Provider returned error: rate-limited upstream"))[0] == "rate_limit"
    assert classify_error(TimeoutError("t"))[0] == "timeout"
    assert classify_error(RuntimeError("other"))[0] == "error"


# --- CostEstimator integration ---------------------------------------------


def test_cost_estimator_uses_pool_and_reports_stats() -> None:
    est = CostEstimator()
    ests = {"a": FakeEstimator(), "b": FakeEstimator()}
    est._pool_factory = lambda: _pool(ests)  # type: ignore[assignment]
    items = [
        {"file": f"src/f{i}.py", "category": "code_quality", "severity": "medium",
         "description": str(i), "cost_usd": 10.0, "function": f"fn{i}"}
        for i in range(9)
    ]
    items.append({"file": "src/auth.py", "category": "security", "severity": "high",
                  "description": "9", "cost_usd": 777.0, "type": "security_hotspot",
                  "remediation_hours": 4.0})
    out = est._estimate_all_items(items, {}, 85.0)
    assert len(out) == 10
    assert out[-1]["cost_usd"] == 777.0  # fixed cost preserved
    assert all(i["estimation_source"] == "llm" for i in out)
    stats = est._estimation_stats(out)
    assert stats["llm"] == 10 and stats["fallback"] == 0
    assert sum(stats["per_provider"].values()) == 10
    assert set(stats["llm_models"]) <= {"a", "b"}
    assert set(stats["llm_provider"].split(",")) <= {"a", "b"}
    assert stats["cache_hits"] == 0 and stats["elapsed_s"] is not None
    assert est._build_warnings(stats, {"live": True}, {"live": True}) == []
