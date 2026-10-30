"""Live lookups with cited table fallbacks, caching and time boxes."""

import socket
import time
from typing import Any

import pytest

import intelligence.rate_agent as rate_agent_mod
from data.reference_tables import REFERENCE_TABLES_VERSION, live_cache
from intelligence.rate_agent import RateIntelligenceAgent
from intelligence.security_cost_agent import parse_breach_cost

ddgs_mod = pytest.importorskip("ddgs")


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Fresh cache, no env override, no SO zip / background download."""
    live_cache.clear()
    monkeypatch.delenv("ENGINEER_HOURLY_RATE", raising=False)
    monkeypatch.setattr(rate_agent_mod, "SO_ZIP_PATH", tmp_path / "so.zip")
    monkeypatch.setattr(rate_agent_mod, "SO_BACKGROUND_DOWNLOAD", False)
    yield
    live_cache.clear()


def _boom(*_a: object, **_k: object) -> None:
    raise ConnectionError("network blocked")


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every outbound network path raises."""
    import httpx

    monkeypatch.setattr(httpx, "get", _boom)
    monkeypatch.setattr(httpx, "Client", _boom)
    monkeypatch.setattr(ddgs_mod, "DDGS", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


BLS_JSON = {
    "status": "REQUEST_SUCCEEDED",
    "Results": {"series": [{"data": [{"value": "150000"}]}]},
}
LEVELS_JSON = [
    {"title": "Python Engineer", "totalyearlycompensation": 208000}
] * 3
OTHER_HTML = "<html><body><p>No data here.</p></body></html>"
DDG_RESULTS = [
    {
        "body": (
            "Python engineers earn $75 per hour. The global average cost of a "
            "data breach reached $4.45 million. The probability of a breach "
            "this year is 12%."
        ),
        "href": "https://example.com/a",
    }
]


class _Resp:
    def __init__(self, payload: Any) -> None:
        self.status_code = 200
        self._payload = payload
        self.text = payload if isinstance(payload, str) else ""

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _Net:
    """Canned httpx/ddgs responses with call counting."""

    def __init__(self) -> None:
        self.calls = 0

    def route(self, url: str) -> Any:
        self.calls += 1
        if "api.bls.gov" in url:
            return _Resp(BLS_JSON)
        if "levels.fyi" in url:
            return _Resp(LEVELS_JSON)
        return _Resp(OTHER_HTML)


@pytest.fixture
def canned(monkeypatch: pytest.MonkeyPatch) -> _Net:
    """Mock httpx and ddgs with canned live responses."""
    import httpx

    net = _Net()

    class FakeClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def get(self, url: str, **_k: object) -> _Resp:
            return net.route(url)

    class FakeDDGS:
        def __enter__(self) -> "FakeDDGS":
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def text(self, *_a: object, **_k: object) -> list[dict]:
            net.calls += 1
            return DDG_RESULTS

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(httpx, "get", lambda url, **_k: net.route(url))
    monkeypatch.setattr(ddgs_mod, "DDGS", FakeDDGS)
    return net


# (a) network down -> table fallback ------------------------------------------
def test_rates_fall_back_to_table(no_network: None) -> None:
    """All sources fail: cited table rate, live False, inside time box."""
    start = time.monotonic()
    r = RateIntelligenceAgent().blend_rates("Python", "mid")
    assert time.monotonic() - start < 8.5
    assert r["live"] is False and r["live_sources"] == 0
    assert r["blended_rate"] == pytest.approx(90.30, abs=0.01)
    assert r["reference_version"] == REFERENCE_TABLES_VERSION
    assert r["source"] and r["citation"]
    assert all(not b["live"] for b in r["breakdown"].values())


def test_benchmarks_fall_back_to_table(no_network: None) -> None:
    """Benchmark scrape fails: table value, live False."""
    import constants
    from intelligence.benchmark_agent import BenchmarkAgent

    b = BenchmarkAgent().get_current_benchmarks("python")
    assert b["live"] is False
    assert b["cost_per_function_usd"] == constants.CISQ_COST_PER_FUNCTION
    for key in ("avg_debt_days", "avg_debt_ratio_pct", "confidence", "sources"):
        assert key in b


def test_security_falls_back_to_table(no_network: None) -> None:
    """Breach/DBIR lookups fail: table values, real CVSS still used."""
    from intelligence.security_cost_agent import SecurityCostAgent

    agent = SecurityCostAgent()
    hi = agent.get_risk_weighted_cost("CWE-89", 9.8, 4.0, 90.0)
    lo = agent.get_risk_weighted_cost(None, 3.0, 4.0, 90.0)
    assert hi["data_fresh"] is False and hi["live"] is False
    assert hi["breach_cost_used"] == pytest.approx(4_880_000 * 1.5)
    assert hi["total_security_cost"] > hi["fix_cost"] == 360.0
    assert lo["expected_breach_value"] == 0


def test_rate_deterministic_offline(no_network: None) -> None:
    """Offline blend is deterministic."""
    agent = RateIntelligenceAgent()
    vals = {agent.blend_rates(t, "senior")["blended_rate"] for t in ("Go", "Rust")}
    assert len(vals) == 1


def test_env_rate_is_fallback_when_offline(
    no_network: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every live source down, ENGINEER_HOURLY_RATE is used before the table."""
    monkeypatch.setenv("ENGINEER_HOURLY_RATE", "100")
    r = RateIntelligenceAgent().blend_rates("Python", "mid")
    assert r["blended_rate"] == 100.0
    assert r["source"] == "env_fallback"
    assert r["live"] is False


def test_table_used_when_offline_and_no_env(no_network: None) -> None:
    """With every live source down and no env value, the cited table is used."""
    r = RateIntelligenceAgent().blend_rates("Python", "mid")
    assert r["source"] != "env_fallback"
    assert "table fallback" in r["source"]


def test_env_rate_ignored_when_live(
    canned: _Net, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live sources win over ENGINEER_HOURLY_RATE."""
    monkeypatch.setenv("ENGINEER_HOURLY_RATE", "100")
    r = RateIntelligenceAgent().blend_rates("Python", "mid")
    assert r["live"] is True
    assert r["blended_rate"] != 100.0


# (b) canned live responses ---------------------------------------------------
def test_live_rates_used(canned: _Net) -> None:
    """Live BLS/Levels/DDG values are blended, live True, SO falls back."""
    r = RateIntelligenceAgent().blend_rates("Python", "mid")
    bls = 150000 / 2080 * 1.42
    levels = 208000 / 2080
    expected = (bls * 0.4 + levels * 0.3 + 75 * 0.1) / 0.8
    assert r["live"] is True and r["live_sources"] == 3
    assert r["blended_rate"] == pytest.approx(expected, abs=0.02)
    assert r["breakdown"]["bls"]["live"] and not r["breakdown"]["so"]["live"]
    assert r["breakdown"]["so"]["effective_weight"] == 0
    assert sum(b["effective_weight"] for b in r["breakdown"].values()) == (
        pytest.approx(1.0, abs=0.01)
    )


def test_live_benchmark_used(canned: _Net) -> None:
    """Benchmark is derived from the live rate blend and cited."""
    from intelligence.benchmark_agent import (
        REMEDIATION_HOURS_PER_FUNCTION,
        BenchmarkAgent,
    )

    rate = RateIntelligenceAgent().blend_rates("Python", "mid")
    b = BenchmarkAgent().get_current_benchmarks("python", rate=rate)
    assert b["live"] is True and b["confidence"] == "high"
    assert b["cost_per_function_usd"] == pytest.approx(
        rate["blended_rate"] * REMEDIATION_HOURS_PER_FUNCTION, abs=0.01
    )
    assert "live blended mid-level rate" in b["citation"]


def test_benchmark_anchored_to_reference() -> None:
    """At the reference rate the derived benchmark equals the table value."""
    import constants
    from intelligence.benchmark_agent import REFERENCE_MID_RATE_USD, BenchmarkAgent

    rate = {"blended_rate": REFERENCE_MID_RATE_USD, "live": True, "source": "x"}
    b = BenchmarkAgent().get_current_benchmarks("python", rate=rate)
    assert b["cost_per_function_usd"] == pytest.approx(
        constants.CISQ_COST_PER_FUNCTION, abs=0.01
    )
    stale = {"blended_rate": 120.0, "live": False}
    assert BenchmarkAgent().get_current_benchmarks("python", rate=stale)["live"] is False


def test_live_security_used(canned: _Net) -> None:
    """Breach cost comes from search snippets; DBIR probability from the table."""
    from data.reference_tables import DBIR_TABLE
    from intelligence.security_cost_agent import SecurityCostAgent

    r = SecurityCostAgent().get_risk_weighted_cost("CWE-78", 9.0, 2.0, 100.0)
    assert r["live"] is True and r["data_fresh"] is False
    assert r["source_details"]["breach_cost"]["live"] is True
    assert r["breach_cost_used"] == pytest.approx(4_450_000 * 1.3)
    assert r["breach_probability_pct"] == pytest.approx(
        DBIR_TABLE["value"] * 0.9 * 100, abs=0.01
    )


# (c) strict parsers ----------------------------------------------------------
def test_security_parsers_strict() -> None:
    """Breach cost needs a tight pattern and a sane range."""
    assert parse_breach_cost("Average cost of a data breach: $4.88 million.") == (
        pytest.approx(4_880_000)
    )
    assert parse_breach_cost(
        "The global average cost of a data breach reached USD 4.99 million."
    ) == pytest.approx(4_990_000)
    assert parse_breach_cost("Company raised $50 million in funding.") is None


# (d) caching -----------------------------------------------------------------
def test_cache_hit_avoids_second_network_call(canned: _Net) -> None:
    """Second identical blend makes no further network calls."""
    agent = RateIntelligenceAgent()
    agent.blend_rates("Python", "mid")
    first = canned.calls
    assert first > 0
    agent.blend_rates("Python", "mid")
    assert canned.calls == first


def test_failure_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed lookup is cached so repeat scans do not re-hit the network."""
    import httpx

    calls = {"n": 0}

    def counting_boom(*_a: object, **_k: object) -> None:
        calls["n"] += 1
        raise ConnectionError("down")

    monkeypatch.setattr(httpx, "Client", counting_boom)
    monkeypatch.setattr(ddgs_mod, "DDGS", counting_boom)
    agent = RateIntelligenceAgent()
    agent.blend_rates("Python", "mid")
    n = calls["n"]
    agent.blend_rates("Python", "mid")
    assert calls["n"] == n
