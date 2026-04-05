"""Tech Debt Quantifier - FastAPI Backend Server."""

import os
import uuid
import time
import io
import logging
import traceback
from datetime import datetime
from typing import Dict, Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from dotenv import load_dotenv
from urllib.parse import urlencode
import httpx
from jose import jwt, JWTError

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from models.schemas import AnalyzeRequest, AnalyzeResponse
from database.connection import DB_AVAILABLE, SessionLocal, engine
from database.models import Base, User
from database.crud import (
    save_scan,
    get_scan_history,
    get_debt_trend,
    get_all_repositories,
    get_scan_summary_data,
    get_scan_findings,
    get_scan_modules,
    get_scan_roadmap,
    get_rich_repo_trend,
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

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_OAUTH_CALLBACK_URL = os.getenv("GITHUB_OAUTH_CALLBACK_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"


def _get_ollama_health() -> dict:
    """Return Ollama configuration and reachability information."""
    provider = os.getenv("LLM_PROVIDER", "not set")
    if provider != "ollama":
        return {
            "configured": False,
            "reachable": False,
            "model": None,
            "base_url": None,
            "status": "inactive",
        }

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    parsed = urlparse(base_url)
    host = parsed.netloc or parsed.path
    health_url = f"{parsed.scheme or 'http'}://{host}/api/tags"

    model = os.getenv("OLLAMA_MODEL", "qwen3.5:latest")
    reachable = False
    status = "unreachable"

    try:
        response = httpx.get(health_url, timeout=3)
        reachable = response.status_code == 200
        status = "ok" if reachable else f"http_{response.status_code}"
    except Exception:
        reachable = False
        status = "unreachable"

    return {
        "configured": True,
        "reachable": reachable,
        "model": model,
        "base_url": base_url,
        "status": status,
    }


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

auth_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(auth_scheme),
) -> User:
    """Get current authenticated user from JWT token."""
    if not creds:
        raise HTTPException(401, "Not authenticated")

    token = creds.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(401, "Invalid token")

    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(401, "User not found")
        return user
    finally:
        db.close()


@app.get("/auth/github/login")
async def github_login():
    """Redirect to GitHub OAuth authorization page."""
    if not GITHUB_CLIENT_ID or not GITHUB_OAUTH_CALLBACK_URL:
        raise HTTPException(500, "GitHub OAuth not configured")

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_OAUTH_CALLBACK_URL,
        "scope": "read:user user:email",
        "allow_signup": "true",
    }
    url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@app.get("/auth/github/callback")
async def github_callback(code: str | None = None, request: Request = None):
    """Handle GitHub OAuth callback, create JWT and redirect to frontend."""
    if not code:
        raise HTTPException(400, "Missing code")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_OAUTH_CALLBACK_URL,
            },
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(400, "Failed to get access token")

        user_resp = await client.get(
            GITHUB_API_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        gh = user_resp.json()

    db = SessionLocal()
    try:
        github_id = str(gh.get("id"))
        if not github_id:
            raise HTTPException(400, "Invalid GitHub user")

        user = db.query(User).filter(User.github_id == github_id).first()
        if not user:
            user = User(
                github_id=github_id,
                login=gh.get("login"),
                name=gh.get("name"),
                avatar_url=gh.get("avatar_url"),
                html_url=gh.get("html_url"),
                email=gh.get("email"),
            )
            db.add(user)
        else:
            user.login = gh.get("login")
            user.name = gh.get("name")
            user.avatar_url = gh.get("avatar_url")
            user.html_url = gh.get("html_url")

        db.commit()
        db.refresh(user)
    finally:
        db.close()

    token_payload = {"sub": str(user.id), "login": user.login}
    jwt_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALG)

    redirect_url = f"{FRONTEND_ORIGIN}/auth/callback#token={jwt_token}"
    return RedirectResponse(redirect_url)


