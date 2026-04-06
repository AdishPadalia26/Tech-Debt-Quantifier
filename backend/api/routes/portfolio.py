"""Portfolio routes."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from database.connection import DB_AVAILABLE, SessionLocal
from database.models import User
from services.portfolio_service import (
    build_portfolio,
    build_portfolio_summary,
    build_portfolio_trends,
    remove_repo_from_portfolio,
)

router = APIRouter(tags=["portfolio"])


def _normalize_repo_id(github_url: str) -> str:
    """Normalize GitHub URLs to owner/repo."""
    url = github_url.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if url.startswith(prefix):
            url = url[len(prefix) :]
            break
    segments = url.strip("/").split("/")
    if len(segments) >= 2:
        return f"{segments[0]}/{segments[1]}"
    return url


@router.get("/portfolio")
async def get_portfolio(user: User = Depends(get_current_user)):
    """Return all repos ranked by debt score descending."""
    if not DB_AVAILABLE:
        raise HTTPException(503, "Database not available.")

    db = SessionLocal()
    try:
        return build_portfolio(db, user.id, _normalize_repo_id)
    finally:
        db.close()


@router.get("/portfolio/summary")
async def get_portfolio_summary(user: User = Depends(get_current_user)):
    """Aggregate stats across all tracked repos."""
    if not DB_AVAILABLE:
        raise HTTPException(503, "Database not available.")

    db = SessionLocal()
    try:
        return build_portfolio_summary(db, user.id)
    finally:
        db.close()


@router.get("/portfolio/trends")
async def get_portfolio_trends(user: User = Depends(get_current_user)):
    """Show debt score over time for all repos."""
    if not DB_AVAILABLE:
        raise HTTPException(503, "Database not available.")

    db = SessionLocal()
    try:
        return build_portfolio_trends(db, user.id)
    finally:
        db.close()


@router.delete("/portfolio/{repo_id:path}")
async def remove_from_portfolio(repo_id: str, user: User = Depends(get_current_user)):
    """Remove a repo from the user portfolio."""
    if not DB_AVAILABLE:
        raise HTTPException(503, "Database not available.")

    db = SessionLocal()
    try:
        return remove_repo_from_portfolio(db, user.id, repo_id)
    finally:
        db.close()
