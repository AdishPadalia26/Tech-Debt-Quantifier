"""Tech Debt Quantifier - FastAPI Backend Server."""

import os
import uuid
import logging
import traceback
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import models
from models.schemas import AnalyzeRequest, AnalyzeResponse

# Import orchestrator with error handling
try:
    from agents.orchestrator import TechDebtOrchestrator
    ORCHESTRATOR_AVAILABLE = True
    logger.info("TechDebtOrchestrator loaded successfully")
except Exception as e:
    ORCHESTRATOR_AVAILABLE = False
    logger.error(f"TechDebtOrchestrator failed to load: {e}")
    logger.error(traceback.format_exc())

# In-memory job store
jobs: Dict[str, Any] = {}

app = FastAPI(
    title="Tech Debt Quantifier",
    version="0.1.0",
    description="Agentic AI platform for technical debt analysis",
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "project": "Tech Debt Quantifier",
        "version": "0.1.0",
        "orchestrator_available": ORCHESTRATOR_AVAILABLE,
    }


@app.get("/health")
async def detailed_health() -> dict:
    """Detailed health check for debugging."""
    return {
        "api": "ok",
        "orchestrator": "ok" if ORCHESTRATOR_AVAILABLE else "error",
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
        raise HTTPException(
            status_code=503,
            detail="Analysis engine failed to load. Check server logs.",
        )

    # Validate GitHub URL
    if "github.com" not in request.github_url:
        raise HTTPException(
            status_code=400,
            detail="URL must be a GitHub repository (github.com)",
        )

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued",
        "result": None,
        "error": None,
        "github_url": request.github_url,
    }

    logger.info(f"Job {job_id} queued for {request.github_url}")

    repo_id = request.repo_id or request.github_url.split("/")[-1]

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
    """Background task — runs full agent pipeline."""
    try:
        logger.info(f"Job {job_id}: starting analysis of {github_url}")
        jobs[job_id]["status"] = "running"

        orchestrator = TechDebtOrchestrator()
        result = await orchestrator.run_analysis(github_url, repo_id)

        # Flatten raw_analysis into top-level for frontend compatibility
        raw_analysis = result.pop("raw_analysis", {}) or {}
        flat_result = {**result, **raw_analysis}

        jobs[job_id]["status"] = flat_result.get("status", "complete")
        jobs[job_id]["result"] = flat_result

        logger.info(f"Job {job_id}: completed successfully")

    except Exception as e:
        error_msg = str(e)
        full_trace = traceback.format_exc()
        logger.error(f"Job {job_id} failed: {error_msg}")
        logger.error(full_trace)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = error_msg
        jobs[job_id]["traceback"] = full_trace


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> dict:
    """Poll for analysis results."""

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = jobs[job_id]

    if job["status"] == "complete":
        result = job["result"]
        try:
            orchestrator = TechDebtOrchestrator()
            return {
                "job_id": job_id,
                "status": "complete",
                "report": orchestrator.format_report(result),
                "raw": result,
            }
        except Exception:
            return {
                "job_id": job_id,
                "status": "complete",
                "report": "Report formatting unavailable",
                "raw": result,
            }

    if job["status"] == "failed":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": job.get("error", "Unknown error"),
        }

    return {
        "job_id": job_id,
        "status": job["status"],
    }


@app.get("/jobs")
async def list_jobs() -> dict:
    """List all jobs — useful for debugging."""
    return {
        "total": len(jobs),
        "jobs": [
            {
                "job_id": jid,
                "status": j["status"],
                "url": j.get("github_url"),
                "error": j.get("error"),
            }
            for jid, j in jobs.items()
        ],
    }


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("Tech Debt Quantifier API Server")
    print("=" * 50)
    print("Server starting at: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
