"""Database operations for scan persistence and history queries."""

from sqlalchemy.orm import Session
from sqlalchemy import desc
from database.models import Repository, Scan, DebtItem
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ─── Repository Operations ───────────────────────────────────


def get_or_create_repository(db: Session, github_url: str) -> Repository:
    """Get existing repo or create new one."""
    parts = github_url.rstrip("/").split("/")
    owner = parts[-2] if len(parts) >= 2 else "unknown"
    name = parts[-1] if parts else "unknown"

    repo = db.query(Repository).filter(
        Repository.github_url == github_url
    ).first()

    if not repo:
        repo = Repository(
            github_url=github_url,
            repo_name=name,
            repo_owner=owner,
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        logger.info(f"Created new repository: {github_url}")

    return repo


# ─── Scan Operations ─────────────────────────────────────────


def save_scan(
    db: Session,
    job_id: str,
    github_url: str,
    analysis: dict,
    agent_state: dict,
    duration_seconds: float = 0,
) -> Scan:
    """Save a completed scan to the database."""

    repo = get_or_create_repository(db, github_url)

    # Extract data safely
    profile = analysis.get("repo_profile", {})
    tech_stack = profile.get("tech_stack", {})
    team = profile.get("team", {})
    multipliers = profile.get("multipliers", {})
    hourly_rates = analysis.get("hourly_rates", {})

    scan = Scan(
        repository_id=repo.id,
        job_id=job_id,
        total_cost_usd=analysis.get("total_cost_usd", 0),
        debt_score=analysis.get("debt_score", 0),
        total_hours=analysis.get("total_remediation_hours", 0),
        total_sprints=analysis.get("total_remediation_sprints", 0),
        cost_by_category=analysis.get("cost_by_category", {}),
        hourly_rate=hourly_rates.get("blended_rate"),
        rate_confidence=hourly_rates.get("confidence"),
        team_size=team.get("estimated_team_size"),
        bus_factor=team.get("bus_factor"),
        repo_age_days=team.get("repo_age_days"),
        combined_multiplier=multipliers.get("combined_multiplier"),
        primary_language=tech_stack.get("primary_language"),
        frameworks=tech_stack.get("frameworks", []),
        executive_summary=agent_state.get("executive_summary"),
        priority_actions=agent_state.get("priority_actions"),
        roi_analysis=agent_state.get("roi_analysis"),
        raw_result=agent_state,
        status="complete",
        scan_duration_seconds=duration_seconds,
    )

    db.add(scan)

    # Save individual debt items for trend analysis
    debt_items = analysis.get("debt_items", [])
    for item in debt_items[:100]:  # cap at 100 items per scan
        db.add(
            DebtItem(
                scan_id=scan.id,
                file_path=item.get("file", ""),
                function_name=item.get("function", ""),
                category=item.get("category", ""),
                severity=item.get("severity", ""),
                cost_usd=item.get("cost_usd", 0),
                hours=(item.get("adjusted_minutes", 0) or 0) / 60,
                complexity=item.get("complexity"),
                churn_multiplier=item.get("churn_multiplier"),
            )
        )

    # Update last_scanned_at on repo
    repo.last_scanned_at = datetime.utcnow()
    repo.primary_language = tech_stack.get("primary_language")

    db.commit()
    db.refresh(scan)

    logger.info(
        f"Saved scan {scan.id} for {github_url}: "
        f"${analysis.get('total_cost_usd', 0):,.0f}"
    )
    return scan


# ─── History Queries ─────────────────────────────────────────


def get_scan_history(db: Session, github_url: str, limit: int = 10) -> list:
    """Get last N scans for a repo, ordered newest first."""
    repo = db.query(Repository).filter(
        Repository.github_url == github_url
    ).first()

    if not repo:
        return []

    scans = (
        db.query(Scan)
        .filter(Scan.repository_id == repo.id, Scan.status == "complete")
        .order_by(desc(Scan.created_at))
        .limit(limit)
        .all()
    )

    return scans


def get_debt_trend(db: Session, github_url: str) -> dict:
    """Calculate debt trend across all scans. Returns trend data for charts."""
    scans = get_scan_history(db, github_url, limit=20)

    if not scans:
        return {"trend": [], "change_pct": 0, "direction": "stable"}

    # Build trend data points (oldest first for chart)
    trend = [
        {
            "date": scan.created_at.isoformat(),
            "date_display": scan.created_at.strftime("%b %d"),
            "total_cost": scan.total_cost_usd,
            "debt_score": scan.debt_score,
            "scan_id": scan.id,
        }
        for scan in reversed(scans)
    ]

    # Calculate change from previous to latest scan
    if len(scans) >= 2:
        latest = scans[0].total_cost_usd
        previous = scans[1].total_cost_usd
        change_pct = ((latest - previous) / previous * 100) if previous else 0
        direction = (
            "up" if change_pct > 2 else "down" if change_pct < -2 else "stable"
        )
    else:
        change_pct = 0
        direction = "stable"

    return {
        "trend": trend,
        "change_pct": round(change_pct, 1),
        "direction": direction,
        "total_scans": len(scans),
        "first_scan_cost": trend[0]["total_cost"] if trend else 0,
        "latest_cost": trend[-1]["total_cost"] if trend else 0,
    }


def get_all_repositories(db: Session) -> list:
    """Get all tracked repos with their latest scan."""
    repos = db.query(Repository).order_by(
        desc(Repository.last_scanned_at)
    ).all()

    result = []
    for repo in repos:
        latest_scan = (
            db.query(Scan)
            .filter(Scan.repository_id == repo.id, Scan.status == "complete")
            .order_by(desc(Scan.created_at))
            .first()
        )

        result.append(
            {
                "github_url": repo.github_url,
                "repo_name": repo.repo_name,
                "repo_owner": repo.repo_owner,
                "last_scanned": (
                    repo.last_scanned_at.isoformat()
                    if repo.last_scanned_at
                    else None
                ),
                "latest_cost": (
                    latest_scan.total_cost_usd if latest_scan else None
                ),
                "latest_score": (
                    latest_scan.debt_score if latest_scan else None
                ),
                "total_scans": len(repo.scans),
                "language": repo.primary_language,
            }
        )

    return result
