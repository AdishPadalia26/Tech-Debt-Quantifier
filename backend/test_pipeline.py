"""
Full pipeline test for Tech Debt Quantifier.
Tests every component: DB, API, agents, PDF, frontend connection.
Run with: python test_pipeline.py
"""
import asyncio
import httpx
import json
import time
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

BASE_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"
TEST_REPO = "https://github.com/pallets/flask"

results = []


def test(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "passed": passed, "detail": detail})
    print(f"  [{status}]  {name}")
    if detail and not passed:
        print(f"         -> {detail}")
    elif detail and passed:
        print(f"         -> {detail}")


def section(title: str):
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


def test_database():
    section("1. DATABASE (SQLite)")
    try:
        from database.connection import SessionLocal, engine
        from sqlalchemy import inspect

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        required = ["repositories", "scans", "debt_items"]
        for t in required:
            test(f"Table '{t}' exists", t in tables)

        db = SessionLocal()
        from database.models import Scan, Repository, DebtItem
        repo_count = db.query(Repository).count()
        scan_count = db.query(Scan).count()
        item_count = db.query(DebtItem).count()
        test(
            "DB query works",
            True,
            f"{repo_count} repos, {scan_count} scans, {item_count} items",
        )

        if scan_count > 0:
            latest = db.query(Scan).order_by(Scan.created_at.desc()).first()
            test(
                "Latest scan readable",
                True,
                f"cost=${latest.total_cost_usd:,.0f} score={latest.debt_score} at {latest.created_at}",
            )
        db.close()

    except Exception as e:
        test("Database connection", False, str(e))


def test_api_health():
    section("2. BACKEND API (localhost:8000)")
    try:
        r = httpx.get(f"{BASE_URL}/", timeout=5)
        test("GET / health check", r.status_code == 200, r.json().get("status", ""))

        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        data = r.json()
        test("GET /health returns ok", r.status_code == 200)
        test(
            "Orchestrator available",
            data.get("orchestrator") == "ok",
            f"orchestrator={data.get('orchestrator')}",
        )
        test(
            "HF_TOKEN configured",
            data.get("env_vars", {}).get("HF_TOKEN") == "set",
            data.get("env_vars", {}).get("HF_TOKEN", "missing"),
        )
        test(
            "LLM provider set",
            data.get("env_vars", {}).get("LLM_PROVIDER")
            not in [None, "not set"],
            data.get("env_vars", {}).get("LLM_PROVIDER", "not set"),
        )

        r = httpx.get(f"{BASE_URL}/repositories", timeout=5)
        test(
            "GET /repositories works",
            r.status_code == 200,
            f"{r.json().get('total', 0)} repos tracked",
        )

    except httpx.ConnectError:
        test(
            "Backend running",
            False,
            "Cannot connect -- run: uvicorn main:app --reload --port 8000",
        )
        return False
    return True


def test_analysis_tools():
    section("3. ANALYSIS TOOLS")

    tools = [
        ("tools/static_analysis.py", "Static analyzer"),
        ("tools/git_mining.py", "Git miner"),
        ("tools/cost_estimator.py", "Cost estimator"),
    ]
    for path, label in tools:
        exists = os.path.exists(path)
        test(f"{label} exists", exists, path)

    try:
        from tools.cost_estimator import CostEstimator
        CostEstimator()
        test("CostEstimator imports OK", True)
    except Exception as e:
        test("CostEstimator imports OK", False, str(e))

    intel_files = [
        "intelligence/rate_agent.py",
        "intelligence/repo_profiler.py",
        "intelligence/benchmark_agent.py",
    ]
    for path in intel_files:
        test(f"{os.path.basename(path)} exists", os.path.exists(path), path)


def test_llm():
    section("4. LLM / REPORTER (HuggingFace)")

    try:
        hf_token = os.getenv("HF_TOKEN")
        test("HF_TOKEN in .env", bool(hf_token), "Get free token at huggingface.co/settings/tokens")

        llm_provider = os.getenv("LLM_PROVIDER", "not set")
        test("LLM_PROVIDER configured", llm_provider != "not set", f"LLM_PROVIDER={llm_provider}")

        model_id = os.getenv("HF_MODEL_ID", "not set")
        test("HF_MODEL_ID configured", model_id != "not set", f"Model: {model_id}")

        from agents.llm_factory import get_llm
        test("LLM factory imports OK", True)

        llm = get_llm("summary")
        test("LLM instantiates OK", llm is not None)

    except Exception as e:
        test("LLM setup", False, str(e))


