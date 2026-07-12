"""Tech Debt Quantifier - FastAPI backend server."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

load_dotenv()

from api.routes.analyze import router as analyze_router
from api.routes.auth import router as auth_router
from api.routes.github import router as github_router
from api.routes.health import router as health_router
from api.routes.integrations import router as integrations_router
from api.routes.portfolio import router as portfolio_router
from api.routes.repositories import router as repositories_router
from api.routes.reports import router as reports_router
from api.routes.scans import router as scans_router
from database.connection import DB_AVAILABLE, engine
from database.models import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 300


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Fail long-running HTTP requests with a consistent 504 response."""

    async def dispatch(self, request, call_next):  # type: ignore[override]
        start = time.time()
        try:
            return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            elapsed = time.time() - start
            logger.error("Request timed out after %.1fs: %s", elapsed, request.url.path)
            return JSONResponse(
                {"error": f"Request timed out after {elapsed:.0f}s"},
                status_code=504,
            )


app = FastAPI(
    title="Tech Debt Quantifier",
    version="0.2.0",
    description="Agentic AI platform for technical debt analysis",
)

app.add_middleware(TimeoutMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(analyze_router)
app.include_router(auth_router)
app.include_router(github_router)
app.include_router(portfolio_router)
app.include_router(repositories_router)
app.include_router(reports_router)
app.include_router(scans_router)
app.include_router(integrations_router)


@app.on_event("startup")
async def startup_event() -> None:
    """Create database tables and pre-probe Redis availability."""
    if DB_AVAILABLE:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables verified/created")
        except Exception as exc:
            logger.error("Table creation failed: %s", exc)
    logger.info("Database available: %s", DB_AVAILABLE)

    # Pre-probe Redis availability in a background thread so the blocking
    # TCP connect attempt doesn't stall the first request.
    from services.job_service import _do_probe
    import threading
    threading.Thread(target=_do_probe, daemon=True, name="redis-probe-startup").start()


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("Tech Debt Quantifier API Server")
    print("=" * 50)
    print(f"Database: {'available' if DB_AVAILABLE else 'unavailable'}")
    print("Server starting at: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
