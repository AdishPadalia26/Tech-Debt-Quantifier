"""Tech Debt Quantifier - FastAPI Backend Server."""

import os
import uuid
import time
import logging
import traceback
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from models.schemas import AnalyzeRequest, AnalyzeResponse
from database.connection import DB_AVAILABLE, SessionLocal, engine
from database.models import Base
from database.crud import (
    save_scan,
    get_scan_history,
    get_debt_trend,
    get_all_repositories,
)

try:
    from agents.orchestrator import TechDebtOrchestrator
    ORCHESTRATOR_AVAILABLE = True
    logger.info("TechDebtOrchestrator loaded successfully")
except Exception as e:
    ORCHESTRATOR_AVAILABLE = False
    logger.error(f"TechDebtOrchestrator failed to load: {e}")
    logger.error(traceback.format_exc())

jobs: Dict[str, Any] = {}

app = FastAPI(
    title="Tech Debt Quantifier",
    version="0.2.0",
    description="Agentic AI platform for technical debt analysis",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    """Create tables if they don't exist."""
    if DB_AVAILABLE:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables verified/created")
        except Exception as e:
            logger.error(f"Table creation failed: {e}")
    logger.info(f"Database available: {DB_AVAILABLE}")


@app.get("/")
async def health() -> dict:
    return {
        "status": "ok",
        "project": "Tech Debt Quantifier",
        "version": "0.2.0",
        "orchestrator_available": ORCHESTRATOR_AVAILABLE,
        "database_available": DB_AVAILABLE,
    }


@app.get("/health")
async def detailed_health() -> dict:
    return {
        "api": "ok",
        "orchestrator": "ok" if ORCHESTRATOR_AVAILABLE else "error",
        "database": "ok" if DB_AVAILABLE else "error",
        "active_jobs": len(jobs),
        "env_vars": {
            "HF_TOKEN": "set" if os.getenv("HF_TOKEN") else "missing",
            "OPENAI_API_KEY": "set" if os.getenv("OPENAI_API_KEY") else "missing",
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "not set"),
            "DATABASE_URL": "set" if os.getenv("DATABASE_URL") else "missing",
        },
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    """Start async analysis of a GitHub repo."""

    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Analysis engine not loaded.")

    if "github.com" not in request.github_url:
        raise HTTPException(status_code=400, detail="Must be a github.com URL")

    job_id = str(uuid.uuid4())
    repo_id = request.repo_id or request.github_url.split("/")[-1]

    jobs[job_id] = {
        "status": "queued",
        "result": None,
        "error": None,
        "github_url": request.github_url,
    }

    logger.info(f"Job {job_id} queued for {request.github_url}")

    background_tasks.add_task(
        run_analysis_job,
        job_id,
        request.github_url,
        repo_id,
    )

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis started. Poll GET /results/{job_id} for updates.",
    )


async def run_analysis_job(job_id: str, github_url: str, repo_id: str) -> None:
    """Background task — runs full agent pipeline, saves to DB."""
    start_time = time.time()
    try:
        jobs[job_id]["status"] = "running"

        orchestrator = TechDebtOrchestrator()
        result = await orchestrator.run_analysis(github_url, repo_id)

        duration = time.time() - start_time
        jobs[job_id]["status"] = result.get("status", "complete")
        jobs[job_id]["result"] = result

        # Save to SQLite
        # Analysis data may be in raw_analysis or flattened into result
        analysis_data = result.get("raw_analysis") or result
        if result.get("status") != "failed" and analysis_data.get("total_cost_usd"):
            try:
                db = SessionLocal()
                saved_scan = save_scan(
                    db=db,
                    job_id=job_id,
                    github_url=github_url,
                    analysis=analysis_data,
                    agent_state=result,
                    duration_seconds=duration,
                )
                jobs[job_id]["scan_id"] = saved_scan.id
                logger.info(f"Scan saved to DB: {saved_scan.id}")
                db.close()
            except Exception as db_err:
                logger.error(f"DB save failed (analysis still ok): {db_err}")

        logger.info(f"Job {job_id}: completed in {duration:.1f}s")

    except Exception as e:
        error_msg = str(e)
        full_trace = traceback.format_exc()
        logger.error(f"Job {job_id} failed: {error_msg}")
        logger.error(full_trace)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = error_msg


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> dict:
    """Poll for analysis results."""

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = jobs[job_id]

    if job["status"] == "complete":
        result = job["result"]
        return {
            "job_id": job_id,
            "status": "complete",
            "scan_id": job.get("scan_id"),
            "raw": result,
        }

    if job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job.get("error")}

    return {"job_id": job_id, "status": job["status"]}


@app.get("/jobs")
async def list_jobs() -> dict:
    """List all in-memory jobs."""
    return {
        "total": len(jobs),
        "jobs": [
            {"job_id": jid, "status": j["status"], "url": j.get("github_url")}
            for jid, j in jobs.items()
        ],
    }


# ──────────────────────────────────────────────
# Database-backed endpoints
# ──────────────────────────────────────────────


@app.get("/history/{repo_url:path}")
async def get_repo_history(repo_url: str):
    """Get scan history and trend for a repo."""
    # repo_url comes in as: github.com/pallets/flask
    # normalize to full URL
    if not repo_url.startswith("http"):
        repo_url = f"https://{repo_url}"

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        history = get_scan_history(db, repo_url, limit=10)
        trend = get_debt_trend(db, repo_url)

        scans = [
            {
                "scan_id": s.id,
                "date": s.created_at.isoformat(),
                "date_display": s.created_at.strftime("%b %d, %Y"),
                "total_cost": s.total_cost_usd,
                "debt_score": s.debt_score,
                "total_hours": s.total_hours,
                "executive_summary": s.executive_summary,
                "cost_by_category": s.cost_by_category,
            }
            for s in history
        ]

        return {
            "github_url": repo_url,
            "scans": scans,
            "trend": trend,
            "total_scans": len(scans),
        }
    finally:
        db.close()


@app.get("/repositories")
async def list_repositories():
    """List all tracked repositories with latest metrics."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        repos = get_all_repositories(db)
        return {"repositories": repos, "total": len(repos)}
    finally:
        db.close()


@app.get("/scan/{scan_id}")
async def get_scan(scan_id: str):
    """Get a specific scan by ID."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        from database.models import Scan

        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            raise HTTPException(404, "Scan not found")
        return {
            "scan_id": scan.id,
            "total_cost": scan.total_cost_usd,
            "debt_score": scan.debt_score,
            "executive_summary": scan.executive_summary,
            "priority_actions": scan.priority_actions,
            "roi_analysis": scan.roi_analysis,
            "raw_result": scan.raw_result,
            "created_at": scan.created_at.isoformat(),
        }
    finally:
        db.close()


@app.get("/report/{scan_id}/pdf")
async def download_pdf_report(scan_id: str):
    """Download a PDF report for a specific scan."""
    from fastapi.responses import Response
    from reports.pdf_generator import TechDebtPDFGenerator

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        from database.models import Scan

        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            raise HTTPException(404, "Scan not found")

        analysis = scan.raw_result or {}
        agent_state = scan.raw_result or {}

        generator = TechDebtPDFGenerator()
        pdf_bytes = generator.generate(analysis, agent_state)

        repo_name = "report"
        if scan.repository:
            repo_name = scan.repository.repo_name or "report"

        filename = f"tech-debt-{repo_name}-{scan_id[:8]}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("Tech Debt Quantifier API Server")
    print("=" * 50)
    print(f"Database: {'available' if DB_AVAILABLE else 'unavailable'}")
    print("Server starting at: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
