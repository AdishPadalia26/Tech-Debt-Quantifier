"""Live lookups with cited table fallbacks, caching and time boxes."""

import socket
import time
from typing import Any

import pytest

import intelligence.rate_agent as rate_agent_mod
from data.reference_tables import REFERENCE_TABLES_VERSION, live_cache
from intelligence.benchmark_agent import parse_per_function_cost
from intelligence.rate_agent import RateIntelligenceAgent
from intelligence.security_cost_agent import (
    parse_breach_cost,
    parse_breach_probability,
)

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
BENCH_HTML = (
    "<html><body><p>Studies vary. Remediation costs about $620 per function "
    "point on average.</p></body></html>"
)
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
        return _Resp(BENCH_HTML)


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
    """A strict per-function-point sentence is accepted and cited."""
    from intelligence.benchmark_agent import BenchmarkAgent

    b = BenchmarkAgent().get_current_benchmarks("python")
    assert b["live"] is True
    assert b["cost_per_function_usd"] == 620.0
    assert "$620 per function point" in b["citation"]


def test_live_security_used(canned: _Net) -> None:
    """Breach cost and DBIR probability come from search snippets."""
    from intelligence.security_cost_agent import SecurityCostAgent

    r = SecurityCostAgent().get_risk_weighted_cost("CWE-78", 9.0, 2.0, 100.0)
    assert r["live"] is True and r["data_fresh"] is True
    assert r["breach_cost_used"] == pytest.approx(4_450_000 * 1.3)
    assert r["breach_probability_pct"] == pytest.approx(12 * 0.9, abs=0.01)


# (c) strict parsers ----------------------------------------------------------
def test_benchmark_parser_strict() -> None:
    """Blog-style loose text is rejected; tied sentence accepted."""
    blog = (
        "Defects can cost $607 to fix in production. Teams ship every "
        "function they write. Another figure is $12 per function point."
    )
    assert parse_per_function_cost(blog) is None
    good = "CISQ estimates remediation at $1,250 per function point."
    value, snippet = parse_per_function_cost(good) or (0, "")
    assert value == 1250.0 and "per function point" in snippet
    assert parse_per_function_cost("It costs $90,000 per function.") is None


def test_security_parsers_strict() -> None:
    """Breach cost and probability need tight patterns and sane ranges."""
    assert parse_breach_cost("Average cost of a data breach: $4.88 million.") == (
        pytest.approx(4_880_000)
    )
    assert parse_breach_cost("Company raised $50 million in funding.") is None
    assert parse_breach_probability(
        "The probability of a breach is 8%."
    ) == pytest.approx(0.08)
    assert parse_breach_probability("We saw 80% growth in breach reports") is None


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
