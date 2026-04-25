"""Tech Debt Quantifier - FastAPI backend server."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

load_dotenv()

from api.deps import (
    get_current_user,
    get_current_user_optional,
    get_github_access_token_optional,
)
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
from mcp_server import REPOS_DIR
from models.schemas import AnalyzeRequest, AnalyzeResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
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
_result_cache: dict[str, tuple[dict[str, Any], datetime]] = {}

CACHE_TTL_MINUTES = 30
REQUEST_TIMEOUT_SECONDS = 300
CLONE_TIMEOUT_SECONDS = int(os.getenv("ANALYSIS_CLONE_TIMEOUT_SECONDS", "180"))
ANALYSIS_TIMEOUT_SECONDS = 90
LLM_TIMEOUT_SECONDS = int(os.getenv("REPORT_TIMEOUT_SECONDS", "180"))

PHASES = [
    (5, "Cloning repository"),
    (20, "Scanning files"),
    (40, "Analyzing code patterns"),
    (60, "Estimating costs"),
    (80, "Generating report"),
    (95, "Finalizing"),
]

CACHED_REPOS_DIR = REPOS_DIR.resolve()


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Fail long-running HTTP requests with a consistent 504 response."""

    async def dispatch(self, request, call_next):  # type: ignore[override]
        start = time.time()
        try:
            return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            elapsed = time.time() - start
            logger.error("Request timed out after %.1fs: %s", elapsed, request.url.path)
            return JSONResponse(
                {"error": f"Request timed out after {elapsed:.0f}s"},
                status_code=504,
            )


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def normalize_analysis_result(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure analysis results always match the frontend's expected shape."""
    payload = raw if isinstance(raw, dict) else {}

    debt_items = payload.get("debt_items") or []
    if not isinstance(debt_items, list):
        debt_items = []

    normalized_items: list[dict[str, Any]] = []
    for item in debt_items:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "file": str(item.get("file") or "unknown"),
                "category": str(item.get("category") or "code_quality"),
                "severity": str(item.get("severity") or "medium").lower(),
                "cost_usd": _safe_float(item.get("cost_usd")),
                "base_cost_usd": _safe_float(item.get("base_cost_usd")),
                "base_minutes": _safe_float(item.get("base_minutes")),
                "adjusted_minutes": _safe_float(item.get("adjusted_minutes")),
                "hourly_rate": _safe_float(item.get("hourly_rate"), 85.0),
                "combined_multiplier": _safe_float(
                    item.get("combined_multiplier"), 1.0
                ),
                "complexity": item.get("complexity"),
                "function": item.get("function"),
                "cost_factors": item.get("cost_factors") or [],
                "cost_explanation": item.get("cost_explanation") or "",
            }
        )

    raw_cats = payload.get("cost_by_category") or {}
    if not isinstance(raw_cats, dict):
        raw_cats = {}

    normalized_cats: dict[str, dict[str, Any]] = {}
    for key, value in raw_cats.items():
        if isinstance(value, dict):
            normalized_cats[key] = {
                "cost_usd": _safe_float(value.get("cost_usd")),
                "count": _safe_int(value.get("count") or value.get("item_count")),
                "hours": _safe_float(value.get("hours")),
                "item_count": _safe_int(value.get("item_count") or value.get("count")),
            }
        elif isinstance(value, (int, float)):
            normalized_cats[key] = {
                "cost_usd": float(value),
                "count": 0,
                "hours": 0.0,
                "item_count": 0,
            }

    total_cost = _safe_float(payload.get("total_cost_usd"))
    if total_cost == 0 and normalized_items:
        total_cost = sum(item["cost_usd"] for item in normalized_items)

    total_hours = _safe_float(payload.get("total_remediation_hours"))
    if total_hours == 0 and normalized_items:
        total_hours = sum(item["adjusted_minutes"] for item in normalized_items) / 60

    return {
        **payload,
        "debt_score": _safe_float(payload.get("debt_score")),
        "total_cost_usd": total_cost,
        "total_remediation_hours": total_hours,
        "total_remediation_sprints": _safe_float(
            payload.get("total_remediation_sprints")
        ),
        "debt_items": normalized_items,
        "cost_by_category": normalized_cats,
        "executive_summary": str(payload.get("executive_summary") or ""),
        "recommendations": payload.get("recommendations") or [],
        "priority_actions": payload.get("priority_actions") or [],
        "roi_analysis": payload.get("roi_analysis") or {},
        "repo_profile": payload.get("repo_profile") or {},
        "hourly_rates": payload.get("hourly_rates") or {},
        "sanity_check": payload.get("sanity_check") or {},
        "data_sources_used": payload.get("data_sources_used") or [],
        "findings": payload.get("findings") if isinstance(payload.get("findings"), list) else [],
        "module_summaries": (
            payload.get("module_summaries")
            if isinstance(payload.get("module_summaries"), list)
            else []
        ),
        "roadmap": payload.get("roadmap") if isinstance(payload.get("roadmap"), dict) else {},
    }


