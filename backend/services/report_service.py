"""Report and integration service helpers."""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database.models import Scan

logger = logging.getLogger(__name__)


def get_result_payload(job_id: str, jobs: dict[str, Any], db: Session) -> dict[str, Any] | None:
    """Load result payload from memory first, then persisted scans."""
    if job_id in jobs:
        job = jobs[job_id]
        if job.get("status") == "complete":
            return job.get("result")
        return None

    scan = db.query(Scan).filter(Scan.job_id == job_id).first()
    return scan.raw_result if scan else None


def build_pdf_response(job_id: str, result: dict[str, Any]) -> StreamingResponse:
    """Generate a downloadable PDF response from a completed analysis result."""
    from reports.pdf_generator import TechDebtPDFGenerator

    generator = TechDebtPDFGenerator()
    analysis = result.get("raw_analysis") or result
    pdf_bytes = generator.generate(analysis, result)
    repo_name = (result.get("github_url", "report").split("/")[-1]) or "report"
    filename = f"tech-debt-{repo_name}-{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def ensure_complete_result(job_id: str, result: dict[str, Any] | None) -> dict[str, Any]:
    """Return a completed result or raise a 404-style HTTP error."""
    if not result:
        raise HTTPException(404, f"Job {job_id} not found or not complete")
    return result
