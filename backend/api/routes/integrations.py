"""Optional integration routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from database.connection import SessionLocal
from integrations.jira_client import JiraClient
from integrations.slack_notifier import SlackNotifier
from services.report_service import ensure_complete_result, get_result_payload

router = APIRouter(tags=["integrations"])
_jobs_ref: dict[str, Any] = {}

slack_notifier = SlackNotifier()
jira_client = JiraClient()


def set_jobs_reference(jobs: dict[str, Any]) -> None:
    """Provide access to the in-memory jobs registry used by main.py."""
    global _jobs_ref
    _jobs_ref = jobs


@router.get("/integrations/status")
async def integrations_status():
    """Check which optional integrations are configured."""
    jira_ok = jira_client.is_configured()
    return {
        "slack": {
            "configured": slack_notifier.is_configured(),
            "channel": slack_notifier.default_channel,
        },
        "jira": {
            "configured": jira_ok,
            "server": jira_client.server if jira_ok else "",
            "project": jira_client.project,
        },
    }


@router.post("/report/{job_id}/slack")
async def send_to_slack(job_id: str, channel: str | None = None):
    """Send an analysis summary to Slack if configured."""
    db = SessionLocal()
    try:
        result = ensure_complete_result(job_id, get_result_payload(job_id, _jobs_ref, db))
    finally:
        db.close()

    outcome = slack_notifier.send_analysis_report(result, channel=channel, job_id=job_id)
    if not outcome.get("ok"):
        raise HTTPException(400, outcome.get("error", "Slack delivery failed"))
    return outcome


@router.post("/report/{job_id}/jira")
async def create_jira_tickets(
    job_id: str,
    max_tickets: int = 10,
    min_severity: str = "medium",
):
    db = SessionLocal()
    try:
        payload = get_result_payload(job_id, _jobs_ref, db)
    finally:
        db.close()

    if not payload:
        raise HTTPException(
            404,
            f"Job '{job_id}' not found or not complete yet. "
            "Wait for the scan to finish before creating tickets.",
        )

    result = ensure_complete_result(job_id, payload)
    outcome = jira_client.create_tickets_for_analysis(
        result,
        max_tickets=max_tickets,
        min_severity=min_severity,
    )
    if not outcome.get("ok"):
        raise HTTPException(400, outcome.get("error", "Jira error"))
    return outcome


@router.get("/jira/test")
async def test_jira_connection():
    """Test Jira credentials without creating issues."""
    return jira_client.test_connection()
