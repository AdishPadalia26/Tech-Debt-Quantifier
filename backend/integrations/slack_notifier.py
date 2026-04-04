import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Sends tech debt analysis summaries to Slack."""

    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")
        self.default_channel = os.getenv(
            "SLACK_DEFAULT_CHANNEL", "#all-tech-debt"
        )
        self._client = None

    @property
    def client(self):
        if not self._client:
            from slack_sdk import WebClient
            self._client = WebClient(token=self.token)
        return self._client

    def is_configured(self) -> bool:
        return bool(self.token and self.token != "xoxb-your-token-here")

    def send_analysis_report(
        self,
        result: dict,
        channel: str = None,
        job_id: str = None
    ) -> dict:
        """
        Send a rich Slack message for a completed analysis.
        Returns {"ok": True, "ts": "..."} or {"ok": False, "error": "..."}
        """
        if not self.is_configured():
            return {"ok": False, "error": "Slack not configured"}

        channel = channel or self.default_channel

        try:
            analysis = result.get("raw_analysis", {})
            blocks = self._build_blocks(analysis, result, job_id)

            response = self.client.chat_postMessage(
                channel=channel,
                text=self._build_fallback_text(analysis, result),
                blocks=blocks,
                unfurl_links=False,
            )
            logger.info(
                f"Slack notification sent to {channel}: "
                f"ts={response['ts']}"
            )
            return {"ok": True, "ts": response["ts"],
                    "channel": channel}

        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            return {"ok": False, "error": str(e)}

    def _build_fallback_text(self, analysis: dict,
                              result: dict) -> str:
        repo = result.get("github_url", "Unknown")
        cost = analysis.get("total_cost_usd", 0)
        score = analysis.get("debt_score", 0)
        return (
            f"🔍 Tech Debt Report: {repo} | "
            f"Score: {score:.1f}/10 | "
            f"Total Cost: ${cost:,.0f}"
        )

    def _build_blocks(self, analysis: dict,
                       result: dict, job_id: str) -> list:
        repo = result.get("github_url", "Unknown")
        repo_name = repo.split("/")[-1] if "/" in repo else repo

        cost = analysis.get("total_cost_usd", 0)
        score = analysis.get("debt_score", 0)
        hours = analysis.get("total_remediation_hours", 0)
        sprints = analysis.get("total_remediation_sprints", 0)

        # Score emoji
        if score <= 3:
            score_emoji = "🟢"
        elif score <= 6:
            score_emoji = "🟡"
        else:
            score_emoji = "🔴"

        # Categories
        categories = analysis.get("cost_by_category", {})
        top_cats = sorted(
            [(k, v.get("cost_usd", 0))
             for k, v in categories.items()
             if isinstance(v, dict)],
            key=lambda x: x[1],
            reverse=True
        )[:3]

        cat_lines = "\n".join(
            f"  -  {k.replace('_', ' ').title()}: "
            f"*${v:,.0f}*"
            for k, v in top_cats
        )

        # Priority actions
        actions = result.get("priority_actions", [])
        action_lines = "\n".join(
            f"  {i+1}. *{a.get('title','')}* — "
            f"${a.get('estimated_cost',0):,.0f} "
            f"({a.get('estimated_hours',0)}h)"
            for i, a in enumerate(actions[:3])
            if "error" not in a
        )

        # ROI
        roi = result.get("roi_analysis", {})
        roi_text = ""
        if roi and roi.get("annual_maintenance_savings", 0) > 0:
            roi_text = (
                f"*ROI:* Fix costs ${roi.get('total_fix_cost',0):,.0f} → "
                f"saves ${roi.get('annual_maintenance_savings',0):,.0f}/yr "
                f"-  Payback in {roi.get('payback_months',0)} months"
            )

        # Executive summary (truncated)
        summary = result.get("executive_summary", "")
        if summary and len(summary) > 300:
            summary = summary[:297] + "..."

        blocks = [
            # Header
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔍 Tech Debt Report: {repo_name}",
                    "emoji": True,
                }
            },
            # Context
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": (
                        f"*Repository:* <{repo}|{repo}> -  "
                        f"*Analyzed:* "
                        f"{datetime.now().strftime('%b %d, %Y %H:%M')}"
                    )
                }]
            },
            {"type": "divider"},
            # Key metrics
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*{score_emoji} Debt Score*\n"
                            f"`{score:.1f} / 10`"
                        )
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*💰 Total Cost*\n"
                            f"`${cost:,.0f}`"
                        )
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*⏱ Remediation*\n"
                            f"`{hours:.0f} hours`"
                        )
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*🏃 Sprints Needed*\n"
                            f"`{sprints:.1f} sprints`"
                        )
                    },
                ]
            },
        ]

        # Executive summary
        if summary:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Executive Summary*\n{summary}"
                }
            })

        # Cost breakdown
        if cat_lines:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*💸 Cost Breakdown*\n{cat_lines}"
                }
            })

        # Priority actions
        if action_lines:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*🎯 Top Priority Actions*\n"
                        f"{action_lines}"
                    )
                }
            })

        # ROI
        if roi_text:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": roi_text}
            })

        blocks.append({"type": "divider"})

        # Action buttons
        buttons = [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "📄 Download PDF",
                    "emoji": True
                },
                "url": (
                    f"http://localhost:8000/report/"
                    f"{job_id}/pdf"
                ) if job_id else repo,
                "style": "primary",
            }
        ]

        blocks.append({
            "type": "actions",
            "elements": buttons
        })

        return blocks