def test_pdf():
    section("5. PDF GENERATOR")

    try:
        import reportlab
        test("reportlab installed", True, f"version {reportlab.Version}")
    except ImportError:
        test("reportlab installed", False, "Run: pip install reportlab pillow")
        return

    try:
        from reports.pdf_generator import TechDebtPDFGenerator
        test("PDF generator imports OK", True)

        mock_analysis = {
            "repo_path": "https://github.com/pallets/flask",
            "total_cost_usd": 131393.54,
            "debt_score": 3.5,
            "total_remediation_hours": 763.0,
            "total_remediation_sprints": 9.5,
            "cost_by_category": {
                "code_quality": {"cost_usd": 51303, "hours": 298, "item_count": 156},
                "security": {"cost_usd": 42312, "hours": 245, "item_count": 23},
                "documentation": {"cost_usd": 19106, "hours": 220, "item_count": 412},
            },
            "debt_items": [
                {
                    "file": "src/flask/app.py",
                    "function": "full_dispatch_request",
                    "category": "code_quality",
                    "severity": "high",
                    "cost_usd": 2400,
                    "adjusted_minutes": 1800,
                    "complexity": 15,
                    "churn_multiplier": 2.1,
                },
            ],
            "sanity_check": {
                "your_cost_per_function": 263,
                "variance_pct": -75.7,
                "assessment": "Below avg",
            },
            "hourly_rates": {"blended_rate": 86.23, "confidence": "high"},
            "repo_profile": {
                "tech_stack": {
                    "primary_language": "Python",
                    "frameworks": ["Flask"],
                    "ai_ml_libraries": [],
                    "databases": [],
                    "has_tests": True,
                    "has_ci_cd": True,
                },
                "team": {
                    "estimated_team_size": 523,
                    "bus_factor": 5,
                    "repo_age_days": 5475,
                },
                "multipliers": {"combined_multiplier": 1.8},
            },
            "data_sources_used": ["BLS", "DuckDuckGo", "OSV.dev"],
        }

        mock_state = {
            "github_url": "https://github.com/pallets/flask",
            "executive_summary": "Flask's technical debt totals $131,393 driven by security and code quality issues.",
            "priority_actions": [
                {
                    "rank": 1,
                    "title": "Fix security in sessions",
                    "file_or_module": "src/flask/sessions.py",
                    "why": "High security risk",
                    "estimated_hours": 28,
                    "estimated_cost": 2415,
                    "saves_per_month": 302,
                    "sprint": "Sprint 1",
                },
            ],
            "roi_analysis": {
                "total_fix_cost": 39418,
                "annual_maintenance_savings": 26279,
                "payback_months": 18,
                "3_year_roi_pct": 100,
                "recommended_budget": 9854,
                "recommendation": "Allocate $9,854/quarter.",
            },
        }

        gen = TechDebtPDFGenerator()
        pdf_bytes = gen.generate(mock_analysis, mock_state)

        test(
            "PDF generates without error",
            len(pdf_bytes) > 1000,
            f"PDF size: {len(pdf_bytes):,} bytes",
        )

        test_pdf_path = "test_report_output.pdf"
        with open(test_pdf_path, "wb") as f:
            f.write(pdf_bytes)
        test(
            "PDF saved to disk",
            os.path.exists(test_pdf_path),
            f"Saved: {test_pdf_path}",
        )

        print(f"\n  Open this file to preview the PDF:")
        print(f"     {os.path.abspath(test_pdf_path)}")

    except Exception as e:
        test("PDF generation", False, str(e))
        import traceback
        print(traceback.format_exc())


