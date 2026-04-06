"""Scan and finding routes."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from database.connection import DB_AVAILABLE, SessionLocal
from database.crud import (
    add_finding_feedback,
    compare_scans,
    get_scan_modules,
    get_scan_roadmap,
    get_scan_summary_data,
    query_scan_findings,
    suppress_finding,
)
from database.models import Scan, User
from models.schemas import FindingFeedbackRequest, FindingSuppressionRequest

router = APIRouter(tags=["scans"])


@router.get("/scan/{scan_id}")
async def get_scan(scan_id: str, user: User = Depends(get_current_user)):
    """Get a specific scan by ID."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        scan = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
        if not scan:
            raise HTTPException(404, "Scan not found")
        return {
            "scan_id": scan.id,
            "total_cost": scan.total_cost_usd,
            "debt_score": scan.debt_score,
            "executive_summary": scan.executive_summary,
            "priority_actions": scan.priority_actions,
            "roi_analysis": scan.roi_analysis,
            "llm_insights": (scan.raw_result or {}).get("llm_insights")
            or ((scan.raw_result or {}).get("raw_analysis") or {}).get("llm_insights")
            or {},
            "raw_result": scan.raw_result,
            "created_at": scan.created_at.isoformat(),
        }
    finally:
        db.close()


@router.get("/scan/{scan_id}/summary")
async def get_scan_summary(scan_id: str, user: User = Depends(get_current_user)):
    """Get normalized summary data for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        summary = get_scan_summary_data(db, scan_id, user_id=user.id)
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
    user: User = Depends(get_current_user),
):
    """Get structured findings for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        findings = query_scan_findings(
            db,
            scan_id,
            user_id=user.id,
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
    scan_id: str, user: User = Depends(get_current_user)
):
    """Get module summaries for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        modules = get_scan_modules(db, scan_id, user_id=user.id)
        if modules is None:
            raise HTTPException(404, "Scan not found")
        return {"scan_id": scan_id, "modules": modules, "total": len(modules)}
    finally:
        db.close()


@router.get("/scan/{scan_id}/roadmap")
async def get_scan_roadmap_endpoint(
    scan_id: str, user: User = Depends(get_current_user)
):
    """Get remediation roadmap buckets for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        roadmap = get_scan_roadmap(db, scan_id, user_id=user.id)
        if roadmap is None:
            raise HTTPException(404, "Scan not found")
        return {"scan_id": scan_id, "roadmap": roadmap}
    finally:
        db.close()


@router.get("/scan/compare")
async def compare_scan_endpoint(
    base_scan_id: str,
    target_scan_id: str,
    user: User = Depends(get_current_user),
):
    """Compare two scans and return deltas in cost, score, and findings."""
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