@app.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current user info."""
    return {
        "id": user.id,
        "login": user.login,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "html_url": user.html_url,
    }


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
    ollama_health = _get_ollama_health()
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
        "ollama": ollama_health,
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
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
        "user_id": user.id,
    }

    logger.info(f"Job {job_id} queued for {request.github_url} (user: {user.id})")

    background_tasks.add_task(
        run_analysis_job,
        job_id,
        request.github_url,
        repo_id,
        user.id,
    )

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis started. Poll GET /results/{job_id} for updates.",
    )


async def run_analysis_job(job_id: str, github_url: str, repo_id: str, user_id: int | None = None) -> None:
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
                    user_id=user_id,
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
        return _normalize_result_payload(job_id, "complete", job.get("scan_id"), result)

    if job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job.get("error")}

    return {"job_id": job_id, "status": job["status"]}


def _normalize_result_payload(job_id: str, status: str, scan_id: str | None, state: dict) -> dict:
    if not isinstance(state, dict):
        state = {}

    result = state.get("result", {}) if isinstance(state, dict) else {}
    
    raw_analysis = (
        result.get("raw_analysis") or
        state.get("raw_analysis") or
        result or
        state or
        {}
    )

    priority_actions = (
        result.get("priority_actions") or
        state.get("priority_actions") or
        []
    )

    executive_summary = (
        result.get("executive_summary") or
        state.get("executive_summary") or
        ""
    )

    roi_analysis = (
        result.get("roi_analysis") or
        state.get("roi_analysis") or
        {}
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
        "debt_items": raw_analysis.get("debt_items") or [],
        "findings": raw_analysis.get("findings") or [],
        "module_summaries": raw_analysis.get("module_summaries") or [],
        "roadmap": raw_analysis.get("roadmap") or {},
        "executive_summary": executive_summary,
        "priority_actions": priority_actions,
        "roi_analysis": roi_analysis,
        "sanity_check": raw_analysis.get("sanity_check") or {},
        "hourly_rates": raw_analysis.get("hourly_rates") or {},
        "repo_profile": raw_analysis.get("repo_profile") or {},
        "data_sources_used": raw_analysis.get("data_sources_used") or [],
        "raw_analysis": raw_analysis,
        "raw": state,
    }


@app.get("/debug/results/{job_id}")
async def debug_results(job_id: str):
    """Return the raw result JSON for a job_id without any transformation."""
    if job_id in jobs:
        return jobs[job_id]

    from database.connection import SessionLocal
    from database.models import Scan

    db = SessionLocal()
    scan = db.query(Scan).filter(Scan.job_id == job_id).first()
    db.close()

    if not scan:
        raise HTTPException(status_code=404, detail="Job not found")

    return scan.raw_result


@app.get("/debug/raw/{job_id}")
async def debug_raw(job_id: str):
    """
    Return exactly what is in the DB for this job, zero transformation.
    """
    from database.connection import SessionLocal
    from database.models import Scan

    db = SessionLocal()
    scan = db.query(Scan).filter(Scan.job_id == job_id).first()
    db.close()

    if not scan:
        if job_id in jobs:
            return {
                "source": "memory",
                "status": jobs[job_id].get("status"),
                "result_keys": list((jobs[job_id].get("result") or {}).keys()),
                "raw_analysis_keys": list(
                    (jobs[job_id].get("result") or {})
                    .get("raw_analysis", {}).keys()
                ),
                "full": jobs[job_id].get("result"),
            }
        return {"error": "not found"}

    raw = scan.raw_result or {}
    return {
        "source": "database",
        "job_id": job_id,
        "debt_score_column": scan.debt_score,
        "total_cost_column": scan.total_cost_usd,
        "remediation_hours_column": scan.remediation_hours,
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


@app.get("/history/{repo_url:path}/rich")
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


@app.get("/repositories")
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


@app.get("/scan/{scan_id}")
async def get_scan(scan_id: str, user: User = Depends(get_current_user)):
    """Get a specific scan by ID."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        from database.models import Scan

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
            "raw_result": scan.raw_result,
            "created_at": scan.created_at.isoformat(),
        }
    finally:
        db.close()


@app.get("/scan/{scan_id}/summary")
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


