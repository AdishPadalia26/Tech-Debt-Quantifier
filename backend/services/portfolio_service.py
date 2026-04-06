"""Portfolio-oriented service helpers for route handlers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Repository, Scan


def top_category(analysis: dict[str, Any]) -> str:
    """Return the highest-cost category label from an analysis payload."""
    categories = analysis.get("cost_by_category", {})
    if not categories:
        return "unknown"
    category, _ = max(
        categories.items(),
        key=lambda entry: (
            entry[1].get("cost_usd", 0) if isinstance(entry[1], dict) else 0
        ),
    )
    return category.replace("_", " ").title()


def risk_level(score: float) -> str:
    """Return a human-friendly risk level from the debt score."""
    if score >= 7:
        return "critical"
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def build_portfolio(db: Session, user_id: int, normalize_repo_id) -> dict[str, Any]:
    """Return the latest scan snapshot for each repository in a user portfolio."""
    all_scans = (
        db.query(Scan)
        .filter(Scan.user_id == user_id, Scan.status == "complete")
        .order_by(Scan.created_at.desc())
        .all()
    )
    repo_map = {
        repo.id: repo
        for repo in db.query(Repository).filter(Repository.user_id == user_id).all()
    }

    seen: dict[str, tuple[Scan, str]] = {}
    for scan in all_scans:
        raw = scan.raw_result or {}
        github_url = (
            raw.get("github_url")
            or raw.get("repo_url")
            or (repo_map.get(scan.repository_id).github_url if repo_map.get(scan.repository_id) else None)
            or ""
        )
        key = normalize_repo_id(github_url) if github_url else scan.repository_id
        if key and key not in seen:
            seen[key] = (scan, github_url)

    repos = []
    for key, (scan, github_url) in seen.items():
        raw = scan.raw_result or {}
        analysis = raw.get("raw_analysis") or raw
        profile = analysis.get("repo_profile", {}) or {}
        tech = profile.get("tech_stack", {}) or {}
        team = profile.get("team", {}) or {}

        full_url = github_url if str(github_url).startswith("http") else f"https://github.com/{key}"
        repos.append(
            {
                "repo_id": key,
                "github_url": full_url,
                "debt_score": float(scan.debt_score or 0),
                "total_cost": float(scan.total_cost_usd or 0),
                "remediation_hours": float(scan.total_hours or 0),
                "language": tech.get("primary_language", scan.primary_language or "Unknown"),
                "team_size": team.get("estimated_team_size", scan.team_size or 0),
                "bus_factor": team.get("bus_factor", scan.bus_factor or 0),
                "has_tests": tech.get("has_tests", False),
                "has_ci_cd": tech.get("has_ci_cd", False),
                "scanned_at": scan.created_at.isoformat() if scan.created_at else None,
                "top_category": top_category(analysis),
                "risk_level": risk_level(float(scan.debt_score or 0)),
            }
        )

    repos.sort(key=lambda repo: repo["debt_score"], reverse=True)
    return {"repos": repos, "total": len(repos)}


def build_portfolio_summary(db: Session, user_id: int) -> dict[str, Any]:
    """Return aggregate portfolio metrics for a user."""
    stats = (
        db.query(
            func.count(Scan.id).label("total_scans"),
            func.avg(Scan.debt_score).label("avg_score"),
            func.sum(Scan.total_cost_usd).label("total_cost"),
            func.sum(Scan.total_hours).label("total_hours"),
            func.max(Scan.debt_score).label("worst_score"),
            func.min(Scan.debt_score).label("best_score"),
        )
        .filter(Scan.user_id == user_id, Scan.status == "complete")
        .first()
    )
    unique_repos = (
        db.query(func.count(func.distinct(Scan.repository_id)))
        .filter(Scan.user_id == user_id, Scan.status == "complete")
        .scalar()
    )

    return {
        "total_repos": unique_repos or 0,
        "total_scans": stats.total_scans or 0,
        "avg_debt_score": round(float(stats.avg_score or 0), 1),
        "total_cost_usd": float(stats.total_cost or 0),
        "total_hours": float(stats.total_hours or 0),
        "worst_score": float(stats.worst_score or 0),
        "best_score": float(stats.best_score or 0),
    }


def build_portfolio_trends(db: Session, user_id: int) -> dict[str, Any]:
    """Return debt score and cost history grouped by repository."""
    scans = (
        db.query(
            Scan.repository_id,
            Scan.debt_score,
            Scan.total_cost_usd,
            Scan.created_at,
        )
        .filter(Scan.user_id == user_id, Scan.status == "complete")
        .order_by(Scan.repository_id, Scan.created_at)
        .all()
    )

    trends: dict[str, list[dict[str, Any]]] = {}
    for scan in scans:
        trends.setdefault(scan.repository_id, []).append(
            {
                "date": scan.created_at.isoformat() if scan.created_at else None,
                "score": scan.debt_score or 0,
                "cost": scan.total_cost_usd or 0,
            }
        )
    return {"trends": trends}


def remove_repo_from_portfolio(db: Session, user_id: int, repo_id: str) -> dict[str, Any]:
    """Delete all scans for a repository in the current user portfolio."""
    deleted = (
        db.query(Scan)
        .filter(Scan.repository_id == repo_id, Scan.user_id == user_id)
        .delete()
    )
    db.commit()
    return {"deleted_scans": deleted, "repo_id": repo_id}
