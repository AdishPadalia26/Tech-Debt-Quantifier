"""Tests for LLMEstimator."""
import pytest
from tools.llm_estimator import LLMEstimator


def test_fallback_returns_valid_estimate():
    """Test fallback returns valid estimate."""
    est = LLMEstimator(ollama_client=None, model="")
    result = est._fallback("security", "high")
    assert result["realistic_hours"] > 0
    assert result["confidence"] == "low"
    assert result["source"] == "fallback"
    assert 1 <= result["severity_score"] <= 10


def test_parse_response_valid_json():
    """Test parsing valid JSON response."""
    est = LLMEstimator(ollama_client=None, model="")
    raw = '''{"realistic_hours": 8.0, "severity_score": 7,
              "business_risk_score": 8, "fix_complexity_score": 6,
              "confidence": "high",
              "primary_risk": "Auth bypass possible",
              "fix_summary": "Sanitize all inputs",
              "cost_rationale": "Requires full auth rewrite"}'''
    result = est._parse_response(raw, "security", "high")
    assert result["realistic_hours"] == 8.0
    assert result["confidence"] == "high"


def test_parse_response_strips_think_tags():
    """Test parsing strips think tags."""
    est = LLMEstimator(ollama_client=None, model="")
    raw = '''<think>Let me analyze this carefully...</think>
    {"realistic_hours": 3.0, "severity_score": 5,
     "business_risk_score": 5, "fix_complexity_score": 5,
     "confidence": "medium",
     "primary_risk": "Minor risk",
     "fix_summary": "Simple refactor",
     "cost_rationale": "Straightforward"}'''
    result = est._parse_response(raw, "code_quality", "medium")
    assert result["realistic_hours"] == 3.0


def test_parse_response_invalid_json_raises():
    """Test parsing invalid JSON uses fallback."""
    est = LLMEstimator(ollama_client=None, model="")
    result = est._parse_response("not json at all", "security", "high")
    assert result["confidence"] == "low"
    assert "fallback" in result.get("source", "")


def test_clamp_extreme_hours():
    """Test clamping extreme hours."""
    est = LLMEstimator(ollama_client=None, model="")
    raw = '''{"realistic_hours": 999, "severity_score": 15,
              "business_risk_score": 0, "fix_complexity_score": 5,
              "confidence": "high",
              "primary_risk": "test", "fix_summary": "test",
              "cost_rationale": "test"}'''
    result = est._parse_response(raw, "security", "high")
    assert result["realistic_hours"] <= 200.0
    assert result["severity_score"] <= 10
    assert result["business_risk_score"] >= 1


def test_fallback_estimates():
    """Test fallback estimates method."""
    est = LLMEstimator(ollama_client=None, model="")
    result = est._fallback_estimates("code_quality", "medium")
    assert result["realistic_hours"] >= 0
    assert result["severity_score"] >= 1
    assert result["severity_score"] <= 10
    assert result["confidence"] == "low"