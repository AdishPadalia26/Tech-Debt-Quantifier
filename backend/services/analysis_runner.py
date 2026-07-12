"""Background analysis pipeline, result cache, and URL utilities."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from database.connection import SessionLocal
from database.crud import save_scan
from mcp_server import REPOS_DIR
from models.normalize import normalize_analysis_result
from services.job_service import get_job, job_exists, update_job

logger = logging.getLogger(__name__)

try:
    from agents.orchestrator import TechDebtOrchestrator  # noqa: F401

    ORCHESTRATOR_AVAILABLE = True
    logger.info("TechDebtOrchestrator loaded successfully")
except Exception as exc:
    ORCHESTRATOR_AVAILABLE = False
    logger.error("TechDebtOrchestrator failed to load: %s", exc)
    logger.error(traceback.format_exc())

_result_cache: dict[str, tuple[dict[str, Any], datetime]] = {}

CACHE_TTL_MINUTES = 30
CLONE_TIMEOUT_SECONDS = int(os.getenv("ANALYSIS_CLONE_TIMEOUT_SECONDS", "180"))
ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "300"))
LLM_TIMEOUT_SECONDS = int(os.getenv("REPORT_TIMEOUT_SECONDS", "180"))

PHASES = [
    (5, "Cloning repository"),
    (20, "Preparing analysis"),
    (92, "Generating report"),
    (96, "Finalizing report"),
]

CACHED_REPOS_DIR = REPOS_DIR.resolve()


def get_cached_result(github_url: str) -> dict[str, Any] | None:
    key = hashlib.md5(github_url.encode("utf-8")).hexdigest()
    cached = _result_cache.get(key)
    if not cached:
        return None
    result, cached_at = cached
    if datetime.now(timezone.utc) - cached_at < timedelta(minutes=CACHE_TTL_MINUTES):
        logger.info("Cache hit for %s", github_url)
        return result
    _result_cache.pop(key, None)
    return None


def set_cached_result(github_url: str, result: dict[str, Any]) -> None:
    key = hashlib.md5(github_url.encode("utf-8")).hexdigest()
    _result_cache[key] = (result, datetime.now(timezone.utc))


def update_progress(job_id: str, pct: int, phase: str) -> None:
    if not job_exists(job_id):
        return
    update_job(job_id, progress=pct, phase=phase)
    logger.info("Job %s: %s%% - %s", job_id, pct, phase)


async def run_with_timeout(
    coro_or_func: Any, timeout_seconds: int = 120, *args: Any, **kwargs: Any
) -> Any:
    name = getattr(coro_or_func, "__qualname__", None) or getattr(
        coro_or_func, "__name__", coro_or_func.__class__.__name__
    )
    try:
        if asyncio.iscoroutinefunction(coro_or_func):
            return await asyncio.wait_for(
                coro_or_func(*args, **kwargs),
                timeout=timeout_seconds,
            )
        if asyncio.iscoroutine(coro_or_func):
            return await asyncio.wait_for(coro_or_func, timeout=timeout_seconds)
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: coro_or_func(*args, **kwargs)),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"{name} timed out after {timeout_seconds}s") from exc


def _validate_github_url(url: str) -> str:
    """Validate and canonicalize a GitHub repo URL, rejecting SSRF vectors."""
    from urllib.parse import urlparse
    from fastapi import HTTPException

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"https", "http"}:
        raise HTTPException(400, "URL must use http(s)")
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise HTTPException(400, "Host must be github.com")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise HTTPException(400, "URL must be github.com/<owner>/<repo>")
    return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}"


def normalize_repo_id(github_url: str) -> str:
    """Normalize repository identifiers to owner/repo."""
    url = github_url.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    if not url.startswith("http"):
        segments = url.strip("/").split("/")
        if len(segments) >= 2:
            return f"{segments[0]}/{segments[1]}"
        return url
    parts = (
        url.replace("https://github.com/", "")
        .replace("http://github.com/", "")
        .strip("/")
        .split("/")
    )
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return "/".join(parts)


def run_analysis_job(
    job_id: str,
    github_url: str,
    repo_id: str,
    user_id: int | None = None,
    github_access_token: str | None = None,
) -> None:
    """Run a full analysis pipeline in the background and persist the scan.

    Intentionally synchronous so Starlette's BackgroundTasks runner offloads it
    to a thread pool, keeping the FastAPI event loop free.

    On Windows, asyncio.run() defaults to ProactorEventLoop which conflicts with
    the main server's ProactorEventLoop via shared IOCP.  We use SelectorEventLoop
    explicitly in this worker thread to avoid that conflict.
    """
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                _run_pipeline(job_id, github_url, repo_id, user_id, github_access_token)
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    else:
        asyncio.run(
            _run_pipeline(job_id, github_url, repo_id, user_id, github_access_token)
        )


async def _run_pipeline(
    job_id: str,
    github_url: str,
    repo_id: str,
    user_id: int | None = None,
    github_access_token: str | None = None,
) -> None:
    """Async implementation of the analysis pipeline (runs inside a thread)."""
    start_time = time.time()
    repo_path: str | None = None
    try:
        from agents.analyzer import AnalyzerAgent
        from agents.crawler import CrawlerAgent
        from agents.reporter import ReporterAgent

        update_job(job_id, status="processing", error=None)
        update_progress(job_id, *PHASES[0])

        state: dict[str, Any] = {
            "github_url": github_url,
            "repo_id": repo_id,
            "github_access_token": github_access_token,
            "repo_path": None,
            "clone_status": None,
            "raw_analysis": None,
            "repo_profile": None,
            "findings": None,
            "module_summaries": None,
            "roadmap": None,
            "executive_summary": None,
            "priority_actions": None,
            "roi_analysis": None,
            "llm_insights": None,
            "job_id": job_id,
            "status": "queued",
            "error": None,
            "messages": [],
        }

        crawler = CrawlerAgent()
        analyzer = AnalyzerAgent()
        reporter = ReporterAgent()

        state = await run_with_timeout(crawler.run, CLONE_TIMEOUT_SECONDS, state)
        if state.get("status") == "failed":
            raise RuntimeError(state.get("error") or "Repository clone failed")

        repo_path = state.get("repo_path")
        update_job(job_id, repo_path=repo_path)
        update_progress(job_id, *PHASES[1])
        state = await run_with_timeout(analyzer.run, ANALYSIS_TIMEOUT_SECONDS, state)
        if state.get("status") == "failed":
            raise RuntimeError(state.get("error") or "Analysis pipeline failed")

        update_progress(job_id, *PHASES[2])
        state = await run_with_timeout(reporter.run, LLM_TIMEOUT_SECONDS, state)
        if state.get("status") == "failed":
            raise RuntimeError(state.get("error") or "Report generation failed")

        duration = time.time() - start_time
        raw_analysis = normalize_analysis_result(state.get("raw_analysis"))
        state["raw_analysis"] = raw_analysis
        state["status"] = "complete"

        update_job(job_id, status="complete", result=state)
        update_progress(job_id, *PHASES[3])
        update_job(job_id, progress=100, phase="Complete")
        set_cached_result(github_url, state)

        analysis_data = state.get("raw_analysis") or state
        if analysis_data.get("total_cost_usd"):
            try:
                db = SessionLocal()
                saved_scan = save_scan(
                    db=db,
                    job_id=job_id,
                    github_url=github_url,
                    analysis=analysis_data,
                    agent_state=state,
                    duration_seconds=duration,
                    user_id=user_id,
                )
                update_job(job_id, scan_id=saved_scan.id)
                logger.info("Scan saved to DB: %s", saved_scan.id)
                db.close()
            except Exception as db_err:
                logger.error("DB save failed (analysis still ok): %s", db_err)

        logger.info("Job %s completed in %.1fs", job_id, duration)
    except TimeoutError as exc:
        logger.error("Job %s timed out: %s", job_id, exc)
        logger.error(traceback.format_exc())
        update_job(job_id, status="error", error=f"Analysis timed out: {exc}")
    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc)
        logger.error(traceback.format_exc())
        update_job(job_id, status="error", error=str(exc))
    finally:
        job = get_job(job_id) or {}
        update_job(job_id, progress=min(int(job.get("progress") or 0), 100))
        if job.get("status") not in {"complete", "error"}:
            update_job(
                job_id,
                status="error",
                error=job.get("error") or "Analysis did not complete",
            )
        try:
            repo_path = (get_job(job_id) or {}).get("repo_path") or repo_path
            if repo_path and os.path.exists(repo_path):
                resolved_repo_path = os.path.abspath(repo_path)
                common = os.path.commonpath([resolved_repo_path, str(CACHED_REPOS_DIR)])
                if common == str(CACHED_REPOS_DIR):
                    logger.info(
                        "Preserving cached repository for job %s at %s",
                        job_id,
                        resolved_repo_path,
                    )
                else:
                    shutil.rmtree(repo_path, ignore_errors=True)
        except Exception:
            logger.warning("Failed to clean repo path for job %s", job_id)
