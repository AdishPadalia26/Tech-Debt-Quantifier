"""Tech Debt Quantifier - FastAPI backend server."""

from __future__ import annotations

import logging
import os
import time
import traceback
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_current_user, get_current_user_optional
from api.routes.auth import router as auth_router
from api.routes.github import router as github_router
from api.routes.integrations import (
    router as integrations_router,
    set_jobs_reference as set_integration_jobs_reference,
)
from api.routes.portfolio import router as portfolio_router
from api.routes.repositories import router as repositories_router
from api.routes.reports import (
    router as reports_router,
    set_jobs_reference as set_report_jobs_reference,
)
from api.routes.scans import router as scans_router
from database.connection import DB_AVAILABLE, SessionLocal, engine
from database.crud import save_scan
from database.models import Base, Scan, User
from models.schemas import AnalyzeRequest, AnalyzeResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from agents.orchestrator import TechDebtOrchestrator

    ORCHESTRATOR_AVAILABLE = True
    logger.info("TechDebtOrchestrator loaded successfully")
except Exception as exc:
    ORCHESTRATOR_AVAILABLE = False
    logger.error("TechDebtOrchestrator failed to load: %s", exc)
    logger.error(traceback.format_exc())

jobs: dict[str, Any] = {}


def _get_ollama_health() -> dict[str, Any]:
    """Return Ollama configuration and reachability information."""
    provider = os.getenv("LLM_PROVIDER", "not set")
    if provider != "ollama":
        return {
            "configured": False,
            "reachable": False,
            "model": None,
            "base_url": None,
            "status": "inactive",
        }

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    parsed = urlparse(base_url)
    host = parsed.netloc or parsed.path
    health_url = f"{parsed.scheme or 'http'}://{host}/api/tags"
    model = os.getenv("OLLAMA_MODEL", "qwen3.5:latest")

    try:
        response = httpx.get(health_url, timeout=3)
        reachable = response.status_code == 200
        status = "ok" if reachable else f"http_{response.status_code}"
    except Exception:
        reachable = False
        status = "unreachable"

    return {
        "configured": True,
        "reachable": reachable,
        "model": model,
        "base_url": base_url,
        "status": status,
    }


def normalize_repo_id(github_url: str) -> str:
    """Normalize repository identifiers to owner/repo."""
    url = github_url.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if url.startswith(prefix):
            url = url[len(prefix) :]
            break
    if not url.startswith("http"):
        segments = url.strip("/").split("/")
        if len(segments) >= 2:
            return f"{segments[0]}/{segments[1]}"
        return url
    parts = (
        url.replace("https://github.com/", "")
        .replace("http://github.com/", "")
        .strip("/")
        .split("/")
    )
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return "/".join(parts)


def _normalize_result_payload(
    job_id: str, status: str, scan_id: str | None, state: dict[str, Any]
) -> dict[str, Any]:
    """Normalize in-memory analysis state into a stable API payload.

    The results endpoint is polled by the frontend progress UI, so keep this
    payload intentionally lean. Detailed findings, modules, roadmap, and raw
    analysis can be fetched through scan-specific endpoints after completion.
    """
    result = state.get("result", {}) if isinstance(state, dict) else {}
    raw_analysis = (
        result.get("raw_analysis")
        or state.get("raw_analysis")
        or result
        or state
        or {}
    )
    priority_actions = result.get("priority_actions") or state.get("priority_actions") or []
    executive_summary = result.get("executive_summary") or state.get("executive_summary") or ""
    roi_analysis = result.get("roi_analysis") or state.get("roi_analysis") or {}
    llm_insights = result.get("llm_insights") or state.get("llm_insights") or raw_analysis.get("llm_insights") or {}

    return {
        "job_id": job_id,
        "status": status,
        "scan_id": scan_id,
        "debt_score": raw_analysis.get("debt_score") or 0,
        "total_cost_usd": raw_analysis.get("total_cost_usd") or 0,
        "total_remediation_hours": raw_analysis.get("total_remediation_hours") or 0,
        "total_remediation_sprints": raw_analysis.get("total_remediation_sprints") or 0,
        "cost_by_category": raw_analysis.get("cost_by_category") or {},
        "ownership_summary": raw_analysis.get("ownership_summary") or {},
        "executive_summary": executive_summary,
        "priority_actions": priority_actions,
        "roi_analysis": roi_analysis,
        "llm_insights": llm_insights,
        "sanity_check": raw_analysis.get("sanity_check") or {},
        "hourly_rates": raw_analysis.get("hourly_rates") or {},
        "repo_profile": raw_analysis.get("repo_profile") or {},
        "data_sources_used": raw_analysis.get("data_sources_used") or [],
    }


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

app.include_router(auth_router)
app.include_router(github_router)
app.include_router(portfolio_router)
app.include_router(repositories_router)
app.include_router(reports_router)
app.include_router(scans_router)
app.include_router(integrations_router)

set_report_jobs_reference(jobs)
set_integration_jobs_reference(jobs)


@app.on_event("startup")
async def startup_event() -> None:
    """Create database tables if they do not exist."""
    if DB_AVAILABLE:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables verified/created")
        except Exception as exc:
            logger.error("Table creation failed: %s", exc)
    logger.info("Database available: %s", DB_AVAILABLE)


@app.get("/")
async def health() -> dict[str, Any]:
    """Return a compact health response."""
    return {
        "status": "ok",
        "project": "Tech Debt Quantifier",
        "version": "0.2.0",
        "orchestrator_available": ORCHESTRATOR_AVAILABLE,
        "database_available": DB_AVAILABLE,
    }


