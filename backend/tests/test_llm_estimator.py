"""Tests for LLMEstimator."""
from unittest.mock import MagicMock

import pytest
from tools.llm_estimator import LLMEstimator


def _est() -> LLMEstimator:
    """Return an LLMEstimator with a mock LLM (no real API calls in tests)."""
    return LLMEstimator(llm=MagicMock())


def test_fallback_returns_valid_estimate():
    result = _est()._fallback("security", "high")
    assert result["realistic_hours"] > 0
    assert result["confidence"] == "low"
    assert result["source"] == "fallback"
    assert 1 <= result["severity_score"] <= 10


def test_parse_response_valid_json():
    raw = '''{"realistic_hours": 8.0, "severity_score": 7,
              "business_risk_score": 8, "fix_complexity_score": 6,
              "confidence": "high",
              "primary_risk": "Auth bypass possible",
              "fix_summary": "Sanitize all inputs",
              "cost_rationale": "Requires full auth rewrite"}'''
    result = _est()._parse_response(raw, "security", "high")
    assert result["realistic_hours"] == 8.0
    assert result["confidence"] == "high"


def test_parse_response_strips_think_tags():
    raw = '''<think>Let me analyze this carefully...</think>
    {"realistic_hours": 3.0, "severity_score": 5,
     "business_risk_score": 5, "fix_complexity_score": 5,
     "confidence": "medium",
     "primary_risk": "Minor risk",
     "fix_summary": "Simple refactor",
     "cost_rationale": "Straightforward"}'''
    result = _est()._parse_response(raw, "code_quality", "medium")
    assert result["realistic_hours"] == 3.0


def test_parse_response_invalid_json_uses_fallback():
    result = _est()._parse_response("not json at all", "security", "high")
    assert result["confidence"] == "low"
    assert "fallback" in result.get("source", "")


def test_clamp_extreme_hours():
    raw = '''{"realistic_hours": 999, "severity_score": 15,
              "business_risk_score": 0, "fix_complexity_score": 5,
              "confidence": "high",
              "primary_risk": "test", "fix_summary": "test",
              "cost_rationale": "test"}'''
    result = _est()._parse_response(raw, "security", "high")
    assert result["realistic_hours"] <= 200.0
    assert result["severity_score"] <= 10
    assert result["business_risk_score"] >= 1


def test_fallback_estimates():
    result = LLMEstimator._fallback_estimates("code_quality", "medium")
    assert result["realistic_hours"] >= 0
    assert result["severity_score"] >= 1
    assert result["severity_score"] <= 10
    assert result["confidence"] == "low"

class _NotFoundError(Exception):
    """Stand-in for groq.NotFoundError (404 model_not_found)."""


_404_MSG = (
    "Error code: 404 - {'error': {'message': 'The model `llama-3.3-70b-versatile` "
    "does not exist', 'type': 'invalid_request_error', 'code': 'model_not_found'}}"
)

_VALID_ESTIMATE = (
    '{"realistic_hours": 6.0, "severity_score": 7, "business_risk_score": 6,'
    ' "fix_complexity_score": 4, "confidence": "high", "primary_risk": "r",'
    ' "fix_summary": "f", "cost_rationale": "c"}'
)

_ITEMS = [
    {"file_path": "a.py", "category": "security", "severity": "critical"},
    {"file_path": "b.py", "category": "code_quality", "severity": "low"},
    {"file_path": "c.py", "category": "documentation", "severity": "medium"},
]


def _failing_estimator() -> LLMEstimator:
    llm = MagicMock()
    llm.invoke.side_effect = _NotFoundError(_404_MSG)
    return LLMEstimator(llm=llm)


def _responding_estimator(content: str) -> LLMEstimator:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=content)
    return LLMEstimator(llm=llm)


def test_fallback_hours_ignore_severity():
    """Severity is applied downstream, so fallback hours depend on category only."""
    hours = {
        sev: LLMEstimator._fallback_estimates("security", sev)["realistic_hours"]
        for sev in ("critical", "high", "medium", "low")
    }
    assert len(set(hours.values())) == 1
    assert hours["critical"] == 4.0
    crit = LLMEstimator._fallback_estimates("security", "critical")
    low = LLMEstimator._fallback_estimates("security", "low")
    assert crit["severity_score"] > low["severity_score"]
    assert crit["estimation_source"] == "fallback"
    assert crit["estimation_error"]


def test_single_item_404_falls_back_with_error():
    est = _failing_estimator()
    result = est.estimate_debt_item("a.py", "security", "high", "desc")
    assert result["estimation_source"] == "fallback"
    assert result["estimation_error"].startswith("_NotFoundError: Error code: 404")
    assert len(result["estimation_error"]) <= len("_NotFoundError: ") + 200
    assert est.last_error == result["estimation_error"]


def test_batch_404_all_items_fallback_with_error():
    est = _failing_estimator()
    results = est.estimate_debt_items_batch(_ITEMS)
    assert len(results) == len(_ITEMS)
    assert all(r["estimation_source"] == "fallback" for r in results)
    assert all("model_not_found" in r["estimation_error"] for r in results)
    assert est.last_error is not None and "404" in est.last_error


def test_single_item_success_is_llm():
    est = _responding_estimator(_VALID_ESTIMATE)
    result = est.estimate_debt_item("a.py", "security", "high", "desc")
    assert result["estimation_source"] == "llm"
    assert "estimation_error" not in result
    assert result["realistic_hours"] == 6.0
    assert est.last_error is None


def test_batch_success_is_llm():
    est = _responding_estimator("[" + ",".join([_VALID_ESTIMATE] * 3) + "]")
    results = est.estimate_debt_items_batch(_ITEMS)
    assert [r["estimation_source"] for r in results] == ["llm"] * 3
    assert est.last_error is None


def test_batch_short_response_marks_missing_items_fallback():
    est = _responding_estimator("[" + _VALID_ESTIMATE + "]")
    results = est.estimate_debt_items_batch(_ITEMS)
    assert [r["estimation_source"] for r in results] == ["llm", "fallback", "fallback"]
    assert results[1]["estimation_error"].startswith("MissingEstimate")


def test_unparseable_response_falls_back():
    est = _responding_estimator("sorry, I cannot help")
    result = est.estimate_debt_item("a.py", "security", "high", "desc")
    assert result["estimation_source"] == "fallback"
    assert result["estimation_error"].startswith("ValueError")


def test_strip_reasoning_handles_nemotron_style_output() -> None:
    """Reasoning text without an opening <think> tag must not break JSON parsing."""
    from tools.llm_estimator import _strip_reasoning

    raw = 'Let me weigh {severity} and [hours]...\n</think>\n```json\n{"hours": 3}\n```'
    assert _strip_reasoning(raw) == '{"hours": 3}'
    assert _strip_reasoning('<think>a {b}</think>[{"h": 1}]') == '[{"h": 1}]'
    assert _strip_reasoning('{"h": 2}\n<think>truncated {x') == '{"h": 2}'
