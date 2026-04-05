"""Focused tests for product-layer analysis helpers."""

from pathlib import Path

from services.finding_aggregator import FindingAggregator
from tools.architecture_analysis import ArchitectureAnalyzer
from tools.scoring import aggregate_repo_score, max_severity, severity_rank
from tools.test_debt_analysis import TestDebtAnalyzer


def test_scoring_helpers() -> None:
    """Scoring helpers should use semantic ordering and bounded scores."""
    assert severity_rank("critical") > severity_rank("high")
    assert max_severity(["low", "high", "medium"]) == "high"
    assert aggregate_repo_score(
        total_cost=1000.0, function_count=10, cisq_per_function=200.0
    ) == 5.0


def test_finding_aggregator_outputs() -> None:
    """Finding aggregator should build stable product views."""
    debt_items = [
        {
            "file": "app/service.py",
            "category": "code_quality",
            "severity": "high",
            "type": "complexity_hotspot",
            "function": "handle",
            "line": 10,
            "remediation_hours": 3.0,
            "cost_usd": 210.0,
            "confidence": 0.8,
            "business_impact": "high",
            "complexity": 18,
            "change_count": 7,
        },
        {
            "file": "app/api.py",
            "category": "documentation",
            "severity": "low",
            "type": "missing_docstring",
            "function": "endpoint",
            "line": 3,
            "remediation_hours": 0.3,
            "cost_usd": 10.0,
            "confidence": 0.7,
            "business_impact": "low",
            "doc_type": "missing_docstring",
        },
    ]

    aggregated = FindingAggregator().aggregate(debt_items)

    assert len(aggregated["findings"]) == 2
    assert aggregated["findings"][0]["module"] == "app"
    assert aggregated["module_summaries"][0]["module"] == "app"
    assert "quick_wins" in aggregated["roadmap"]


def test_test_debt_analyzer_detects_missing_tests(tmp_path: Path) -> None:
    """Test debt analyzer should flag source files without matching tests."""
    app_dir = tmp_path / "app"
    tests_dir = tmp_path / "tests"
    app_dir.mkdir()
    tests_dir.mkdir()

    (app_dir / "service.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    (tests_dir / "test_other.py").write_text(
        "def test_other():\n    assert True\n", encoding="utf-8"
    )

    findings = TestDebtAnalyzer().find_test_gaps(str(tmp_path), ["app/service.py"])

    assert findings
    assert findings[0]["category"] == "test_debt"
    assert findings[0]["is_hotspot"] is True


def test_architecture_analyzer_detects_oversized_module(tmp_path: Path) -> None:
    """Architecture analyzer should flag large multi-function modules."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    lines = ["import os\n", "import sys\n"]
    for idx in range(12):
        lines.append(f"def fn_{idx}():\n")
        for _ in range(35):
            lines.append("    value = 1\n")
        lines.append("    return value\n\n")

    (app_dir / "big_module.py").write_text("".join(lines), encoding="utf-8")

    findings = ArchitectureAnalyzer().analyze(str(tmp_path), hourly_rate=100.0)

    assert findings
    assert any(item["type"] == "oversized_module" for item in findings)
