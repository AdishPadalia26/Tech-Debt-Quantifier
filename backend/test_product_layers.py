"""Focused tests for product-layer analysis helpers."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base
from database.crud import (
    get_scan_findings,
    get_scan_modules,
    get_scan_roadmap,
    get_scan_summary_data,
    save_scan,
)
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


def test_rich_scan_persistence_round_trip() -> None:
    """Structured findings, modules, and roadmap should persist in DB tables."""
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        analysis = {
            "total_cost_usd": 1200.0,
            "debt_score": 3.4,
            "total_remediation_hours": 14.0,
            "total_remediation_sprints": 0.2,
            "cost_by_category": {"code_quality": {"cost_usd": 1200.0, "hours": 14.0, "item_count": 2}},
            "hourly_rates": {"blended_rate": 85.0, "confidence": "medium"},
            "repo_profile": {
                "tech_stack": {"primary_language": "py", "frameworks": ["flask"]},
                "team": {"estimated_team_size": 2, "bus_factor": 1, "repo_age_days": 200},
                "multipliers": {"combined_multiplier": 1.2},
            },
            "debt_items": [
                {
                    "file": "app/service.py",
                    "function": "handle",
                    "category": "code_quality",
                    "severity": "high",
                    "cost_usd": 400.0,
                    "remediation_hours": 3.0,
                    "complexity": 18,
                    "churn_multiplier": 1.7,
                }
            ],
            "findings": [
                {
                    "id": "finding-1",
                    "file_path": "app/service.py",
                    "module": "app",
                    "category": "code_quality",
                    "subcategory": "complexity_hotspot",
                    "symbol_name": "handle",
                    "line_start": 10,
                    "line_end": 10,
                    "severity": "high",
                    "business_impact": "high",
                    "effort_hours": 3.0,
                    "cost_usd": 400.0,
                    "confidence": 0.8,
                    "source_tool": "git+static",
                    "status": "open",
                    "evidence": [{"source": "complexity", "summary": "Complexity score 18"}],
                }
            ],
            "module_summaries": [
                {
                    "module": "app",
                    "finding_count": 1,
                    "total_cost_usd": 400.0,
                    "total_effort_hours": 3.0,
                    "max_severity": "high",
                    "avg_confidence": 0.8,
                }
            ],
            "roadmap": {
                "quick_wins": [
                    {
                        "finding_id": "finding-1",
                        "title": "Code Quality in app/service.py",
                        "file_path": "app/service.py",
                        "module": "app",
                        "severity": "high",
                        "business_impact": "high",
                        "effort_hours": 3.0,
                        "cost_usd": 400.0,
                        "confidence": 0.8,
                    }
                ],
                "next_up": [],
                "strategic": [],
            },
            "summary": {"files_scanned": 1, "functions_analyzed": 1, "issues_found": 1},
        }
        agent_state = {"raw_analysis": analysis, "status": "complete"}

        scan = save_scan(
            db=db,
            job_id="job-1",
            github_url="https://github.com/pallets/flask",
            analysis=analysis,
            agent_state=agent_state,
            duration_seconds=1.2,
            user_id=None,
        )

        summary = get_scan_summary_data(db, scan.id)
        findings = get_scan_findings(db, scan.id)
        modules = get_scan_modules(db, scan.id)
        roadmap = get_scan_roadmap(db, scan.id)

        assert summary is not None
        assert summary["scan_id"] == scan.id
        assert findings and findings[0]["id"] == "finding-1"
        assert modules and modules[0]["module"] == "app"
        assert roadmap["quick_wins"][0]["finding_id"] == "finding-1"
    finally:
        db.close()
