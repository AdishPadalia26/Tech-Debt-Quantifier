"""Report routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from database.connection import SessionLocal
from services.report_service import (
    build_pdf_response,
    ensure_complete_result,
    get_result_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])
_jobs_ref: dict[str, Any] = {}


def set_jobs_reference(jobs: dict[str, Any]) -> None:
    """Provide access to the in-memory jobs registry used by main.py."""
    global _jobs_ref
    _jobs_ref = jobs


@router.get("/report/{job_id}/pdf")
async def download_pdf_report(job_id: str):
    """Generate and download a PDF report for a completed analysis job."""
    db = SessionLocal()
    try:
        result = ensure_complete_result(job_id, get_result_payload(job_id, _jobs_ref, db))
        return build_pdf_response(job_id, result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("PDF generation failed for %s", job_id)
        raise HTTPException(500, f"PDF generation failed: {exc}") from exc
    finally:
        db.close()
