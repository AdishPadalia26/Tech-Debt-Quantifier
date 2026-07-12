"""Report routes."""

import logging

from fastapi import APIRouter, HTTPException

from database.connection import SessionLocal
from services.report_service import (
    build_pdf_response,
    ensure_complete_result,
    get_result_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


@router.get("/report/{job_id}/pdf")
async def download_pdf_report(job_id: str):
    """Generate and download a PDF report for a completed analysis job."""
    db = SessionLocal()
    try:
        result = ensure_complete_result(job_id, get_result_payload(job_id, db))
        return build_pdf_response(job_id, result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("PDF generation failed for %s", job_id)
        raise HTTPException(500, f"PDF generation failed: {exc}") from exc
    finally:
        db.close()
