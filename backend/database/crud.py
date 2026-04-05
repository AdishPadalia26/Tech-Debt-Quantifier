"""Database operations for scan persistence and history queries."""

from datetime import datetime, UTC
import logging
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from database.models import (
    Repository,
    Scan,
    DebtItem,
    Finding,
    ModuleSummary,
    RoadmapItem,
)

logger = logging.getLogger(__name__)


# ─── Repository Operations ───────────────────────────────────


def _normalize_url(github_url: str) -> str:
    """Normalize any repo identifier to full GitHub URL for consistent lookups."""
    url = github_url.strip().rstrip("/")
    if url.startswith("https://github.com/"):
        return url
    if url.startswith("http://github.com/"):
        return url.replace("http://", "https://")
    if url.startswith("github.com/"):
        return f"https://{url}"
    if not url.startswith("http"):
        return f"https://github.com/{url}"
    return url


def get_or_create_repository(db: Session, github_url: str, user_id: int | None = None) -> Repository:
    """Get existing repo or create new one."""
    normalized = _normalize_url(github_url)
    parts = normalized.rstrip("/").split("/")
    owner = parts[-2] if len(parts) >= 2 else "unknown"
    name = parts[-1] if parts else "unknown"

    repo = db.query(Repository).filter(
        Repository.github_url == normalized
    ).first()

    if not repo:
        repo = Repository(
            github_url=normalized,
            repo_name=name,
            repo_owner=owner,
            user_id=user_id,
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        logger.info(f"Created new repository: {normalized}")
    elif user_id and not repo.user_id:
        repo.user_id = user_id
        db.commit()

    return repo


# ─── Scan Operations ─────────────────────────────────────────


def save_scan(
    db: Session,
    job_id: str,
    github_url: str,
    analysis: dict,
    agent_state: dict,
    duration_seconds: float = 0,
    user_id: int | None = None,
) -> Scan:
    """Save a completed scan to the database."""

    repo = get_or_create_repository(db, github_url, user_id=user_id)

    # Extract data safely
    profile = analysis.get("repo_profile", {})
    tech_stack = profile.get("tech_stack", {})
    team = profile.get("team", {})
    multipliers = profile.get("multipliers", {})
    hourly_rates = analysis.get("hourly_rates", {})

    scan = Scan(
        repository_id=repo.id,
        job_id=job_id,
        user_id=user_id,
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
    db.flush()

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
                hours=item.get("remediation_hours", (item.get("adjusted_minutes", 0) or 0) / 60),
                complexity=item.get("complexity"),
                churn_multiplier=item.get("churn_multiplier"),
            )
        )

    findings = analysis.get("findings", [])
    for finding in findings[:250]:
        db.add(
            Finding(
                scan_id=scan.id,
                finding_key=finding.get("id"),
                file_path=finding.get("file_path", ""),
                module=finding.get("module", ""),
                category=finding.get("category", ""),
                subcategory=finding.get("subcategory"),
                symbol_name=finding.get("symbol_name"),
                line_start=finding.get("line_start"),
                line_end=finding.get("line_end"),
                severity=finding.get("severity"),
                business_impact=finding.get("business_impact"),
                effort_hours=finding.get("effort_hours", 0),
                cost_usd=finding.get("cost_usd", 0),
                confidence=finding.get("confidence", 0),
                source_tool=finding.get("source_tool"),
                status=finding.get("status", "open"),
                evidence=finding.get("evidence", []),
            )
        )

    module_summaries = analysis.get("module_summaries", [])
    for module_summary in module_summaries[:200]:
        db.add(
            ModuleSummary(
                scan_id=scan.id,
                module=module_summary.get("module", ""),
                finding_count=module_summary.get("finding_count", 0),
                total_cost_usd=module_summary.get("total_cost_usd", 0),
                total_effort_hours=module_summary.get("total_effort_hours", 0),
                max_severity=module_summary.get("max_severity"),
                avg_confidence=module_summary.get("avg_confidence", 0),
            )
        )

    roadmap = analysis.get("roadmap", {})
    for bucket, items in roadmap.items():
        if not isinstance(items, list):
            continue
        for item in items[:100]:
            db.add(
                RoadmapItem(
                    scan_id=scan.id,
                    bucket=bucket,
                    finding_id=item.get("finding_id"),
                    title=item.get("title"),
                    file_path=item.get("file_path", ""),
                    module=item.get("module", ""),
                    severity=item.get("severity"),
                    business_impact=item.get("business_impact"),
                    effort_hours=item.get("effort_hours", 0),
                    cost_usd=item.get("cost_usd", 0),
                    confidence=item.get("confidence", 0),
                )
            )

    # Update last_scanned_at on repo
    repo.last_scanned_at = datetime.now(UTC).replace(tzinfo=None)
    repo.primary_language = tech_stack.get("primary_language")

    db.commit()
    db.refresh(scan)

    logger.info(
        f"Saved scan {scan.id} for {github_url}: "
        f"${analysis.get('total_cost_usd', 0):,.0f}"
    )
    return scan


