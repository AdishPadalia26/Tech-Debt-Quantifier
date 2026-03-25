"""Tech Debt Quantifier - FastAPI Backend Server."""

import os
import uuid
import time
import io
import logging
import traceback
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from models.schemas import AnalyzeRequest, AnalyzeResponse
from database.connection import DB_AVAILABLE, SessionLocal, engine
from database.models import Base
from database.crud import (
    save_scan,
    get_scan_history,
    get_debt_trend,
    get_all_repositories,
)

try:
    from agents.orchestrator import TechDebtOrchestrator
    ORCHESTRATOR_AVAILABLE = True
    logger.info("TechDebtOrchestrator loaded successfully")
except Exception as e:
    ORCHESTRATOR_AVAILABLE = False
    logger.error(f"TechDebtOrchestrator failed to load: {e}")
    logger.error(traceback.format_exc())

jobs: Dict[str, Any] = {}


def normalize_repo_id(github_url: str) -> str:
    """Always store as 'owner/repo' format."""
    url = github_url.strip().rstrip("/")
    # Strip protocol prefixes
    for prefix in ["https://github.com/", "http://github.com/", "github.com/"]:
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    # Already short format
    if not url.startswith("http"):
        segments = url.strip("/").split("/")
        if len(segments) >= 2:
            return f"{segments[0]}/{segments[1]}"
        return url
    # Fallback: extract from full URL
    parts = url.replace("https://github.com/", "").replace("http://github.com/", "")
    segments = parts.strip("/").split("/")
    if len(segments) >= 2:
        return f"{segments[0]}/{segments[1]}"
    return parts

app = FastAPI(
    title="Tech Debt Quantifier",
    version="0.2.0",
    description="Agentic AI platform for technical debt analysis",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    """Create tables if they don't exist."""
    if DB_AVAILABLE:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables verified/created")
        except Exception as e:
            logger.error(f"Table creation failed: {e}")
    logger.info(f"Database available: {DB_AVAILABLE}")


@app.get("/")
async def health() -> dict:
    return {
        "status": "ok",
        "project": "Tech Debt Quantifier",
        "version": "0.2.0",
        "orchestrator_available": ORCHESTRATOR_AVAILABLE,
        "database_available": DB_AVAILABLE,
    }


@app.get("/health")
async def detailed_health() -> dict:
    return {
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
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    """Start async analysis of a GitHub repo."""

    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Analysis engine not loaded.")

    if "github.com" not in request.github_url:
        raise HTTPException(status_code=400, detail="Must be a github.com URL")

    job_id = str(uuid.uuid4())
    repo_id = normalize_repo_id(request.repo_id or request.github_url)

    jobs[job_id] = {
        "status": "queued",
        "result": None,
        "error": None,
        "github_url": request.github_url,
    }

    logger.info(f"Job {job_id} queued for {request.github_url}")

    background_tasks.add_task(
        run_analysis_job,
        job_id,
        request.github_url,
        repo_id,
    )

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis started. Poll GET /results/{job_id} for updates.",
    )


async def run_analysis_job(job_id: str, github_url: str, repo_id: str) -> None:
    """Background task — runs full agent pipeline, saves to DB."""
    start_time = time.time()
    try:
        jobs[job_id]["status"] = "running"

        orchestrator = TechDebtOrchestrator()
        result = await orchestrator.run_analysis(github_url, repo_id)

        duration = time.time() - start_time
        jobs[job_id]["status"] = result.get("status", "complete")
        jobs[job_id]["result"] = result

        # Save to SQLite
        # Analysis data may be in raw_analysis or flattened into result
        analysis_data = result.get("raw_analysis") or result
        if result.get("status") != "failed" and analysis_data.get("total_cost_usd"):
            try:
                db = SessionLocal()
                saved_scan = save_scan(
                    db=db,
                    job_id=job_id,
                    github_url=github_url,
                    analysis=analysis_data,
                    agent_state=result,
                    duration_seconds=duration,
                )
                jobs[job_id]["scan_id"] = saved_scan.id
                logger.info(f"Scan saved to DB: {saved_scan.id}")
                db.close()
            except Exception as db_err:
                logger.error(f"DB save failed (analysis still ok): {db_err}")

        logger.info(f"Job {job_id}: completed in {duration:.1f}s")

    except Exception as e:
        error_msg = str(e)
        full_trace = traceback.format_exc()
        logger.error(f"Job {job_id} failed: {error_msg}")
        logger.error(full_trace)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = error_msg


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> dict:
    """Poll for analysis results."""

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = jobs[job_id]

    if job["status"] == "complete":
        result = job["result"]
        return {
            "job_id": job_id,
            "status": "complete",
            "scan_id": job.get("scan_id"),
            "raw": result,
        }

    if job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job.get("error")}

    return {"job_id": job_id, "status": job["status"]}


