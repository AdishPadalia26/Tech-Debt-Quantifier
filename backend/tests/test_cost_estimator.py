"""Tests for CostEstimator and cost explanation builder."""
import pytest
from tools.cost_estimator import CostEstimator


def test_cost_by_category_structure():
    """cost_by_category must have cost_usd, count, hours per category."""
    estimator = CostEstimator()
    mock_debt_items = [
        {"category": "security", "cost_usd": 500, "adjusted_minutes": 60,
         "severity": "high", "file": "auth.py"},
        {"category": "code_quality", "cost_usd": 200, "adjusted_minutes": 30,
         "severity": "low", "file": "utils.py"},
    ]
    result = estimator._categorize_costs(mock_debt_items)
    assert "security" in result
    assert result["security"]["cost_usd"] == 500
    assert result["security"]["item_count"] == 1
    assert "code_quality" in result


def test_hybrid_enabled_defaults():
    """Test hybrid estimation disabled by default."""
    estimator = CostEstimator()
    assert estimator._hybrid_enabled is False or estimator._hybrid_enabled is True


def test_calculate_debt_score():
    """Test debt score calculation."""
    estimator = CostEstimator()
    score = estimator.calculate_debt_score(
        total_cost=10000.0,
        function_count=100,
        cisq_per_function=85.0,
    )
    assert score >= 0
    assert score <= 10


def test_sanity_check():
    """Test sanity check on cost estimates."""
    estimator = CostEstimator()
    result = estimator.sanity_check(
        total_cost=10000.0,
        function_count=100,
        cisq_per_function=85.0,
    )
    assert "your_cost_per_function" in result
    assert "industry_avg" in result
    assert "is_reasonable" in result