"""Health check routes."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter

from database.connection import DB_AVAILABLE
from services.analysis_runner import ORCHESTRATOR_AVAILABLE
from services.job_service import list_jobs as list_redis_jobs

router = APIRouter()


def _get_ollama_health() -> dict[str, Any]:
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


@router.get("/")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "project": "Tech Debt Quantifier",
        "version": "0.2.0",
        "orchestrator_available": ORCHESTRATOR_AVAILABLE,
        "database_available": DB_AVAILABLE,
    }


@router.get("/health")
async def detailed_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "1.0.0",
        "api": "ok",
        "orchestrator": "ok" if ORCHESTRATOR_AVAILABLE else "error",
        "database": "ok" if DB_AVAILABLE else "error",
        "active_jobs": len(list_redis_jobs()),
        "env_vars": {
            "GROQ_API_KEY": "set" if os.getenv("GROQ_API_KEY") else "missing",
            "NVIDIA_NIM_API_KEY": "set" if os.getenv("NVIDIA_NIM_API_KEY") else "missing",
            "OPENAI_API_KEY": "set" if os.getenv("OPENAI_API_KEY") else "missing",
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "not set"),
            "DATABASE_URL": "set" if os.getenv("DATABASE_URL") else "missing",
        },
        "ollama": _get_ollama_health(),
    }