def get_cached_result(github_url: str) -> dict[str, Any] | None:
    """Return a recent cached analysis for the repository, if available."""
    key = hashlib.md5(github_url.encode("utf-8")).hexdigest()
    cached = _result_cache.get(key)
    if not cached:
        return None

    result, cached_at = cached
    if datetime.now(timezone.utc) - cached_at < timedelta(minutes=CACHE_TTL_MINUTES):
        logger.info("Cache hit for %s", github_url)
        return result

    _result_cache.pop(key, None)
    return None


def set_cached_result(github_url: str, result: dict[str, Any]) -> None:
    """Store a recent successful result for a repository."""
    key = hashlib.md5(github_url.encode("utf-8")).hexdigest()
    _result_cache[key] = (result, datetime.now(timezone.utc))


def update_progress(job_id: str, pct: int, phase: str) -> None:
    """Update in-memory job progress for polling clients."""
    if job_id not in jobs:
        return
    jobs[job_id]["progress"] = pct
    jobs[job_id]["phase"] = phase
    logger.info("Job %s: %s%% - %s", job_id, pct, phase)


async def run_with_timeout(
    coro_or_func: Any, timeout_seconds: int = 120, *args: Any, **kwargs: Any
) -> Any:
    """Run a sync or async callable with an explicit timeout."""
    name = getattr(coro_or_func, "__qualname__", None) or getattr(
        coro_or_func, "__name__", coro_or_func.__class__.__name__
    )
    try:
        if asyncio.iscoroutinefunction(coro_or_func):
            return await asyncio.wait_for(
                coro_or_func(*args, **kwargs),
                timeout=timeout_seconds,
            )

        if asyncio.iscoroutine(coro_or_func):
            return await asyncio.wait_for(coro_or_func, timeout=timeout_seconds)

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: coro_or_func(*args, **kwargs)),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"{name} timed out after {timeout_seconds}s") from exc


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
    raw_analysis = normalize_analysis_result(raw_analysis)
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
        "raw_analysis": raw_analysis,
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


def _extract_scan_analysis_payload(scan: Scan) -> dict[str, Any]:
    """Return the normalized analysis object stored inside a persisted scan."""
    raw_result = scan.raw_result or {}
    if not isinstance(raw_result, dict):
        return normalize_analysis_result({})

    raw_analysis = raw_result.get("raw_analysis")
    if isinstance(raw_analysis, dict):
        return normalize_analysis_result(raw_analysis)

    return normalize_analysis_result(raw_result)


app = FastAPI(
    title="Tech Debt Quantifier",
    version="0.2.0",
    description="Agentic AI platform for technical debt analysis",
)

