"""Tech Debt Quantifier - FastAPI Backend Server."""

import logging
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
async def root() -> dict:
    """Health check endpoint."""
    logger.info("Health check requested")
    return {
        "status": "ok",
        "project": "Tech Debt Quantifier",
        "version": "0.1.0",
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Submit a repository for technical debt analysis.
    
    Args:
        request: AnalyzeRequest containing github_url and repo_id
    
    Returns:
        AnalyzeResponse with job_id and status
    """
    job_id = str(uuid.uuid4())
    logger.info(f"Analysis queued for repo: {request.repo_id} (job_id: {job_id})")
    
    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message=f"Analysis queued for {request.github_url}",
    )


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> dict:
    """
    Get results for a specific analysis job.
    
    Args:
        job_id: The unique job identifier
    
    Returns:
        Job status and results (mocked for Sprint 1)
    """
    logger.info(f"Results requested for job: {job_id}")
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Analysis in progress",
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