@app.get("/jobs")
async def list_jobs() -> dict:
    """List all in-memory jobs."""
    return {
        "total": len(jobs),
        "jobs": [
            {"job_id": jid, "status": j["status"], "url": j.get("github_url")}
            for jid, j in jobs.items()
        ],
    }


# ──────────────────────────────────────────────
# Database-backed endpoints
# ──────────────────────────────────────────────


@app.get("/history/{repo_url:path}")
async def get_repo_history(repo_url: str):
    """Get scan history and trend for a repo."""
    # repo_url comes in as: github.com/pallets/flask
    # normalize to full URL
    if not repo_url.startswith("http"):
        repo_url = f"https://{repo_url}"

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        history = get_scan_history(db, repo_url, limit=10)
        trend = get_debt_trend(db, repo_url)

        scans = [
            {
                "scan_id": s.id,
                "date": s.created_at.isoformat(),
                "date_display": s.created_at.strftime("%b %d, %Y"),
                "total_cost": s.total_cost_usd,
                "debt_score": s.debt_score,
                "total_hours": s.total_hours,
                "executive_summary": s.executive_summary,
                "cost_by_category": s.cost_by_category,
            }
            for s in history
        ]

        return {
            "github_url": repo_url,
            "scans": scans,
            "trend": trend,
            "total_scans": len(scans),
        }
    finally:
        db.close()


@app.get("/repositories")
async def list_repositories():
    """List all tracked repositories with latest metrics."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        repos = get_all_repositories(db)
        return {"repositories": repos, "total": len(repos)}
    finally:
        db.close()


@app.get("/scan/{scan_id}")
async def get_scan(scan_id: str):
    """Get a specific scan by ID."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        from database.models import Scan

        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            raise HTTPException(404, "Scan not found")
        return {
            "scan_id": scan.id,
            "total_cost": scan.total_cost_usd,
            "debt_score": scan.debt_score,
            "executive_summary": scan.executive_summary,
            "priority_actions": scan.priority_actions,
            "roi_analysis": scan.roi_analysis,
            "raw_result": scan.raw_result,
            "created_at": scan.created_at.isoformat(),
        }
    finally:
        db.close()


@app.get("/report/{job_id}/pdf")
async def download_pdf_report(job_id: str):
    """Generate and download PDF report for a completed job."""

    if job_id not in jobs:
        # Try loading from DB
        from database.connection import SessionLocal
        from database.models import Scan
        db = SessionLocal()
        scan = db.query(Scan).filter(
            Scan.job_id == job_id
        ).first()
        db.close()
        if not scan:
            raise HTTPException(404, "Job not found")
        result = scan.raw_result
    else:
        job = jobs[job_id]
        if job['status'] != 'complete':
            raise HTTPException(400, f"Job not complete: {job['status']}")
        result = job['result']

    try:
        from reports.pdf_generator import TechDebtPDFGenerator
        generator = TechDebtPDFGenerator()

        analysis = result.get('raw_analysis') or result
        pdf_bytes = generator.generate(analysis, result)

        repo_name = (result.get('github_url', 'report')
                     .split('/')[-1])
        filename = f"tech-debt-{repo_name}-{datetime.now().strftime('%Y%m%d')}.pdf"

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"PDF generation failed: {str(e)}")


def _top_category(analysis: dict) -> str:
    cats = analysis.get("cost_by_category", {})
    if not cats:
        return "unknown"
    top = max(cats.items(), key=lambda x: x[1].get("cost_usd", 0) if isinstance(x[1], dict) else 0)
    return top[0].replace("_", " ").title()


def _risk_level(score: float) -> str:
    if score >= 7:
        return "critical"
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


