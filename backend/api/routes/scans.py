"""Scan and finding routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user, get_current_user_optional
from database.connection import DB_AVAILABLE, SessionLocal
from database.crud import (
    add_finding_feedback,
    compare_scans,
    get_scan_modules,
    get_scan_roadmap,
    get_scan_summary_data,
    query_scan_findings,
    strip_secrets,
    suppress_finding,
)
from database.models import Scan, User
from models.schemas import FindingFeedbackRequest, FindingSuppressionRequest

router = APIRouter(tags=["scans"])
logger = logging.getLogger(__name__)

# raw_result keys the frontend scan detail page reads (frontend/src/app/scans).
_LIFTED_RAW_KEYS = ("github_url", "repo_id")

# Small estimate-quality keys from raw_result["raw_analysis"] shown on the scan page.
_LIFTED_ANALYSIS_KEYS = (
    "estimation_stats",
    "warnings",
    "total_cost_range",
    "non_principal_cost",
    "waterfall",
    "model_version",
    "hourly_rates",
)


@router.get("/scan/compare")
async def compare_scan_endpoint(
    base_scan_id: str,
    target_scan_id: str,
    user: User = Depends(get_current_user),
):
    """Compare two scans and return deltas in cost, score, and findings.

    NOTE: This static route must be declared before ``/scan/{scan_id}`` so
    FastAPI does not match ``/scan/compare`` as ``scan_id="compare"``.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        comparison = compare_scans(
            db,
            base_scan_id,
            target_scan_id,
            user_id=user.id,
        )
        if comparison is None:
            raise HTTPException(404, "One or both scans not found")
        return comparison
    finally:
        db.close()


def build_scan_detail(scan: Scan, include_raw: bool = False) -> dict[str, Any]:
    """Build the GET /scan/{id} response body without leaking secrets.

    The full ``raw_result`` (~10 MB) is only included when ``include_raw`` is
    set, and is always passed through ``strip_secrets``. By default a slim
    ``raw_result`` stub with only the keys the frontend reads
    (``github_url``, ``repo_id``) is returned, and those keys are also lifted
    to the top level.

    Args:
        scan: Persisted scan row.
        include_raw: Return the full (secret-stripped) raw_result.

    Returns:
        JSON-serializable scan detail dict.
    """
    raw = scan.raw_result if isinstance(scan.raw_result, dict) else {}
    raw_analysis = raw.get("raw_analysis")
    raw_analysis = raw_analysis if isinstance(raw_analysis, dict) else {}
    lifted = {key: raw.get(key) for key in _LIFTED_RAW_KEYS}
    return {
        "scan_id": scan.id,
        "total_cost": scan.total_cost_usd,
        "debt_score": scan.debt_score,
        "executive_summary": scan.executive_summary,
        "priority_actions": scan.priority_actions,
        "roi_analysis": scan.roi_analysis,
        "llm_insights": raw.get("llm_insights")
        or raw_analysis.get("llm_insights")
        or {},
        **lifted,
        **{key: raw_analysis.get(key) for key in _LIFTED_ANALYSIS_KEYS},
        "raw_result": strip_secrets(raw) if include_raw else lifted,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
    }


@router.get("/scan/{scan_id}")
async def get_scan(
    scan_id: str,
    include_raw: bool = False,
    user: User | None = Depends(get_current_user_optional),
):
    """Get a specific scan by ID (raw_result only with ``include_raw=true``)."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        query = db.query(Scan).filter(Scan.id == scan_id)
        if user is not None:
            query = query.filter(Scan.user_id == user.id)
        else:
            query = query.filter(Scan.user_id.is_(None))
        scan = query.first()
        if not scan:
            raise HTTPException(404, "Scan not found")
        return build_scan_detail(scan, include_raw=include_raw)
    finally:
        db.close()


@router.get("/scan/{scan_id}/summary")
async def get_scan_summary(
    scan_id: str, user: User | None = Depends(get_current_user_optional)
):
    """Get normalized summary data for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        summary = get_scan_summary_data(db, scan_id, user_id=user.id if user else None)
        if summary is None:
            raise HTTPException(404, "Scan not found")
        return summary
    finally:
        db.close()


@router.get("/scan/{scan_id}/findings")
async def get_scan_findings_endpoint(
    scan_id: str,
    category: str | None = None,
    severity: str | None = None,
    module: str | None = None,
    min_confidence: float | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User | None = Depends(get_current_user_optional),
):
    """Get structured findings for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        findings = query_scan_findings(
            db,
            scan_id,
            user_id=user.id if user else None,
            category=category,
            severity=severity,
            module=module,
            min_confidence=min_confidence,
            limit=limit,
            offset=offset,
        )
        if findings is None:
            raise HTTPException(404, "Scan not found")
        return {
            "scan_id": scan_id,
            "findings": findings["items"],
            "total": findings["total"],
            "limit": findings["limit"],
            "offset": findings["offset"],
        }
    finally:
        db.close()


@router.get("/scan/{scan_id}/modules")
async def get_scan_modules_endpoint(
    scan_id: str, user: User | None = Depends(get_current_user_optional)
):
    """Get module summaries for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        modules = get_scan_modules(db, scan_id, user_id=user.id if user else None)
        if modules is None:
            raise HTTPException(404, "Scan not found")
        return {"scan_id": scan_id, "modules": modules, "total": len(modules)}
    finally:
        db.close()


@router.get("/scan/{scan_id}/roadmap")
async def get_scan_roadmap_endpoint(
    scan_id: str, user: User | None = Depends(get_current_user_optional)
):
    """Get remediation roadmap buckets for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        roadmap = get_scan_roadmap(db, scan_id, user_id=user.id if user else None)
        if roadmap is None:
            raise HTTPException(404, "Scan not found")
        return {"scan_id": scan_id, "roadmap": roadmap}
    finally:
        db.close()


@router.post("/scan/{scan_id}/findings/{finding_id}/suppress")
async def suppress_finding_endpoint(
    scan_id: str,
    finding_id: str,
    request: FindingSuppressionRequest,
    user: User = Depends(get_current_user),
):
    """Suppress a finding for the given scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        suppression = suppress_finding(
            db,
            scan_id,
            finding_id,
            reason=request.reason,
            created_by=user.login,
            user_id=user.id,
        )
        if suppression is None:
            raise HTTPException(404, "Finding not found")
        return {"scan_id": scan_id, "finding_id": finding_id, "suppression": suppression}
    finally:
        db.close()


@router.post("/scan/{scan_id}/findings/{finding_id}/feedback")
async def add_finding_feedback_endpoint(
    scan_id: str,
    finding_id: str,
    request: FindingFeedbackRequest,
    user: User = Depends(get_current_user),
):
    """Attach human feedback to a finding for the given scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        feedback = add_finding_feedback(
            db,
            scan_id,
            finding_id,
            feedback_type=request.feedback_type,
            severity_override=request.severity_override,
            notes=request.notes,
            created_by=user.login,
            user_id=user.id,
        )
        if feedback is None:
            raise HTTPException(404, "Finding not found")
        return {"scan_id": scan_id, "finding_id": finding_id, "feedback": feedback}
    finally:
        db.close()