@app.get("/scan/{scan_id}/findings")
async def get_scan_findings_endpoint(
    scan_id: str, user: User = Depends(get_current_user)
):
    """Get structured findings for a specific scan."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available.")

    db = SessionLocal()
    try:
        findings = get_scan_findings(db, scan_id, user_id=user.id)
        if findings is None:
            raise HTTPException(404, "Scan not found")
        return {"scan_id": scan_id, "findings": findings, "total": len(findings)}
    finally:
        db.close()


@app.get("/scan/{scan_id}/modules")
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


@app.get("/scan/{scan_id}/roadmap")
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
async def get_portfolio(user: User = Depends(get_current_user)):
    """Return all repos ranked by debt score descending."""
    from database.connection import SessionLocal
    from database.models import Scan, Repository

    db = SessionLocal()

    all_scans = (
        db.query(Scan)
        .filter(Scan.user_id == user.id, Scan.status == "complete")
        .order_by(Scan.created_at.desc())
        .all()
    )

    repo_map = {r.id: r for r in db.query(Repository).filter(Repository.user_id == user.id).all()}
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
async def get_portfolio_summary(user: User = Depends(get_current_user)):
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
    ).filter(Scan.user_id == user.id, Scan.status == "complete").first()

    unique_repos = db.query(func.count(func.distinct(Scan.repository_id))).filter(
        Scan.user_id == user.id, Scan.status == "complete"
    ).scalar()

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
async def get_portfolio_trends(user: User = Depends(get_current_user)):
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
        .filter(Scan.user_id == user.id, Scan.status == "complete")
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
async def remove_from_portfolio(repo_id: str, user: User = Depends(get_current_user)):
    """Remove a repo from tracking."""
    from database.connection import SessionLocal
    from database.models import Scan

    db = SessionLocal()
    deleted = db.query(Scan).filter(
        Scan.repository_id == repo_id,
        Scan.user_id == user.id
    ).delete()
    db.commit()
    db.close()
    return {"deleted_scans": deleted, "repo_id": repo_id}


@app.get("/debug/scans")
async def debug_scans(user: User = Depends(get_current_user)):
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


from integrations.slack_notifier import SlackNotifier
from integrations.jira_client import JiraClient

slack_notifier = SlackNotifier()
jira_client = JiraClient()


@app.get("/integrations/status")
async def integrations_status():
    """Check which integrations are configured."""
    return {
        "slack": {
            "configured": slack_notifier.is_configured(),
            "channel": slack_notifier.default_channel,
        },
        "jira": {
            "configured": jira_client.is_configured(),
            "server": jira_client.server,
            "project": jira_client.project,
        }
    }


@app.post("/report/{job_id}/slack")
async def send_to_slack(
    job_id: str,
    channel: str = None
):
    """Send analysis result to Slack."""
    result = _get_result(job_id)
    if not result:
        raise HTTPException(404, "Job not found or not complete")

    outcome = slack_notifier.send_analysis_report(
        result, channel=channel, job_id=job_id
    )

    if not outcome["ok"]:
        raise HTTPException(400, outcome["error"])

    return outcome


@app.post("/report/{job_id}/jira")
async def create_jira_tickets(
    job_id: str,
    max_tickets: int = 10,
    min_severity: str = "medium",
):
    """Create Jira tickets for top debt items."""
    result = _get_result(job_id)
    if not result:
        raise HTTPException(404, "Job not found or not complete")

    outcome = jira_client.create_tickets_for_analysis(
        result,
        max_tickets=max_tickets,
        min_severity=min_severity,
    )

    if not outcome.get("ok"):
        raise HTTPException(400, outcome.get("error", "Unknown error"))

    return outcome


def _get_result(job_id: str) -> dict | None:
    """Load result from memory or DB."""
    if job_id in jobs:
        job = jobs[job_id]
        if job["status"] == "complete":
            return job["result"]
        return None

    from database.connection import SessionLocal
    from database.models import Scan
    db = SessionLocal()
    scan = db.query(Scan).filter(
        Scan.job_id == job_id
    ).first()
    db.close()
    return scan.raw_result if scan else None


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