app.add_middleware(TimeoutMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
    ],
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
        "status": "ok",
        "version": "1.0.0",
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
    github_access_token: str | None = Depends(get_github_access_token_optional),
) -> AnalyzeResponse:
    """Queue an async repository analysis job."""
    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(503, "Analysis engine not loaded.")
    if "github.com" not in request.github_url:
        raise HTTPException(400, "Must be a github.com URL")

    job_id = str(uuid.uuid4())
    repo_id = normalize_repo_id(request.repo_id or request.github_url)
    cached = get_cached_result(request.github_url)
    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "phase": "Queued",
        "result": None,
        "error": None,
        "github_url": request.github_url,
        "user_id": user.id if user else None,
        "github_access_token": github_access_token,
    }
    if cached:
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["phase"] = "Cached result ready"
        jobs[job_id]["result"] = cached
        return AnalyzeResponse(
            job_id=job_id,
            status="complete",
            message=f"Analysis cache hit. Poll GET /results/{job_id} for results.",
        )

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
        github_access_token,
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
    github_access_token: str | None = None,
) -> None:
    """Run a full analysis pipeline in the background and persist the scan."""
    start_time = time.time()
    repo_path: str | None = None
    try:
        from agents.analyzer import AnalyzerAgent
        from agents.crawler import CrawlerAgent
        from agents.reporter import ReporterAgent

        jobs[job_id]["status"] = "processing"
        jobs[job_id]["error"] = None
        update_progress(job_id, *PHASES[0])

        state: dict[str, Any] = {
            "github_url": github_url,
            "repo_id": repo_id,
            "github_access_token": github_access_token,
            "repo_path": None,
            "clone_status": None,
            "raw_analysis": None,
            "repo_profile": None,
            "findings": None,
            "module_summaries": None,
            "roadmap": None,
            "executive_summary": None,
            "priority_actions": None,
            "roi_analysis": None,
            "llm_insights": None,
            "job_id": job_id,
            "status": "queued",
            "error": None,
            "messages": [],
        }

        crawler = CrawlerAgent()
        analyzer = AnalyzerAgent()
        reporter = ReporterAgent()

        state = await run_with_timeout(crawler.run, CLONE_TIMEOUT_SECONDS, state)
        if state.get("status") == "failed":
            raise RuntimeError(state.get("error") or "Repository clone failed")

        repo_path = state.get("repo_path")
        jobs[job_id]["repo_path"] = repo_path
        update_progress(job_id, *PHASES[1])
        update_progress(job_id, *PHASES[2])
        state = await run_with_timeout(analyzer.run, ANALYSIS_TIMEOUT_SECONDS, state)
        if state.get("status") == "failed":
            raise RuntimeError(state.get("error") or "Analysis pipeline failed")

        update_progress(job_id, *PHASES[3])
        update_progress(job_id, *PHASES[4])
        state = await run_with_timeout(reporter.run, LLM_TIMEOUT_SECONDS, state)
        if state.get("status") == "failed":
            raise RuntimeError(state.get("error") or "Report generation failed")

        duration = time.time() - start_time
        raw_analysis = normalize_analysis_result(state.get("raw_analysis"))
        state["raw_analysis"] = raw_analysis
        state["status"] = "complete"

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["result"] = state
        update_progress(job_id, *PHASES[5])
        jobs[job_id]["progress"] = 100
        jobs[job_id]["phase"] = "Complete"
        set_cached_result(github_url, state)

        analysis_data = state.get("raw_analysis") or state
        if analysis_data.get("total_cost_usd"):
            try:
                db = SessionLocal()
                saved_scan = save_scan(
                    db=db,
                    job_id=job_id,
                    github_url=github_url,
                    analysis=analysis_data,
                    agent_state=state,
                    duration_seconds=duration,
                    user_id=user_id,
                )
                jobs[job_id]["scan_id"] = saved_scan.id
                logger.info("Scan saved to DB: %s", saved_scan.id)
                db.close()
            except Exception as db_err:
                logger.error("DB save failed (analysis still ok): %s", db_err)

        logger.info("Job %s completed in %.1fs", job_id, duration)
    except TimeoutError as exc:
        logger.error("Job %s timed out: %s", job_id, exc)
        logger.error(traceback.format_exc())
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = f"Analysis timed out: {exc}"
    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc)
        logger.error(traceback.format_exc())
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
    finally:
        jobs[job_id]["progress"] = min(int(jobs[job_id].get("progress") or 0), 100)
        if jobs[job_id]["status"] not in {"complete", "error"}:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = jobs[job_id].get("error") or "Analysis did not complete"
        try:
            repo_path = jobs[job_id].get("repo_path") or repo_path
            if repo_path and os.path.exists(repo_path):
                resolved_repo_path = os.path.abspath(repo_path)
                common = os.path.commonpath([resolved_repo_path, str(CACHED_REPOS_DIR)])
                if common == str(CACHED_REPOS_DIR):
                    logger.info(
                        "Preserving cached repository for job %s at %s",
                        job_id,
                        resolved_repo_path,
                    )
                else:
                    shutil.rmtree(repo_path, ignore_errors=True)
        except Exception:
            logger.warning("Failed to clean repo path for job %s", job_id)


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> dict[str, Any]:
    """Poll a queued analysis job for updates or final results."""
    if job_id not in jobs:
        try:
            db = SessionLocal()
            scan = db.query(Scan).filter(Scan.job_id == job_id).first()
            if scan:
                raw_result = scan.raw_result or {}
                raw_analysis = _extract_scan_analysis_payload(scan)
                result_data = {
                    "job_id": job_id,
                    "status": "complete",
                    "scan_id": scan.id,
                    "debt_score": raw_analysis.get("debt_score") or scan.debt_score or 0,
                    "total_cost_usd": raw_analysis.get("total_cost_usd") or scan.total_cost_usd or 0,
                    "total_remediation_hours": raw_analysis.get("total_remediation_hours") or scan.total_hours or 0,
                    "total_remediation_sprints": raw_analysis.get("total_remediation_sprints") or scan.total_sprints or 0,
                    "cost_by_category": raw_analysis.get("cost_by_category") or scan.cost_by_category or {},
                    "raw_analysis": raw_analysis,
                    "ownership_summary": raw_analysis.get("ownership_summary", {}),
                    "executive_summary": scan.executive_summary or "",
                    "priority_actions": raw_result.get("priority_actions") or scan.priority_actions or [],
                    "roi_analysis": raw_result.get("roi_analysis") or scan.roi_analysis or {},
                    "repo_profile": raw_analysis.get("repo_profile", {}),
                }
                db.close()
                return result_data
            db.close()
        except Exception:
            pass
        raise HTTPException(404, f"Job {job_id} not found")

    job = jobs[job_id]
    if job["status"] == "complete":
        result = _normalize_result_payload(
            job_id,
            "complete",
            job.get("scan_id"),
            job["result"],
        )
        if not result.get("total_cost_usd") and job.get("scan_id"):
            try:
                db = SessionLocal()
                scan = db.query(Scan).filter(Scan.id == job["scan_id"]).first()
                if scan and scan.total_cost_usd:
                    raw_analysis = _extract_scan_analysis_payload(scan)
                    result["total_cost_usd"] = scan.total_cost_usd
                    result["debt_score"] = scan.debt_score or result.get("debt_score", 0)
                    result["total_remediation_hours"] = scan.total_hours or result.get("total_remediation_hours", 0)
                    result["total_remediation_sprints"] = scan.total_sprints or result.get("total_remediation_sprints", 0)
                    result["cost_by_category"] = scan.cost_by_category or result.get("cost_by_category", {})
                    result["raw_analysis"] = raw_analysis
                    result["repo_profile"] = raw_analysis.get("repo_profile", result.get("repo_profile", {}))
                    result["priority_actions"] = (
                        (scan.raw_result or {}).get("priority_actions")
                        or scan.priority_actions
                        or result.get("priority_actions", [])
                    )
                    result["roi_analysis"] = (
                        (scan.raw_result or {}).get("roi_analysis")
                        or scan.roi_analysis
                        or result.get("roi_analysis", {})
                    )
                    if scan.executive_summary and not result.get("executive_summary"):
                        result["executive_summary"] = scan.executive_summary
                db.close()
            except Exception:
                pass
        return result
    if job["status"] in {"failed", "error"}:
        return {
            "job_id": job_id,
            "status": "error",
            "error": job.get("error"),
            "progress": job.get("progress", 0),
            "phase": job.get("phase", ""),
        }
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "phase": job.get("phase", ""),
    }


@app.get("/status/{job_id}")
async def get_status(job_id: str) -> dict[str, Any]:
    """Return lightweight job status and progress, including DB fallback."""
    if job_id not in jobs:
        try:
            db = SessionLocal()
            scan = db.query(Scan).filter(Scan.job_id == job_id).first()
            db.close()
            if scan:
                return {
                    "job_id": job_id,
                    "status": scan.status or "complete",
                    "progress": 100,
                    "phase": "Complete",
                }
        except Exception as exc:
            logger.warning("DB lookup failed for %s: %s", job_id, exc)
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "progress": job.get("progress", 0),
        "error": job.get("error"),
        "phase": job.get("phase", ""),
    }


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
