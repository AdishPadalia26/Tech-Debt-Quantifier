"""Repository and history routes."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from database.connection import DB_AVAILABLE, SessionLocal
from database.models import User
from database.crud import (
    get_all_repositories,
    get_debt_trend,
    get_repo_change_rollup,
    get_repo_summary_rollup,
    get_repo_triage_stats,
    get_repo_unresolved_findings,
    get_rich_repo_trend,
    get_scan_history,
)

router = APIRouter(tags=["repositories"])


@router.get("/history/{repo_url:path}")
async def get_repo_history(repo_url: str, user: User = Depends(get_current_user)):
    """Get scan history and trend for a repo."""
    if not repo_url.startswith("http"):
        repo_url = f"https://{repo_url}"

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        history = get_scan_history(db, repo_url, user_id=user.id, limit=10)
        trend = get_debt_trend(db, repo_url, user_id=user.id)

        scans = [
            {
                "scan_id": scan.id,
                "date": scan.created_at.isoformat(),
                "date_display": scan.created_at.strftime("%b %d, %Y"),
                "total_cost": scan.total_cost_usd,
                "debt_score": scan.debt_score,
                "total_hours": scan.total_hours,
                "executive_summary": scan.executive_summary,
                "cost_by_category": scan.cost_by_category,
            }
            for scan in history
        ]

        return {
            "github_url": repo_url,
            "scans": scans,
            "trend": trend,
            "total_scans": len(scans),
        }
    finally:
        db.close()


@router.get("/history/{repo_url:path}/rich")
async def get_repo_history_rich(repo_url: str, user: User = Depends(get_current_user)):
    """Get richer trend data for a repository, including findings and roadmap counts."""
    if not repo_url.startswith("http"):
        repo_url = f"https://{repo_url}"

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        trend = get_rich_repo_trend(db, repo_url, user_id=user.id)
        return {"github_url": repo_url, **trend}
    finally:
        db.close()


@router.get("/repositories")
async def list_repositories(user: User = Depends(get_current_user)):
    """List all tracked repositories with latest metrics."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        repos = get_all_repositories(db, user_id=user.id)
        return {"repositories": repos, "total": len(repos)}
    finally:
        db.close()


@router.get("/repositories/{repo_url:path}/summary")
async def get_repository_summary(
    repo_url: str, user: User = Depends(get_current_user)
):
    """Get a high-level rollup for the latest completed repository scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        summary = get_repo_summary_rollup(db, repo_url, user_id=user.id)
        if summary is None:
            raise HTTPException(404, "No completed scans found for repository")
        return summary
    finally:
        db.close()


@router.get("/repositories/{repo_url:path}/triage")
async def get_repository_triage(
    repo_url: str, user: User = Depends(get_current_user)
):
    """Get triage metrics for the latest completed repository scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        triage = get_repo_triage_stats(db, repo_url, user_id=user.id)
        if triage is None:
            raise HTTPException(404, "No completed scans found for repository")
        return triage
    finally:
        db.close()


@router.get("/repositories/{repo_url:path}/unresolved")
async def get_repository_unresolved(
    repo_url: str,
    limit: int = 20,
    user: User = Depends(get_current_user),
):
    """Get unresolved findings from the latest completed repository scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        findings = get_repo_unresolved_findings(
            db,
            repo_url,
            user_id=user.id,
            limit=limit,
        )
        if findings is None:
            raise HTTPException(404, "No completed scans found for repository")
        return {
            "github_url": repo_url,
            "items": findings,
            "total": len(findings),
            "limit": limit,
        }
    finally:
        db.close()


@router.get("/repositories/{repo_url:path}/changes")
async def get_repository_changes(
    repo_url: str, user: User = Depends(get_current_user)
):
    """Get latest-vs-previous debt deltas for a repository."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        changes = get_repo_change_rollup(db, repo_url, user_id=user.id)
        if changes is None:
            raise HTTPException(404, "No completed scans found for repository")
        return {
            "github_url": repo_url,
            **changes,
        }
    finally:
        db.close()


@router.get("/repositories/{repo_url:path}/active-trend")
async def get_repository_active_trend(
    repo_url: str, user: User = Depends(get_current_user)
):
    """Get unresolved active debt trend data for a repository."""
    if not repo_url.startswith("http"):
        repo_url = f"https://{repo_url}"

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        trend = get_rich_repo_trend(db, repo_url, user_id=user.id)
        if not trend.get("trend"):
            raise HTTPException(404, "No completed scans found for repository")
        return {
            "github_url": repo_url,
            "active_trend": trend.get("active_trend", []),
            "latest_active": trend.get("latest_active"),
            "total_scans": trend.get("total_scans", 0),
        }
    finally:
        db.close()