@app.get("/portfolio")
async def get_portfolio():
    """Return all repos ranked by debt score descending."""
    from database.connection import SessionLocal
    from database.models import Scan, Repository

    db = SessionLocal()

    # Get ALL scans, then deduplicate using normalized repo key
    all_scans = (
        db.query(Scan)
        .order_by(Scan.created_at.desc())
        .all()
    )

    # Build repo lookup
    repo_map = {r.id: r for r in db.query(Repository).all()}
    db.close()

    # Deduplicate: keep only latest scan per normalized repo
    seen = {}
    for scan in all_scans:
        raw = scan.raw_result or {}
        # Get github_url from multiple possible sources
        github_url = (
            raw.get("github_url")
            or raw.get("repo_url")
            or (repo_map.get(scan.repository_id).github_url if repo_map.get(scan.repository_id) else None)
            or ""
        )
        # Normalize to owner/repo key
        key = normalize_repo_id(github_url) if github_url else scan.repository_id
        if not key:
            continue
        if key not in seen:
            seen[key] = (scan, github_url)

    portfolio = []
    for key, (scan, github_url) in seen.items():
        raw = scan.raw_result or {}
        analysis = raw.get("raw_analysis") or raw
        profile = analysis.get("repo_profile", {})
        tech = profile.get("tech_stack", {}) if profile else {}
        team = profile.get("team", {}) if profile else {}

        # Ensure github_url has full format for links
        full_url = github_url
        if full_url and not full_url.startswith("http"):
            full_url = f"https://github.com/{full_url}"

        portfolio.append(
            {
                "repo_id": key,
                "github_url": full_url or f"https://github.com/{key}",
                "debt_score": float(scan.debt_score or 0),
                "total_cost": float(scan.total_cost_usd or 0),
                "remediation_hours": float(scan.total_hours or 0),
                "language": tech.get("primary_language", scan.primary_language or "Unknown"),
                "team_size": team.get("estimated_team_size", scan.team_size or 0),
                "bus_factor": team.get("bus_factor", scan.bus_factor or 0),
                "has_tests": tech.get("has_tests", False),
                "has_ci_cd": tech.get("has_ci_cd", False),
                "scanned_at": scan.created_at.isoformat() if scan.created_at else None,
                "top_category": _top_category(analysis),
                "risk_level": _risk_level(float(scan.debt_score or 0)),
            }
        )

    # Sort by debt_score descending
    portfolio.sort(key=lambda x: x["debt_score"], reverse=True)
    return {"repos": portfolio, "total": len(portfolio)}


@app.get("/portfolio/summary")
async def get_portfolio_summary():
    """Aggregate stats across all tracked repos."""
    from database.connection import SessionLocal
    from database.models import Scan
    from sqlalchemy import func

    db = SessionLocal()
    stats = db.query(
        func.count(Scan.id).label("total_scans"),
        func.avg(Scan.debt_score).label("avg_score"),
        func.sum(Scan.total_cost_usd).label("total_cost"),
        func.sum(Scan.total_hours).label("total_hours"),
        func.max(Scan.debt_score).label("worst_score"),
        func.min(Scan.debt_score).label("best_score"),
    ).first()

    unique_repos = db.query(func.count(func.distinct(Scan.repository_id))).scalar()

    db.close()

    return {
        "total_repos": unique_repos or 0,
        "total_scans": stats.total_scans or 0,
        "avg_debt_score": round(float(stats.avg_score or 0), 1),
        "total_cost_usd": float(stats.total_cost or 0),
        "total_hours": float(stats.total_hours or 0),
        "worst_score": float(stats.worst_score or 0),
        "best_score": float(stats.best_score or 0),
    }


@app.get("/portfolio/trends")
async def get_portfolio_trends():
    """Show debt score over time for all repos."""
    from database.connection import SessionLocal
    from database.models import Scan

    db = SessionLocal()
    scans = (
        db.query(
            Scan.repository_id,
            Scan.debt_score,
            Scan.total_cost_usd,
            Scan.created_at,
        )
        .order_by(Scan.repository_id, Scan.created_at)
        .all()
    )
    db.close()

    trends = {}
    for s in scans:
        rid = s.repository_id
        if rid not in trends:
            trends[rid] = []
        trends[rid].append(
            {
                "date": s.created_at.isoformat() if s.created_at else None,
                "score": s.debt_score or 0,
                "cost": s.total_cost_usd or 0,
            }
        )

    return {"trends": trends}


@app.delete("/portfolio/{repo_id:path}")
async def remove_from_portfolio(repo_id: str):
    """Remove a repo from tracking."""
    from database.connection import SessionLocal
    from database.models import Scan

    db = SessionLocal()
    deleted = db.query(Scan).filter(Scan.repository_id == repo_id).delete()
    db.commit()
    db.close()
    return {"deleted_scans": deleted, "repo_id": repo_id}


@app.get("/debug/scans")
async def debug_scans():
    """Show all scans in DB with their repo info."""
    from database.connection import SessionLocal
    from database.models import Scan, Repository

    db = SessionLocal()
    scans = db.query(Scan).order_by(Scan.created_at.desc()).all()
    repo_map = {r.id: r for r in db.query(Repository).all()}
    db.close()

    return {
        "count": len(scans),
        "scans": [
            {
                "id": s.id,
                "repository_id": s.repository_id,
                "repo_url": repo_map.get(s.repository_id).github_url if repo_map.get(s.repository_id) else None,
                "normalized": normalize_repo_id(
                    (s.raw_result or {}).get("github_url")
                    or (repo_map.get(s.repository_id).github_url if repo_map.get(s.repository_id) else "")
                    or ""
                ),
                "debt_score": s.debt_score,
                "total_cost": s.total_cost_usd,
                "github_url": (s.raw_result or {}).get("github_url"),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in scans
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