def _get_scan_analysis(scan: Scan) -> dict[str, Any]:
    """Extract normalized analysis payload from a persisted scan."""
    raw = scan.raw_result or {}
    if not isinstance(raw, dict):
        return {}
    raw_analysis = raw.get("raw_analysis")
    if isinstance(raw_analysis, dict):
        return raw_analysis
    return raw


def get_scan_by_id(
    db: Session, scan_id: str, user_id: int | None = None
) -> Scan | None:
    """Load a scan by ID with optional user scoping."""
    query = db.query(Scan).filter(Scan.id == scan_id)
    if user_id is not None:
        query = query.filter(Scan.user_id == user_id)
    return query.first()


def get_scan_summary_data(
    db: Session, scan_id: str, user_id: int | None = None
) -> dict[str, Any] | None:
    """Return normalized summary data for a scan."""
    scan = get_scan_by_id(db, scan_id, user_id=user_id)
    if not scan:
        return None

    analysis = _get_scan_analysis(scan)
    return {
        "scan_id": scan.id,
        "repository_id": scan.repository_id,
        "job_id": scan.job_id,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "total_cost_usd": scan.total_cost_usd,
        "debt_score": scan.debt_score,
        "total_hours": scan.total_hours,
        "total_sprints": scan.total_sprints,
        "cost_by_category": scan.cost_by_category or {},
        "summary": analysis.get("summary", {}),
    }


def get_scan_findings(
    db: Session, scan_id: str, user_id: int | None = None
) -> list[dict[str, Any]] | None:
    """Return structured findings persisted within the scan payload."""
    scan = get_scan_by_id(db, scan_id, user_id=user_id)
    if not scan:
        return None
    if scan.findings:
        return [
            {
                "id": finding.finding_key or finding.id,
                "file_path": finding.file_path,
                "module": finding.module,
                "category": finding.category,
                "subcategory": finding.subcategory,
                "symbol_name": finding.symbol_name,
                "line_start": finding.line_start,
                "line_end": finding.line_end,
                "severity": finding.severity,
                "business_impact": finding.business_impact,
                "effort_hours": finding.effort_hours,
                "cost_usd": finding.cost_usd,
                "confidence": finding.confidence,
                "source_tool": finding.source_tool,
                "status": finding.status,
                "evidence": finding.evidence or [],
            }
            for finding in scan.findings
        ]
    analysis = _get_scan_analysis(scan)
    findings = analysis.get("findings")
    return findings if isinstance(findings, list) else []


def get_scan_modules(
    db: Session, scan_id: str, user_id: int | None = None
) -> list[dict[str, Any]] | None:
    """Return module summaries for a persisted scan."""
    scan = get_scan_by_id(db, scan_id, user_id=user_id)
    if not scan:
        return None
    if scan.module_summaries:
        return [
            {
                "module": module.module,
                "finding_count": module.finding_count,
                "total_cost_usd": module.total_cost_usd,
                "total_effort_hours": module.total_effort_hours,
                "max_severity": module.max_severity,
                "avg_confidence": module.avg_confidence,
            }
            for module in scan.module_summaries
        ]
    analysis = _get_scan_analysis(scan)
    modules = analysis.get("module_summaries")
    return modules if isinstance(modules, list) else []


