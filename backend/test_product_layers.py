"""Focused tests for product-layer analysis helpers."""

import shutil
import subprocess
import uuid
from pathlib import Path
from shutil import which
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import Base
from database.crud import (
    compare_scans,
    add_finding_feedback,
    get_repo_change_rollup,
    get_rich_repo_trend,
    get_repo_summary_rollup,
    get_repo_triage_stats,
    get_repo_unresolved_findings,
    get_scan_findings,
    get_finding_record,
    query_scan_findings,
    get_scan_modules,
    get_scan_roadmap,
    get_scan_summary_data,
    save_scan,
    suppress_finding,
)
from services.finding_aggregator import FindingAggregator
from intelligence.ownership_analyzer import OwnershipAnalyzer
from intelligence.local_llm_service import LocalLLMService
from intelligence.report_writer_agent import ReportWriterAgent
from intelligence.semantic_triage_agent import SemanticTriageAgent
from tools.architecture_analysis import ArchitectureAnalyzer
from tools.dead_code_analysis import DeadCodeAnalyzer
from tools.dependency_analysis import DependencyDebtAnalyzer
from tools.duplication_analysis import DuplicationAnalyzer
from tools.performance_analysis import PerformanceAnalyzer
from tools.reliability_analysis import ReliabilityAnalyzer
from tools.scoring import aggregate_repo_score, max_severity, severity_rank
from tools.test_debt_analysis import TestDebtAnalyzer


class _FakeLLM:
    """Tiny async fake LLM for bounded unit tests."""

    def __init__(self, response: str, *, should_fail: bool = False) -> None:
        self.response = response
        self.should_fail = should_fail

    async def ainvoke(self, prompt: str):
        if self.should_fail:
            raise RuntimeError("LLM unavailable")
        return SimpleNamespace(content=self.response)


class _SlowFakeLLM:
    """Tiny async fake LLM that simulates a hung local model."""

    async def ainvoke(self, prompt: str):
        import asyncio

        await asyncio.sleep(0.05)
        return SimpleNamespace(content='{"ok": true}')


def _build_repo_analysis(findings: list[dict], roadmap: dict | None = None) -> dict:
    """Create a compact analysis payload for structured persistence tests."""
    total_cost = float(sum(float(item.get("cost_usd", 0.0)) for item in findings))
    total_hours = float(sum(float(item.get("effort_hours", 0.0)) for item in findings))
    modules = {}
    for item in findings:
        module_name = item.get("module", "root")
        modules.setdefault(
            module_name,
            {
                "module": module_name,
                "finding_count": 0,
                "total_cost_usd": 0.0,
                "total_effort_hours": 0.0,
                "max_severity": "low",
                "avg_confidence": 0.0,
            },
        )
        module = modules[module_name]
        module["finding_count"] += 1
        module["total_cost_usd"] += float(item.get("cost_usd", 0.0))
        module["total_effort_hours"] += float(item.get("effort_hours", 0.0))
        if severity_rank(str(item.get("severity", "low"))) > severity_rank(
            str(module["max_severity"])
        ):
            module["max_severity"] = str(item.get("severity", "low"))
        module["avg_confidence"] += float(item.get("confidence", 0.0))

    module_summaries = []
    for module in modules.values():
        module["avg_confidence"] = round(
            module["avg_confidence"] / max(module["finding_count"], 1), 2
        )
        module_summaries.append(module)

    return {
        "total_cost_usd": total_cost,
        "debt_score": 2.5,
        "total_remediation_hours": total_hours,
        "total_remediation_sprints": round(total_hours / 80.0, 2),
        "cost_by_category": {},
        "hourly_rates": {"blended_rate": 85.0, "confidence": "medium"},
        "repo_profile": {
            "tech_stack": {"primary_language": "py", "frameworks": ["flask"]},
            "team": {"estimated_team_size": 2, "bus_factor": 1, "repo_age_days": 200},
            "multipliers": {"combined_multiplier": 1.0},
        },
        "debt_items": [],
        "findings": findings,
        "module_summaries": module_summaries,
        "roadmap": roadmap or {},
        "ownership_summary": {
            "commit_sample_size": 0,
            "unique_contributors": 0,
            "active_contributors_90d": 0,
            "bus_factor": 0,
            "top_contributor_share": 0.0,
            "siloed_hotspots": 0,
            "handoff_hotspots": 0,
        },
    }