@app.get("/health")
async def detailed_health() -> dict[str, Any]:
    """Return detailed API and Ollama readiness."""
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
        "ollama": _get_ollama_health(),
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_current_user_optional),
) -> AnalyzeResponse:
    """Queue an async repository analysis job."""
    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(503, "Analysis engine not loaded.")
    if "github.com" not in request.github_url:
        raise HTTPException(400, "Must be a github.com URL")

    job_id = str(uuid.uuid4())
    repo_id = normalize_repo_id(request.repo_id or request.github_url)
    jobs[job_id] = {
        "status": "queued",
        "result": None,
        "error": None,
        "github_url": request.github_url,
        "user_id": user.id if user else None,
    }
    logger.info(
        "Job %s queued for %s (user: %s)",
        job_id,
        request.github_url,
        user.id if user else "anonymous",
    )
    background_tasks.add_task(
        run_analysis_job,
        job_id,
        request.github_url,
        repo_id,
        user.id if user else None,
    )
    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis started. Poll GET /results/{job_id} for updates.",
    )


async def run_analysis_job(
    job_id: str,
    github_url: str,
    repo_id: str,
    user_id: int | None = None,
) -> None:
    """Run a full analysis pipeline in the background and persist the scan."""
    start_time = time.time()
    try:
        jobs[job_id]["status"] = "running"
        orchestrator = TechDebtOrchestrator()
        result = await orchestrator.run_analysis(github_url, repo_id)
        duration = time.time() - start_time
        jobs[job_id]["status"] = result.get("status", "complete")
        jobs[job_id]["result"] = result

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
                    user_id=user_id,
                )
                jobs[job_id]["scan_id"] = saved_scan.id
                logger.info("Scan saved to DB: %s", saved_scan.id)
                db.close()
            except Exception as db_err:
                logger.error("DB save failed (analysis still ok): %s", db_err)

        logger.info("Job %s completed in %.1fs", job_id, duration)
    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc)
        logger.error(traceback.format_exc())
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(exc)


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> dict[str, Any]:
    """Poll a queued analysis job for updates or final results."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job = jobs[job_id]
    if job["status"] == "complete":
        return _normalize_result_payload(job_id, "complete", job.get("scan_id"), job["result"])
    if job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job.get("error")}
    return {"job_id": job_id, "status": job["status"]}


@app.get("/debug/results/{job_id}")
async def debug_results(job_id: str):
    """Return raw in-memory or persisted result JSON for debugging."""
    if job_id in jobs:
        return jobs[job_id]

    db = SessionLocal()
    try:
        scan = db.query(Scan).filter(Scan.job_id == job_id).first()
    finally:
        db.close()
    if not scan:
        raise HTTPException(404, "Job not found")
    return scan.raw_result


@app.get("/debug/raw/{job_id}")
async def debug_raw(job_id: str):
    """Return raw debug information from the database or current job memory."""
    db = SessionLocal()
    try:
        scan = db.query(Scan).filter(Scan.job_id == job_id).first()
    finally:
        db.close()

    if not scan:
        if job_id in jobs:
            job_result = jobs[job_id].get("result") or {}
            return {
                "source": "memory",
                "status": jobs[job_id].get("status"),
                "result_keys": list(job_result.keys()),
                "raw_analysis_keys": list((job_result.get("raw_analysis") or {}).keys()),
                "full": job_result,
            }
        return {"error": "not found"}

    raw = scan.raw_result or {}
    return {
        "source": "database",
        "job_id": job_id,
        "debt_score_column": scan.debt_score,
        "total_cost_column": scan.total_cost_usd,
        "total_hours_column": scan.total_hours,
        "raw_result_keys": list(raw.keys()),
        "raw_analysis_keys": list((raw.get("raw_analysis") or {}).keys()),
        "raw_analysis_snapshot": {
            "debt_score": raw.get("raw_analysis", {}).get("debt_score"),
            "total_cost_usd": raw.get("raw_analysis", {}).get("total_cost_usd"),
            "total_remediation_hours": raw.get("raw_analysis", {}).get(
                "total_remediation_hours"
            ),
            "cost_by_category": raw.get("raw_analysis", {}).get("cost_by_category"),
        },
        "priority_actions": (raw.get("priority_actions") or [])[:2],
    }


@app.get("/jobs")
async def list_jobs() -> dict[str, Any]:
    """List active in-memory jobs."""
    return {
        "total": len(jobs),
        "jobs": [
            {"job_id": job_id, "status": payload["status"], "url": payload.get("github_url")}
            for job_id, payload in jobs.items()
        ],
    }


@app.get("/debug/scans")
async def debug_scans(user: User = Depends(get_current_user)):
    """Show persisted scans with normalized repository info."""
    from database.models import Repository

    db = SessionLocal()
    try:
        scans = db.query(Scan).order_by(Scan.created_at.desc()).all()
        repo_map = {repo.id: repo for repo in db.query(Repository).all()}
    finally:
        db.close()

    return {
        "count": len(scans),
        "scans": [
            {
                "id": scan.id,
                "repository_id": scan.repository_id,
                "repo_url": repo_map.get(scan.repository_id).github_url
                if repo_map.get(scan.repository_id)
                else None,
                "normalized": normalize_repo_id(
                    (scan.raw_result or {}).get("github_url")
                    or (
                        repo_map.get(scan.repository_id).github_url
                        if repo_map.get(scan.repository_id)
                        else ""
                    )
                    or ""
                ),
                "debt_score": scan.debt_score,
                "total_cost": scan.total_cost_usd,
                "github_url": (scan.raw_result or {}).get("github_url"),
                "created_at": scan.created_at.isoformat() if scan.created_at else None,
            }
            for scan in scans
        ],
    }


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