def get_scan_roadmap(
    db: Session, scan_id: str, user_id: int | None = None
) -> dict[str, list[dict[str, Any]]] | None:
    """Return roadmap buckets for a persisted scan."""
    scan = get_scan_by_id(db, scan_id, user_id=user_id)
    if not scan:
        return None
    if scan.roadmap_items:
        roadmap: dict[str, list[dict[str, Any]]] = {}
        for item in scan.roadmap_items:
            roadmap.setdefault(item.bucket, []).append(
                {
                    "finding_id": item.finding_id,
                    "title": item.title,
                    "file_path": item.file_path,
                    "module": item.module,
                    "severity": item.severity,
                    "business_impact": item.business_impact,
                    "effort_hours": item.effort_hours,
                    "cost_usd": item.cost_usd,
                    "confidence": item.confidence,
                }
            )
        return roadmap
    analysis = _get_scan_analysis(scan)
    roadmap = analysis.get("roadmap")
    return roadmap if isinstance(roadmap, dict) else {}


def get_rich_repo_trend(
    db: Session, github_url: str, user_id: int | None = None
) -> dict[str, Any]:
    """Return historical trend data with richer product fields."""
    scans = get_scan_history(db, github_url, limit=20, user_id=user_id)
    if not scans:
        return {"trend": [], "total_scans": 0}

    trend = []
    for scan in reversed(scans):
        analysis = _get_scan_analysis(scan)
        roadmap = get_scan_roadmap(db, scan.id, user_id=user_id) or {}
        findings = get_scan_findings(db, scan.id, user_id=user_id) or []
        modules = get_scan_modules(db, scan.id, user_id=user_id) or []
        trend.append(
            {
                "scan_id": scan.id,
                "date": scan.created_at.isoformat() if scan.created_at else None,
                "date_display": scan.created_at.strftime("%b %d") if scan.created_at else None,
                "total_cost_usd": scan.total_cost_usd,
                "debt_score": scan.debt_score,
                "finding_count": len(findings),
                "module_count": len(modules),
                "quick_wins": len(roadmap.get("quick_wins", [])),
                "strategic_items": len(roadmap.get("strategic", [])),
            }
        )

    return {
        "trend": trend,
        "total_scans": len(trend),
        "latest": trend[-1] if trend else None,
    }


# ─── History Queries ─────────────────────────────────────────


def get_scan_history(db: Session, github_url: str, limit: int = 10, user_id: int | None = None) -> list:
    """Get last N scans for a repo, ordered newest first."""
    normalized = _normalize_url(github_url)
    
    if user_id:
        repo = db.query(Repository).filter(
            Repository.github_url == normalized,
            Repository.user_id == user_id,
        ).first()
    else:
        repo = db.query(Repository).filter(
            Repository.github_url == normalized
        ).first()

    if not repo:
        return []

    if user_id:
        scans = (
            db.query(Scan)
            .filter(Scan.repository_id == repo.id, Scan.status == "complete", Scan.user_id == user_id)
            .order_by(desc(Scan.created_at))
            .limit(limit)
            .all()
        )
    else:
        scans = (
            db.query(Scan)
            .filter(Scan.repository_id == repo.id, Scan.status == "complete")
            .order_by(desc(Scan.created_at))
            .limit(limit)
            .all()
        )

    return scans


def get_debt_trend(db: Session, github_url: str, user_id: int | None = None) -> dict:
    """Calculate debt trend across all scans. Returns trend data for charts."""
    scans = get_scan_history(db, github_url, limit=20, user_id=user_id)

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


def get_all_repositories(db: Session, user_id: int | None = None) -> list:
    """Get all tracked repos with their latest scan."""
    if user_id:
        repos = db.query(Repository).filter(
            Repository.user_id == user_id
        ).order_by(desc(Repository.last_scanned_at)).all()
    else:
        repos = db.query(Repository).order_by(
            desc(Repository.last_scanned_at)
        ).all()

    result = []
    for repo in repos:
        if user_id:
            latest_scan = (
                db.query(Scan)
                .filter(Scan.repository_id == repo.id, Scan.status == "complete", Scan.user_id == user_id)
                .order_by(desc(Scan.created_at))
                .first()
            )
        else:
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