def _make_workspace_temp_dir() -> Path:
    """Create a writable temporary directory inside the backend workspace."""
    base_dir = Path(__file__).resolve().parent / ".pytest_tmp_cases"
    base_dir.mkdir(exist_ok=True)
    temp_dir = base_dir / f"case_{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    return temp_dir


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

    ownership_context = {
        "modules": {
            "app": {
                "owner_count": 2,
                "top_contributor_share": 0.75,
                "ownership_risk": "high",
            }
        }
    }
    aggregated = FindingAggregator().aggregate(
        debt_items, ownership_context=ownership_context
    )

    assert len(aggregated["findings"]) == 2
    assert aggregated["findings"][0]["module"] == "app"
    assert aggregated["module_summaries"][0]["module"] == "app"
    assert aggregated["module_summaries"][0]["owner_count"] == 2
    assert "quick_wins" in aggregated["roadmap"]


def test_ownership_analyzer_profiles_contributor_concentration() -> None:
    """Ownership analyzer should compute contributor and concentration metrics."""
    if which("git") is None:
        return

    tmp_path = _make_workspace_temp_dir()
    try:
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Owner One"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "owner1@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        app_dir = tmp_path / "app"
        app_dir.mkdir()
        service_file = app_dir / "service.py"

        service_file.write_text("def handler():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        service_file.write_text("def handler():\n    value = 1\n    return value\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--author", "Owner One <owner1@example.com>", "-m", "owner update"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        service_file.write_text(
            "def handler():\n    value = 2\n    return value\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--author", "Owner Two <owner2@example.com>", "-m", "handoff update"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        analysis = OwnershipAnalyzer().analyze(
            str(tmp_path),
            hotspot_files=["app/service.py"],
            max_commits=50,
        )

        file_profile = analysis["files"]["app/service.py"]
        module_profile = analysis["modules"]["app"]

        assert analysis["summary"]["unique_contributors"] == 2
        assert file_profile["owner_count"] == 2
        assert file_profile["top_contributor_share"] == 0.67
        assert module_profile["ownership_risk"] in {"medium", "high"}
        assert analysis["hotspots"][0]["file_path"] == "app/service.py"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_test_debt_analyzer_detects_missing_tests() -> None:
    """Test debt analyzer should flag source files without matching tests."""
    tmp_path = _make_workspace_temp_dir()
    try:
        app_dir = tmp_path / "app"
        tests_dir = tmp_path / "tests"
        app_dir.mkdir()
        tests_dir.mkdir()

        (app_dir / "service.py").write_text(
            "def handler():\n    return 1\n", encoding="utf-8"
        )
        (tests_dir / "test_other.py").write_text(
            "def test_other():\n    assert True\n", encoding="utf-8"
        )

        findings = TestDebtAnalyzer().find_test_gaps(str(tmp_path), ["app/service.py"])

        assert findings
        assert findings[0]["category"] == "test_debt"
        assert findings[0]["is_hotspot"] is True
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_architecture_analyzer_detects_oversized_module() -> None:
    """Architecture analyzer should flag large multi-function modules."""
    tmp_path = _make_workspace_temp_dir()
    try:
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
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_duplication_analyzer_detects_duplicate_logic() -> None:
    """Duplication analyzer should flag repeated function bodies across files."""
    tmp_path = _make_workspace_temp_dir()
    try:
        module_dir = tmp_path / "app"
        module_dir.mkdir()
        source = (
            "def normalize(value):\n"
            "    cleaned = value.strip().lower()\n"
            "    if not cleaned:\n"
            "        return 'unknown'\n"
            "    return cleaned\n"
        )
        (module_dir / "a.py").write_text(source, encoding="utf-8")
        (module_dir / "b.py").write_text(source.replace("normalize", "sanitize"), encoding="utf-8")

        findings = DuplicationAnalyzer().analyze(str(tmp_path), hourly_rate=100.0)

        assert findings
        assert any(item["type"] == "duplicate_logic" for item in findings)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_dependency_analyzer_detects_loose_versions() -> None:
    """Dependency analyzer should flag range and wildcard version specs."""
    tmp_path = _make_workspace_temp_dir()
    try:
        (tmp_path / "requirements.txt").write_text(
            "requests>=2.0\nflask\n", encoding="utf-8"
        )
        findings = DependencyDebtAnalyzer().analyze(str(tmp_path), hourly_rate=100.0)

        assert len(findings) >= 2
        assert {item["type"] for item in findings} >= {"range_pinned_version", "unbounded_version"}
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_reliability_analyzer_detects_risky_exception_patterns() -> None:
    """Reliability analyzer should flag bare except and silent handlers."""
    tmp_path = _make_workspace_temp_dir()
    try:
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "service.py").write_text(
            "def run(items=[]):\n"
            "    try:\n"
            "        return items[0]\n"
            "    except:\n"
            "        pass\n",
            encoding="utf-8",
        )
        findings = ReliabilityAnalyzer().analyze(str(tmp_path), hourly_rate=100.0)

        assert len(findings) >= 2
        assert any(item["type"] == "bare_except" for item in findings)
        assert any(item["type"] == "silent_exception_handler" for item in findings)
        assert any(item["type"] == "mutable_default_argument" for item in findings)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_performance_analyzer_detects_nested_loop() -> None:
    """Performance analyzer should flag nested loops."""
    tmp_path = _make_workspace_temp_dir()
    try:
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "perf.py").write_text(
            "def compute(rows):\n"
            "    total = 0\n"
            "    for row in rows:\n"
            "        for value in row:\n"
            "            total += value\n"
            "    return total\n",
            encoding="utf-8",
        )
        findings = PerformanceAnalyzer().analyze(str(tmp_path), hourly_rate=100.0)

        assert findings
        assert any(item["type"] == "nested_loop" for item in findings)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_dead_code_analyzer_detects_unreachable_and_unused_private_helpers() -> None:
    """Dead code analyzer should flag unreachable code and unused private functions."""
    tmp_path = _make_workspace_temp_dir()
    try:
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "dead.py").write_text(
            "def _helper():\n"
            "    return 1\n\n"
            "def run():\n"
            "    return 5\n"
            "    print('never')\n",
            encoding="utf-8",
        )
        findings = DeadCodeAnalyzer().analyze(str(tmp_path), hourly_rate=100.0)

        assert len(findings) >= 2
        assert any(item["type"] == "unreachable_code" for item in findings)
        assert any(item["type"] == "unused_private_function" for item in findings)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


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
                    "owner_count": 2,
                    "top_contributor_share": 0.75,
                    "ownership_risk": "high",
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
            "ownership_summary": {
                "commit_sample_size": 12,
                "unique_contributors": 3,
                "active_contributors_90d": 2,
                "bus_factor": 1,
                "top_contributor_share": 0.8,
                "siloed_hotspots": 1,
                "handoff_hotspots": 0,
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
        assert findings[0]["owner_count"] is None
        assert modules and modules[0]["module"] == "app"
        assert modules[0]["owner_count"] == 2
        assert modules[0]["ownership_risk"] == "high"
        assert roadmap["quick_wins"][0]["finding_id"] == "finding-1"
    finally:
        db.close()


def test_query_scan_findings_filters_and_paginates() -> None:
    """Finding queries should support filtering and pagination."""
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
            "cost_by_category": {},
            "hourly_rates": {"blended_rate": 85.0, "confidence": "medium"},
            "repo_profile": {
                "tech_stack": {"primary_language": "py", "frameworks": ["flask"]},
                "team": {"estimated_team_size": 2, "bus_factor": 1, "repo_age_days": 200},
                "multipliers": {"combined_multiplier": 1.2},
            },
            "debt_items": [],
            "findings": [
                {
                    "id": "f-1",
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
                    "evidence": [],
                },
                {
                    "id": "f-2",
                    "file_path": "tests/test_service.py",
                    "module": "tests",
                    "category": "test_debt",
                    "subcategory": "missing_tests",
                    "symbol_name": None,
                    "line_start": None,
                    "line_end": None,
                    "severity": "medium",
                    "business_impact": "medium",
                    "effort_hours": 2.0,
                    "cost_usd": 100.0,
                    "confidence": 0.7,
                    "source_tool": "tests",
                    "status": "open",
                    "evidence": [],
                },
            ],
            "module_summaries": [],
            "roadmap": {},
        }

        scan = save_scan(
            db=db,
            job_id="job-filter",
            github_url="https://github.com/pallets/flask",
            analysis=analysis,
            agent_state={"raw_analysis": analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )

        filtered = query_scan_findings(
            db,
            scan.id,
            category="code_quality",
            severity="high",
            limit=1,
            offset=0,
        )

        assert filtered is not None
        assert filtered["total"] == 1
        assert len(filtered["items"]) == 1
        assert filtered["items"][0]["id"] == "f-1"
    finally:
        db.close()


def test_compare_scans_reports_added_removed_and_changed() -> None:
    """Scan comparison should surface added, removed, and changed findings."""
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        base_analysis = {
            "total_cost_usd": 1000.0,
            "debt_score": 2.0,
            "total_remediation_hours": 10.0,
            "total_remediation_sprints": 0.1,
            "cost_by_category": {},
            "hourly_rates": {"blended_rate": 85.0, "confidence": "medium"},
            "repo_profile": {
                "tech_stack": {"primary_language": "py", "frameworks": ["flask"]},
                "team": {"estimated_team_size": 2, "bus_factor": 1, "repo_age_days": 200},
                "multipliers": {"combined_multiplier": 1.2},
            },
            "debt_items": [],
            "findings": [
                {
                    "id": "shared",
                    "file_path": "app/service.py",
                    "module": "app",
                    "category": "code_quality",
                    "subcategory": "complexity_hotspot",
                    "symbol_name": "handle",
                    "line_start": 10,
                    "line_end": 10,
                    "severity": "medium",
                    "business_impact": "medium",
                    "effort_hours": 2.0,
                    "cost_usd": 150.0,
                    "confidence": 0.8,
                    "source_tool": "git+static",
                    "status": "open",
                    "evidence": [],
                },
                {
                    "id": "removed",
                    "file_path": "app/old.py",
                    "module": "app",
                    "category": "documentation",
                    "subcategory": "missing_docstring",
                    "symbol_name": None,
                    "line_start": 1,
                    "line_end": 1,
                    "severity": "low",
                    "business_impact": "low",
                    "effort_hours": 1.0,
                    "cost_usd": 50.0,
                    "confidence": 0.7,
                    "source_tool": "ast",
                    "status": "open",
                    "evidence": [],
                },
            ],
            "module_summaries": [],
            "roadmap": {},
        }
        target_analysis = {
            **base_analysis,
            "total_cost_usd": 1300.0,
            "debt_score": 2.8,
            "total_remediation_hours": 13.0,
            "findings": [
                {
                    **base_analysis["findings"][0],
                    "severity": "high",
                    "cost_usd": 250.0,
                },
                {
                    "id": "added",
                    "file_path": "app/new.py",
                    "module": "app",
                    "category": "architecture",
                    "subcategory": "oversized_module",
                    "symbol_name": None,
                    "line_start": 1,
                    "line_end": 1,
                    "severity": "high",
                    "business_impact": "high",
                    "effort_hours": 5.0,
                    "cost_usd": 300.0,
                    "confidence": 0.8,
                    "source_tool": "git+static",
                    "status": "open",
                    "evidence": [],
                },
            ],
        }

        base_scan = save_scan(
            db=db,
            job_id="job-base",
            github_url="https://github.com/pallets/flask",
            analysis=base_analysis,
            agent_state={"raw_analysis": base_analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )
        target_scan = save_scan(
            db=db,
            job_id="job-target",
            github_url="https://github.com/pallets/flask",
            analysis=target_analysis,
            agent_state={"raw_analysis": target_analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )

        comparison = compare_scans(db, base_scan.id, target_scan.id)

        assert comparison is not None
        assert comparison["summary"]["cost_delta_usd"] == 300.0
        assert comparison["summary"]["debt_score_delta"] == 0.8
        assert comparison["added_findings"][0]["id"] == "added"
        assert comparison["removed_findings"][0]["id"] == "removed"
        assert comparison["severity_changed"][0]["id"] == "shared"
    finally:
        db.close()


def test_finding_triage_workflow() -> None:
    """Structured findings should support suppression and reviewer feedback."""
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        analysis = {
            "total_cost_usd": 500.0,
            "debt_score": 1.5,
            "total_remediation_hours": 5.0,
            "total_remediation_sprints": 0.1,
            "cost_by_category": {},
            "hourly_rates": {"blended_rate": 85.0, "confidence": "medium"},
            "repo_profile": {
                "tech_stack": {"primary_language": "py", "frameworks": ["flask"]},
                "team": {"estimated_team_size": 2, "bus_factor": 1, "repo_age_days": 200},
                "multipliers": {"combined_multiplier": 1.0},
            },
            "debt_items": [],
            "findings": [
                {
                    "id": "triage-1",
                    "file_path": "app/service.py",
                    "module": "app",
                    "category": "code_quality",
                    "subcategory": "complexity_hotspot",
                    "symbol_name": "handle",
                    "line_start": 10,
                    "line_end": 10,
                    "severity": "medium",
                    "business_impact": "medium",
                    "effort_hours": 2.0,
                    "cost_usd": 150.0,
                    "confidence": 0.8,
                    "source_tool": "git+static",
                    "status": "open",
                    "evidence": [],
                }
            ],
            "module_summaries": [],
            "roadmap": {},
        }

        scan = save_scan(
            db=db,
            job_id="job-triage",
            github_url="https://github.com/pallets/flask",
            analysis=analysis,
            agent_state={"raw_analysis": analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )

        suppression = suppress_finding(
            db,
            scan.id,
            "triage-1",
            reason="Known and intentionally deferred",
            created_by="tester",
        )
        feedback = add_finding_feedback(
            db,
            scan.id,
            "triage-1",
            feedback_type="accepted_risk",
            severity_override="low",
            notes="Covered by team roadmap",
            created_by="tester",
        )

        finding_record = get_finding_record(db, scan.id, "triage-1")
        findings = get_scan_findings(db, scan.id)

        assert suppression is not None
        assert feedback is not None
        assert finding_record is not None
        assert finding_record.status in {"suppressed", "reviewed"}
        assert findings is not None
        assert findings[0]["suppressed"] is True
        assert findings[0]["feedback"][0]["feedback_type"] == "accepted_risk"
    finally:
        db.close()


def test_repo_rollups_surface_summary_triage_and_unresolved() -> None:
    """Repo-level rollups should reflect latest triage state and unresolved work."""
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        github_url = "https://github.com/pallets/flask"
        findings = [
            {
                "id": "repo-open-critical",
                "file_path": "app/core.py",
                "module": "app",
                "category": "architecture",
                "subcategory": "dependency_cycle",
                "symbol_name": None,
                "line_start": 1,
                "line_end": 1,
                "severity": "critical",
                "business_impact": "high",
                "effort_hours": 8.0,
                "cost_usd": 600.0,
                "confidence": 0.9,
                "source_tool": "architecture",
                "status": "open",
                "evidence": [],
            },
            {
                "id": "repo-reviewed",
                "file_path": "app/service.py",
                "module": "app",
                "category": "code_quality",
                "subcategory": "complexity_hotspot",
                "symbol_name": "handle",
                "line_start": 10,
                "line_end": 10,
                "severity": "medium",
                "business_impact": "medium",
                "effort_hours": 3.0,
                "cost_usd": 180.0,
                "confidence": 0.8,
                "source_tool": "git+static",
                "status": "reviewed",
                "evidence": [],
            },
            {
                "id": "repo-suppressed",
                "file_path": "app/docs.py",
                "module": "app",
                "category": "documentation",
                "subcategory": "missing_docstring",
                "symbol_name": None,
                "line_start": 2,
                "line_end": 2,
                "severity": "high",
                "business_impact": "low",
                "effort_hours": 1.0,
                "cost_usd": 40.0,
                "confidence": 0.7,
                "source_tool": "ast",
                "status": "open",
                "evidence": [],
            },
        ]
        roadmap = {
            "quick_wins": [
                {
                    "finding_id": "repo-suppressed",
                    "title": "Improve docs in app/docs.py",
                    "file_path": "app/docs.py",
                    "module": "app",
                    "severity": "high",
                    "business_impact": "low",
                    "effort_hours": 1.0,
                    "cost_usd": 40.0,
                    "confidence": 0.7,
                }
            ],
            "next_up": [],
            "strategic": [
                {
                    "finding_id": "repo-open-critical",
                    "title": "Break architecture cycle",
                    "file_path": "app/core.py",
                    "module": "app",
                    "severity": "critical",
                    "business_impact": "high",
                    "effort_hours": 8.0,
                    "cost_usd": 600.0,
                    "confidence": 0.9,
                }
            ],
        }

        analysis = _build_repo_analysis(findings, roadmap)
        analysis["ownership_summary"] = {
            "commit_sample_size": 14,
            "unique_contributors": 3,
            "active_contributors_90d": 2,
            "bus_factor": 1,
            "top_contributor_share": 0.78,
            "siloed_hotspots": 1,
            "handoff_hotspots": 0,
        }
        scan = save_scan(
            db=db,
            job_id="job-rollups",
            github_url=github_url,
            analysis=analysis,
            agent_state={"raw_analysis": analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )

        suppress_finding(
            db,
            scan.id,
            "repo-suppressed",
            reason="Accepted documentation gap",
            created_by="tester",
        )

        triage = get_repo_triage_stats(db, github_url)
        unresolved = get_repo_unresolved_findings(db, github_url, limit=10)
        summary = get_repo_summary_rollup(db, github_url)

        assert triage is not None
        assert triage["total_findings"] == 3
        assert triage["active_findings"] == 1
        assert triage["suppressed_findings"] == 1
        assert triage["reviewed_findings"] == 1
        assert triage["by_category"]["architecture"] == 1

        assert unresolved is not None
        assert len(unresolved) == 1
        assert unresolved[0]["id"] == "repo-open-critical"

        assert summary is not None
        assert summary["finding_count"] == 3
        assert summary["quick_wins"] == 1
        assert summary["strategic_items"] == 1
        assert summary["ownership_summary"]["unique_contributors"] == 3
        assert summary["triage"]["suppressed_findings"] == 1
        assert summary["top_modules"][0]["module"] == "app"
    finally:
        db.close()


def test_repo_change_rollup_tracks_new_existing_and_resolved_debt() -> None:
    """Repo change rollups should separate new, existing, and resolved findings."""
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        github_url = "https://github.com/pallets/flask"
        base_findings = [
            {
                "id": "shared-worse",
                "file_path": "app/service.py",
                "module": "app",
                "category": "code_quality",
                "subcategory": "complexity_hotspot",
                "symbol_name": "handle",
                "line_start": 10,
                "line_end": 10,
                "severity": "medium",
                "business_impact": "medium",
                "effort_hours": 3.0,
                "cost_usd": 200.0,
                "confidence": 0.8,
                "source_tool": "git+static",
                "status": "open",
                "evidence": [],
            },
            {
                "id": "resolved-doc",
                "file_path": "app/docs.py",
                "module": "app",
                "category": "documentation",
                "subcategory": "missing_docstring",
                "symbol_name": None,
                "line_start": 3,
                "line_end": 3,
                "severity": "low",
                "business_impact": "low",
                "effort_hours": 1.0,
                "cost_usd": 40.0,
                "confidence": 0.7,
                "source_tool": "ast",
                "status": "open",
                "evidence": [],
            },
        ]
        latest_findings = [
            {
                **base_findings[0],
                "severity": "high",
                "cost_usd": 260.0,
            },
            {
                "id": "new-architecture",
                "file_path": "app/core.py",
                "module": "app",
                "category": "architecture",
                "subcategory": "dependency_cycle",
                "symbol_name": None,
                "line_start": 1,
                "line_end": 1,
                "severity": "critical",
                "business_impact": "high",
                "effort_hours": 8.0,
                "cost_usd": 500.0,
                "confidence": 0.9,
                "source_tool": "architecture",
                "status": "open",
                "evidence": [],
            },
        ]

        base_analysis = _build_repo_analysis(base_findings)
        latest_analysis = _build_repo_analysis(latest_findings)
        base_analysis["debt_score"] = 1.9
        latest_analysis["debt_score"] = 3.2

        save_scan(
            db=db,
            job_id="job-changes-base",
            github_url=github_url,
            analysis=base_analysis,
            agent_state={"raw_analysis": base_analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )
        save_scan(
            db=db,
            job_id="job-changes-latest",
            github_url=github_url,
            analysis=latest_analysis,
            agent_state={"raw_analysis": latest_analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )

        changes = get_repo_change_rollup(db, github_url)
        summary = get_repo_summary_rollup(db, github_url)

        assert changes is not None
        assert changes["summary"]["finding_count_delta"] == 0
        assert changes["new_debt"]["count"] == 1
        assert changes["new_debt"]["items"][0]["id"] == "new-architecture"
        assert changes["existing_debt"]["count"] == 1
        assert changes["existing_debt"]["items"][0]["id"] == "shared-worse"
        assert changes["resolved_debt"]["count"] == 1
        assert changes["resolved_debt"]["items"][0]["id"] == "resolved-doc"
        assert changes["severity_worsened"][0]["id"] == "shared-worse"
        assert changes["category_deltas"]["architecture"]["new"] == 1
        assert changes["category_deltas"]["documentation"]["resolved"] == 1

        assert summary is not None
        assert summary["changes"] is not None
        assert summary["changes"]["new_debt"]["count"] == 1
    finally:
        db.close()


def test_rich_repo_trend_includes_active_category_and_module_views() -> None:
    """Rich repo trends should expose active, category, and module history."""
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        github_url = "https://github.com/pallets/flask"
        first_findings = [
            {
                "id": "trend-shared",
                "file_path": "app/service.py",
                "module": "app",
                "category": "code_quality",
                "subcategory": "complexity_hotspot",
                "symbol_name": "handle",
                "line_start": 10,
                "line_end": 10,
                "severity": "medium",
                "business_impact": "medium",
                "effort_hours": 3.0,
                "cost_usd": 150.0,
                "confidence": 0.8,
                "source_tool": "git+static",
                "status": "open",
                "evidence": [],
            },
            {
                "id": "trend-docs",
                "file_path": "app/docs.py",
                "module": "app",
                "category": "documentation",
                "subcategory": "missing_docstring",
                "symbol_name": None,
                "line_start": 1,
                "line_end": 1,
                "severity": "low",
                "business_impact": "low",
                "effort_hours": 1.0,
                "cost_usd": 30.0,
                "confidence": 0.6,
                "source_tool": "ast",
                "status": "open",
                "evidence": [],
            },
        ]
        second_findings = [
            {
                **first_findings[0],
                "severity": "high",
                "cost_usd": 220.0,
            },
            {
                "id": "trend-arch",
                "file_path": "core/cycle.py",
                "module": "core",
                "category": "architecture",
                "subcategory": "dependency_cycle",
                "symbol_name": None,
                "line_start": 1,
                "line_end": 1,
                "severity": "high",
                "business_impact": "high",
                "effort_hours": 5.0,
                "cost_usd": 300.0,
                "confidence": 0.9,
                "source_tool": "architecture",
                "status": "open",
                "evidence": [],
            },
        ]

        first_analysis = _build_repo_analysis(first_findings)
        second_analysis = _build_repo_analysis(
            second_findings,
            roadmap={"quick_wins": [], "strategic": []},
        )

        first_scan = save_scan(
            db=db,
            job_id="job-trend-1",
            github_url=github_url,
            analysis=first_analysis,
            agent_state={"raw_analysis": first_analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )
        save_scan(
            db=db,
            job_id="job-trend-2",
            github_url=github_url,
            analysis=second_analysis,
            agent_state={"raw_analysis": second_analysis, "status": "complete"},
            duration_seconds=1.0,
            user_id=None,
        )

        suppress_finding(
            db,
            first_scan.id,
            "trend-docs",
            reason="Deferred docs cleanup",
            created_by="tester",
        )

        trend = get_rich_repo_trend(db, github_url)

        assert trend["total_scans"] == 2
        assert len(trend["active_trend"]) == 2
        assert trend["active_trend"][0]["active_finding_count"] == 1
        assert trend["active_trend"][1]["active_finding_count"] == 2
        assert trend["latest_active"]["active_cost_usd"] == 520.0
        assert trend["category_trends"]["code_quality"][0]["count"] == 1
        assert trend["category_deltas"]["architecture"]["count_delta"] == 0
        assert trend["category_deltas"]["documentation"]["count_delta"] == 0
        assert trend["module_trends"]["app"][1]["finding_count"] == 1
        assert trend["module_deltas"]["core"]["finding_count_delta"] == 0
    finally:
        db.close()


def test_main_app_includes_extracted_route_groups() -> None:
    """Main app should expose extracted portfolio, report, and integration routes."""
    from main import app

    route_paths = {getattr(route, "path", "") for route in app.routes}
    assert "/portfolio" in route_paths
    assert "/portfolio/summary" in route_paths
    assert "/report/{job_id}/pdf" in route_paths
    assert "/integrations/status" in route_paths


def test_analyze_endpoint_allows_anonymous_submission(monkeypatch) -> None:
    """Anonymous users should be able to queue an analysis request."""
    import main as backend_main

    async def _fake_run_analysis_job(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(backend_main, "ORCHESTRATOR_AVAILABLE", True)
    monkeypatch.setattr(backend_main, "run_analysis_job", _fake_run_analysis_job)

    client = TestClient(backend_main.app)
    response = client.post(
        "/analyze",
        json={
            "github_url": "https://github.com/pallets/flask",
            "repo_id": "pallets/flask",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    job_id = payload["job_id"]
    assert backend_main.jobs[job_id]["user_id"] is None


def test_results_payload_stays_lightweight() -> None:
    """Polled result payloads should omit bulky raw analysis blobs."""
    from main import _normalize_result_payload

    state = {
        "raw_analysis": {
            "debt_score": 2.1,
            "total_cost_usd": 1234.0,
            "total_remediation_hours": 12.0,
            "total_remediation_sprints": 0.15,
            "cost_by_category": {"code_quality": {"cost_usd": 100.0}},
            "debt_items": [{"id": "huge"}],
            "findings": [{"id": "finding-1"}],
            "module_summaries": [{"module": "app"}],
            "roadmap": {"quick_wins": [{"id": "roadmap-1"}]},
            "ownership_summary": {"unique_contributors": 2},
            "sanity_check": {"assessment": "ok"},
            "hourly_rates": {"confidence": "medium"},
            "repo_profile": {"tech_stack": {}},
            "data_sources_used": ["BLS"],
            "llm_insights": {"provider": "local"},
        },
        "executive_summary": "Summary",
        "priority_actions": [{"rank": 1}],
        "roi_analysis": {"total_fix_cost": 1234.0},
        "llm_insights": {"provider": "local"},
    }

    payload = _normalize_result_payload("job-1", "complete", "scan-1", state)

    assert payload["job_id"] == "job-1"
    assert payload["scan_id"] == "scan-1"
    assert "raw" not in payload
    assert "raw_analysis" not in payload
    assert "debt_items" not in payload
    assert "findings" not in payload
    assert "module_summaries" not in payload
    assert "roadmap" not in payload


async def _run_semantic_triage_with_fake_llm() -> list[dict]:
    service = LocalLLMService(llm=_FakeLLM(
        '[{"finding_id":"f-1","debt_type":"architecture","justified":false,'
        '"remediation_scope":"module","action_hint":"Split the module","confidence_note":"clear structural smell"}]'
    ))
    agent = SemanticTriageAgent(service)
    return await agent.triage(
        [
            {
                "id": "f-1",
                "category": "architecture",
                "module": "app",
                "file_path": "app/core.py",
            }
        ]
    )


def test_local_llm_service_extracts_json() -> None:
    """Local LLM service should extract fenced JSON correctly."""
    service = LocalLLMService(llm=_FakeLLM("```json\n{\"ok\":true}\n```"))
    import asyncio

    parsed = asyncio.run(service.invoke_json("ignored"))
    assert parsed == {"ok": True}


def test_local_llm_service_times_out_cleanly(monkeypatch) -> None:
    """Local LLM service should fall back cleanly when the model stalls."""
    import asyncio

    monkeypatch.setenv("LOCAL_LLM_TIMEOUT_SECONDS", "0.01")
    service = LocalLLMService(llm=_SlowFakeLLM())

    parsed = asyncio.run(service.invoke_json("ignored"))
    assert parsed is None


def test_semantic_triage_agent_uses_structured_llm_output() -> None:
    """Semantic triage should normalize structured local-LLM output."""
    import asyncio

    triage = asyncio.run(_run_semantic_triage_with_fake_llm())
    assert triage[0]["finding_id"] == "f-1"
    assert triage[0]["remediation_scope"] == "module"
    assert triage[0]["action_hint"] == "Split the module"


def test_report_writer_falls_back_when_llm_unavailable() -> None:
    """Report writer should generate deterministic fallback outputs on LLM failure."""
    import asyncio

    service = LocalLLMService(llm=_FakeLLM("", should_fail=True))
    writer = ReportWriterAgent(service)
    analysis = {
        "total_cost_usd": 1200.0,
        "debt_score": 3.2,
        "total_remediation_hours": 18.0,
        "module_summaries": [{"module": "app"}],
    }
    insights = {"architecture_review": {"summary": "Architecture risk is concentrated in app."}}

    summary = asyncio.run(writer.executive_summary(analysis, insights))
    priorities = asyncio.run(
        writer.priority_actions(
            [
                {
                    "id": "f-1",
                    "category": "architecture",
                    "module": "app",
                    "file_path": "app/core.py",
                    "effort_hours": 5.0,
                    "cost_usd": 500.0,
                }
            ],
            [{"finding_id": "f-1", "action_hint": "Split responsibilities"}],
        )
    )

    assert "app" in summary
    assert priorities[0]["file_or_module"] == "app"
    assert priorities[0]["why"] == "Split responsibilities"
