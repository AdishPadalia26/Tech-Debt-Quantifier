"""Analyze, results, status, and debug routes."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import (
    get_current_user,
    get_current_user_optional,
    get_github_access_token_optional,
)
from database.connection import SessionLocal
from database.models import Scan, User
from models.normalize import normalize_analysis_result
from models.schemas import AnalyzeRequest, AnalyzeResponse
from services.analysis_runner import (
    ORCHESTRATOR_AVAILABLE,
    _validate_github_url,
    get_cached_result,
    normalize_repo_id,
    run_analysis_job,
)
from services.job_service import get_job, list_jobs as list_redis_jobs, set_job, update_job

router = APIRouter()
logger = logging.getLogger(__name__)


def _normalize_result_payload(
    job_id: str, status: str, scan_id: str | None, state: dict[str, Any]
) -> dict[str, Any]:
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
    llm_insights = (
        result.get("llm_insights")
        or state.get("llm_insights")
        or raw_analysis.get("llm_insights")
        or {}
    )
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
    raw_result = scan.raw_result or {}
    if not isinstance(raw_result, dict):
        return normalize_analysis_result({})
    raw_analysis = raw_result.get("raw_analysis")
    if isinstance(raw_analysis, dict):
        return normalize_analysis_result(raw_analysis)
    return normalize_analysis_result(raw_result)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(
    request: AnalyzeRequest,
    user: User | None = Depends(get_current_user_optional),
    github_access_token: str | None = Depends(get_github_access_token_optional),
) -> AnalyzeResponse:
    """Queue an async repository analysis job."""
    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(503, "Analysis engine not loaded.")
    canonical_url = _validate_github_url(request.github_url)
    job_id = str(uuid.uuid4())
    repo_id = normalize_repo_id(request.repo_id or canonical_url)
    cached = get_cached_result(canonical_url)
    set_job(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "phase": "Queued",
            "result": None,
            "error": None,
            "github_url": canonical_url,
            "user_id": user.id if user else None,
            "github_access_token": github_access_token,
        },
    )
    if cached:
        update_job(
            job_id,
            status="complete",
            progress=100,
            phase="Cached result ready",
            result=cached,
        )
        return AnalyzeResponse(
            job_id=job_id,
            status="complete",
            message=f"Analysis cache hit. Poll GET /results/{job_id} for results.",
        )
    logger.info(
        "Job %s queued for %s (user: %s)",
        job_id,
        canonical_url,
        user.id if user else "anonymous",
    )
    # Use a daemon thread instead of BackgroundTasks to avoid anyio/asyncio
    # interference with the main event loop on Windows.
    thread = threading.Thread(
        target=run_analysis_job,
        args=(job_id, canonical_url, repo_id, user.id if user else None, github_access_token),
        daemon=True,
        name=f"analysis-{job_id[:8]}",
    )
    thread.start()
    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis started. Poll GET /results/{job_id} for updates.",
    )


@router.get("/results/{job_id}")
async def get_results(job_id: str) -> dict[str, Any]:
    """Poll a queued analysis job for updates or final results."""
    job = get_job(job_id)
    if job is None:
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

    if job["status"] == "complete":
        result = _normalize_result_payload(
            job_id, "complete", job.get("scan_id"), job["result"]
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


@router.get("/status/{job_id}")
async def get_status(job_id: str) -> dict[str, Any]:
    """Return lightweight job status and progress, including DB fallback."""
    job = get_job(job_id)
    if job is None:
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

    return {
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "progress": job.get("progress", 0),
        "error": job.get("error"),
        "phase": job.get("phase", ""),
    }


@router.get("/jobs")
async def list_jobs_endpoint() -> dict[str, Any]:
    """List active jobs from Redis."""
    all_jobs = list_redis_jobs()
    return {
        "total": len(all_jobs),
        "jobs": [
            {"job_id": j.get("job_id"), "status": j.get("status"), "url": j.get("github_url")}
            for j in all_jobs
        ],
    }


@router.get("/debug/results/{job_id}")
async def debug_results(job_id: str) -> Any:
    """Return raw in-memory or persisted result JSON for debugging."""
    job = get_job(job_id)
    if job is not None:
        return job
    db = SessionLocal()
    try:
        scan = db.query(Scan).filter(Scan.job_id == job_id).first()
    finally:
        db.close()
    if not scan:
        raise HTTPException(404, "Job not found")
    return scan.raw_result


@router.get("/debug/raw/{job_id}")
async def debug_raw(job_id: str) -> Any:
    """Return raw debug information from the database or current job memory."""
    db = SessionLocal()
    try:
        scan = db.query(Scan).filter(Scan.job_id == job_id).first()
    finally:
        db.close()

    if not scan:
        job = get_job(job_id)
        if job is not None:
            job_result = job.get("result") or {}
            return {
                "source": "redis",
                "status": job.get("status"),
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
            "total_remediation_hours": raw.get("raw_analysis", {}).get("total_remediation_hours"),
            "cost_by_category": raw.get("raw_analysis", {}).get("cost_by_category"),
        },
        "priority_actions": (raw.get("priority_actions") or [])[:2],
    }


@router.get("/debug/scans")
async def debug_scans(user: User = Depends(get_current_user)) -> Any:
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