async def test_full_pipeline():
    section("6. FULL PIPELINE (End-to-End API Test)")
    print("  This triggers a real analysis -- takes 3-5 minutes...")
    print(f"  Testing with: {TEST_REPO}\n")

    async with httpx.AsyncClient(timeout=600) as client:
        try:
            r = await client.post(
                f"{BASE_URL}/analyze",
                json={"github_url": TEST_REPO, "repo_id": "flask-pipeline-test"},
            )
            test("POST /analyze accepted", r.status_code == 200, r.text[:100] if r.status_code != 200 else "")

            job_id = r.json().get("job_id")
            test("job_id returned", bool(job_id), job_id or "missing")

            if not job_id:
                return

        except Exception as e:
            test("POST /analyze", False, str(e))
            return

        print(f"\n  Polling job {job_id[:8]}... (updates every 10s)")
        start = time.time()
        status = "queued"

        while status not in ["complete", "failed"]:
            await asyncio.sleep(10)
            elapsed = int(time.time() - start)
            try:
                r = await client.get(f"{BASE_URL}/results/{job_id}")
                data = r.json()
                status = data.get("status", "unknown")
                print(f"  [{elapsed:3d}s] Status: {status}")
            except Exception as e:
                print(f"  [{elapsed:3d}s] Poll error: {e}")

            if elapsed > 600:
                test("Pipeline completes in 10min", False, "Timeout")
                return

        elapsed = int(time.time() - start)
        test(f"Pipeline completed ({elapsed}s)", status == "complete", f"Final status: {status}")

        if status != "complete":
            error = data.get("error", "Unknown")
            print(f"\n  Pipeline failed: {error}")
            return

        raw = data.get("raw", {})
        analysis = raw.get("raw_analysis") or raw

        cost = analysis.get("total_cost_usd", 0)
        score = analysis.get("debt_score", 0)
        hours = analysis.get("total_remediation_hours", 0)

        test("Total cost in range ($50k-$300k)", 50000 < cost < 300000, f"${cost:,.0f}")
        test("Debt score in range (1-9)", 1 <= score <= 9, f"{score:.1f}/10")
        test("Remediation hours > 0", hours > 0, f"{hours:.0f} hours")
        test("Executive summary generated", bool(raw.get("executive_summary")), raw.get("executive_summary", "")[:80] + "...")
        test("Priority actions generated", len(raw.get("priority_actions", [])) >= 1, f"{len(raw.get('priority_actions', []))} actions")
        test("ROI analysis generated", bool(raw.get("roi_analysis")), f"3yr ROI: {raw.get('roi_analysis', {}).get('3_year_roi_pct', 0)}%")

        categories = analysis.get("cost_by_category", {})
        test("Cost categories populated", len(categories) >= 2, f"Categories: {list(categories.keys())}")

        repo_profile = analysis.get("repo_profile", {})
        team_size = repo_profile.get("team", {}).get("estimated_team_size", 0)
        test("Team profile populated", team_size > 0, f"Team size: {team_size}")

        r = await client.get(f"{BASE_URL}/report/{job_id}/pdf", timeout=60)
        test(
            "PDF download endpoint works",
            r.status_code == 200 and len(r.content) > 5000,
            f"PDF size: {len(r.content):,} bytes",
        )

        if r.status_code == 200:
            pdf_path = "test_pipeline_report.pdf"
            with open(pdf_path, "wb") as f:
                f.write(r.content)
            print(f"\n  Full pipeline PDF saved: {os.path.abspath(pdf_path)}")

        r = await client.get(f"{BASE_URL}/history/github.com/pallets/flask")
        history = r.json()
        test(
            "Scan saved to DB",
            history.get("total_scans", 0) > 0,
            f"{history.get('total_scans', 0)} scans in history",
        )


def test_frontend():
    section("7. FRONTEND (localhost:3000)")
    try:
        r = httpx.get(FRONTEND_URL, timeout=5)
        test("Frontend accessible", r.status_code == 200, "Next.js running at localhost:3000")
    except httpx.ConnectError:
        test("Frontend running", False, "Run: cd frontend && npm run dev")


async def main():
    print("\n" + "=" * 55)
    print("  TECH DEBT QUANTIFIER -- FULL PIPELINE TEST")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    test_database()
    api_ok = test_api_health()
    test_analysis_tools()
    test_llm()
    test_pdf()
    test_frontend()

    print("\n" + "=" * 55)
    run_full = input(
        "\n  Run FULL pipeline test? (analyzes Flask repo ~5min) [y/N]: "
    ).strip().lower()

    if run_full == "y":
        if api_ok:
            await test_full_pipeline()
        else:
            print("  Skipping -- backend not running")

    print("\n" + "=" * 55)
    print("  TEST SUMMARY")
    print("=" * 55)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)

    print(f"\n  Passed: {passed}/{total}")
    print(f"  Failed: {failed}/{total}")

    if failed > 0:
        print("\n  Failed tests:")
        for r in results:
            if not r["passed"]:
                print(f"    [FAIL] {r['name']}: {r['detail']}")

    if failed == 0:
        print("\n  All tests passed! Pipeline is fully working.")
    elif failed <= 2:
        print("\n  Minor issues -- fix above then re-run")
    else:
        print("\n  Multiple failures -- review errors above")

    print()
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
