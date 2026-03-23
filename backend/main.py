"""Tech Debt Quantifier - FastAPI Backend Server."""

import logging
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agents.orchestrator import TechDebtOrchestrator
from models.schemas import AnalyzeRequest, AnalyzeResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Tech Debt Quantifier",
    description="AI-powered technical debt analysis platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: dict = {}


@app.get("/")
async def root() -> dict:
    """Health check endpoint."""
    logger.info("Health check requested")
    return {
        "status": "ok",
        "project": "Tech Debt Quantifier",
        "version": "0.1.0",
    }


async def run_analysis_job(job_id: str, github_url: str, repo_id: str | None) -> None:
    """Background task that runs the full agent pipeline."""
    try:
        jobs[job_id]["status"] = "running"
        orchestrator = TechDebtOrchestrator()
        result = await orchestrator.run_analysis(github_url, repo_id)
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["result"] = result
    except Exception as e:
        logger.exception("Analysis job failed")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest, background_tasks: BackgroundTasks
) -> AnalyzeResponse:
    """Start async analysis of a GitHub repo."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "result": None}

    background_tasks.add_task(
        run_analysis_job, job_id, request.github_url, request.repo_id
    )

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis started. Poll /results/{job_id} for updates.",
    )


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> dict:
    """Poll for analysis results."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    if job["status"] == "complete":
        orchestrator = TechDebtOrchestrator()
        report = orchestrator.format_report(job["result"])
        return {
            "job_id": job_id,
            "status": "complete",
            "report": report,
            "raw": job["result"],
        }

    return {"job_id": job_id, "status": job["status"]}


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("Tech Debt Quantifier API Server")
    print("=" * 50)
    print("Server starting at: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
