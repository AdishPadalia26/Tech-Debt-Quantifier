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
    FindingSuppression,
    FindingFeedback,
)
from tools.scoring import severity_rank

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
                "suppressed": any(s.active for s in finding.suppressions),
                "suppressions": [
                    {
                        "id": suppression.id,
                        "reason": suppression.reason,
                        "created_by": suppression.created_by,
                        "active": suppression.active,
                        "created_at": (
                            suppression.created_at.isoformat()
                            if suppression.created_at
                            else None
                        ),
                    }
                    for suppression in finding.suppressions
                ],
                "feedback": [
                    {
                        "id": feedback.id,
                        "feedback_type": feedback.feedback_type,
                        "severity_override": feedback.severity_override,
                        "notes": feedback.notes,
                        "created_by": feedback.created_by,
                        "created_at": (
                            feedback.created_at.isoformat()
                            if feedback.created_at
                            else None
                        ),
                    }
                    for feedback in finding.feedback_entries
                ],
            }
            for finding in scan.findings
        ]
    analysis = _get_scan_analysis(scan)
    findings = analysis.get("findings")
    return findings if isinstance(findings, list) else []


def query_scan_findings(
    db: Session,
    scan_id: str,
    *,
    user_id: int | None = None,
    category: str | None = None,
    severity: str | None = None,
    module: str | None = None,
    min_confidence: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    """Return filtered, paginated findings for a scan."""
    findings = get_scan_findings(db, scan_id, user_id=user_id)
    if findings is None:
        return None

    filtered = findings
    if category:
        filtered = [f for f in filtered if f.get("category") == category]
    if severity:
        min_severity_rank = severity_rank(severity)
        filtered = [
            f for f in filtered if severity_rank(str(f.get("severity", "low"))) >= min_severity_rank
        ]
    if module:
        filtered = [f for f in filtered if f.get("module") == module]
    if min_confidence is not None:
        filtered = [
            f for f in filtered if float(f.get("confidence", 0.0)) >= min_confidence
        ]

    filtered = sorted(
        filtered,
        key=lambda f: (
            severity_rank(str(f.get("severity", "low"))),
            float(f.get("cost_usd", 0.0)),
            float(f.get("confidence", 0.0)),
        ),
        reverse=True,
    )

    total = len(filtered)
    items = filtered[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


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


def compare_scans(
    db: Session,
    base_scan_id: str,
    target_scan_id: str,
    *,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Compare two scans and summarize score, cost, and finding deltas."""
    base_scan = get_scan_by_id(db, base_scan_id, user_id=user_id)
    target_scan = get_scan_by_id(db, target_scan_id, user_id=user_id)
    if not base_scan or not target_scan:
        return None

    base_findings = get_scan_findings(db, base_scan_id, user_id=user_id) or []
    target_findings = get_scan_findings(db, target_scan_id, user_id=user_id) or []

    base_by_id = {finding.get("id"): finding for finding in base_findings}
    target_by_id = {finding.get("id"): finding for finding in target_findings}

    added_ids = [finding_id for finding_id in target_by_id if finding_id not in base_by_id]
    removed_ids = [finding_id for finding_id in base_by_id if finding_id not in target_by_id]
    common_ids = [finding_id for finding_id in target_by_id if finding_id in base_by_id]

    severity_changed = []
    for finding_id in common_ids:
        base_finding = base_by_id[finding_id]
        target_finding = target_by_id[finding_id]
        if base_finding.get("severity") != target_finding.get("severity"):
            severity_changed.append(
                {
                    "id": finding_id,
                    "file_path": target_finding.get("file_path"),
                    "from_severity": base_finding.get("severity"),
                    "to_severity": target_finding.get("severity"),
                }
            )

    return {
        "base_scan_id": base_scan_id,
        "target_scan_id": target_scan_id,
        "summary": {
            "cost_delta_usd": round(target_scan.total_cost_usd - base_scan.total_cost_usd, 2),
            "debt_score_delta": round(target_scan.debt_score - base_scan.debt_score, 2),
            "hours_delta": round(target_scan.total_hours - base_scan.total_hours, 2),
            "finding_count_delta": len(target_findings) - len(base_findings),
        },
        "added_findings": [target_by_id[finding_id] for finding_id in added_ids[:50]],
        "removed_findings": [base_by_id[finding_id] for finding_id in removed_ids[:50]],
        "severity_changed": severity_changed[:50],
    }


def get_finding_record(
    db: Session,
    scan_id: str,
    finding_id: str,
    *,
    user_id: int | None = None,
) -> Finding | None:
    """Return a structured finding record by scan and finding key/id."""
    scan = get_scan_by_id(db, scan_id, user_id=user_id)
    if not scan:
        return None

    return (
        db.query(Finding)
        .filter(
            Finding.scan_id == scan.id,
            (Finding.finding_key == finding_id) | (Finding.id == finding_id),
        )
        .first()
    )


def suppress_finding(
    db: Session,
    scan_id: str,
    finding_id: str,
    *,
    reason: str,
    created_by: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Create an active suppression for a finding and update its status."""
    finding = get_finding_record(db, scan_id, finding_id, user_id=user_id)
    if not finding:
        return None

    suppression = FindingSuppression(
        finding_id=finding.id,
        reason=reason,
        created_by=created_by,
        active=True,
    )
    finding.status = "suppressed"
    db.add(suppression)
    db.commit()
    db.refresh(suppression)

    return {
        "id": suppression.id,
        "finding_id": finding.finding_key or finding.id,
        "reason": suppression.reason,
        "created_by": suppression.created_by,
        "active": suppression.active,
    }


def add_finding_feedback(
    db: Session,
    scan_id: str,
    finding_id: str,
    *,
    feedback_type: str,
    severity_override: str | None = None,
    notes: str | None = None,
    created_by: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Attach feedback to a finding and optionally update its status."""
    finding = get_finding_record(db, scan_id, finding_id, user_id=user_id)
    if not finding:
        return None

    feedback = FindingFeedback(
        finding_id=finding.id,
        feedback_type=feedback_type,
        severity_override=severity_override,
        notes=notes,
        created_by=created_by,
    )
    if feedback_type in {"false_positive", "accepted_risk"}:
        finding.status = "reviewed"
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return {
        "id": feedback.id,
        "finding_id": finding.finding_key or finding.id,
        "feedback_type": feedback.feedback_type,
        "severity_override": feedback.severity_override,
        "notes": feedback.notes,
        "created_by": feedback.created_by,
    }


def get_latest_scan_for_repo(
    db: Session, github_url: str, user_id: int | None = None
) -> Scan | None:
    """Return the most recent completed scan for a repository."""
    normalized = _normalize_url(github_url)
    repo_query = db.query(Repository).filter(Repository.github_url == normalized)
    if user_id is not None:
        repo_query = repo_query.filter(Repository.user_id == user_id)
    repo = repo_query.first()
    if not repo:
        return None

    scan_query = db.query(Scan).filter(
        Scan.repository_id == repo.id,
        Scan.status == "complete",
    )
    if user_id is not None:
        scan_query = scan_query.filter(Scan.user_id == user_id)
    return scan_query.order_by(desc(Scan.created_at)).first()


def get_repo_triage_stats(
    db: Session, github_url: str, user_id: int | None = None
) -> dict[str, Any] | None:
    """Return triage statistics for the latest scan of a repository."""
    latest_scan = get_latest_scan_for_repo(db, github_url, user_id=user_id)
    if not latest_scan:
        return None

    findings = get_scan_findings(db, latest_scan.id, user_id=user_id) or []
    total = len(findings)
    suppressed = sum(1 for finding in findings if finding.get("suppressed"))
    active = sum(1 for finding in findings if finding.get("status") == "open")
    reviewed = sum(1 for finding in findings if finding.get("status") == "reviewed")

    by_category: dict[str, int] = {}
    for finding in findings:
        category = finding.get("category", "unknown")
        by_category[category] = by_category.get(category, 0) + 1

    return {
        "scan_id": latest_scan.id,
        "total_findings": total,
        "active_findings": active,
        "suppressed_findings": suppressed,
        "reviewed_findings": reviewed,
        "suppression_rate": round((suppressed / total) * 100, 1) if total else 0.0,
        "review_rate": round((reviewed / total) * 100, 1) if total else 0.0,
        "by_category": by_category,
    }


def get_repo_unresolved_findings(
    db: Session,
    github_url: str,
    *,
    user_id: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]] | None:
    """Return the highest-priority unresolved findings for the latest repo scan."""
    latest_scan = get_latest_scan_for_repo(db, github_url, user_id=user_id)
    if not latest_scan:
        return None

    findings = get_scan_findings(db, latest_scan.id, user_id=user_id) or []
    unresolved = [
        finding
        for finding in findings
        if finding.get("status") == "open" and not finding.get("suppressed")
    ]
    unresolved = sorted(
        unresolved,
        key=lambda finding: (
            severity_rank(str(finding.get("severity", "low"))),
            float(finding.get("cost_usd", 0.0)),
            float(finding.get("confidence", 0.0)),
        ),
        reverse=True,
    )
    return unresolved[:limit]


def get_repo_summary_rollup(
    db: Session, github_url: str, user_id: int | None = None
) -> dict[str, Any] | None:
    """Return a high-level product summary for the latest scan of a repository."""
    latest_scan = get_latest_scan_for_repo(db, github_url, user_id=user_id)
    if not latest_scan:
        return None

    findings = get_scan_findings(db, latest_scan.id, user_id=user_id) or []
    modules = get_scan_modules(db, latest_scan.id, user_id=user_id) or []
    roadmap = get_scan_roadmap(db, latest_scan.id, user_id=user_id) or {}
    triage = get_repo_triage_stats(db, github_url, user_id=user_id) or {}

    return {
        "scan_id": latest_scan.id,
        "github_url": _normalize_url(github_url),
        "total_cost_usd": latest_scan.total_cost_usd,
        "debt_score": latest_scan.debt_score,
        "total_hours": latest_scan.total_hours,
        "finding_count": len(findings),
        "module_count": len(modules),
        "quick_wins": len(roadmap.get("quick_wins", [])),
        "strategic_items": len(roadmap.get("strategic", [])),
        "triage": triage,
        "top_modules": modules[:5],
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
