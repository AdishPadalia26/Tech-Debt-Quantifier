"""Jira integration helpers."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SEVERITY_TO_PRIORITY = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "minor": "Low",
    "major": "High",
    "blocker": "Highest",
    "info": "Low",
}

CATEGORY_TO_LABEL = {
    "code_quality": "tech-debt-code",
    "security": "tech-debt-security",
    "documentation": "tech-debt-docs",
    "dependency": "tech-debt-deps",
    "test_debt": "tech-debt-tests",
    "performance": "tech-debt-perf",
    "architecture": "tech-debt-arch",
}

ISSUE_TYPE_FALLBACK = ["Task", "Story", "Bug", "Sub-task", "Issue"]
EPIC_TYPE_FALLBACK = ["Epic", "Initiative"]


class JiraClient:
    """Thin Jira wrapper for integration and ticket export flows."""

    def __init__(self) -> None:
        self.server = (os.getenv("JIRA_SERVER") or "").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL") or ""
        self.token = os.getenv("JIRA_API_TOKEN") or ""
        self.project = (os.getenv("JIRA_PROJECT_KEY") or "TD").upper()
        self._jira = None
        self._meta: Optional[dict[str, dict]] = None

    def is_configured(self) -> bool:
        """Return True when the minimum Jira credentials are present."""
        return bool(
            self.server
            and self.email
            and self.token
            and self.server.startswith("http")
        )

    @property
    def jira(self):
        """Lazily construct the Jira client."""
        if not self._jira:
            from jira import JIRA

            self._jira = JIRA(
                server=self.server,
                basic_auth=(self.email, self.token),
                options={"verify": True},
            )
        return self._jira

    def test_connection(self) -> dict:
        """Verify credentials and return project info."""
        if not self.is_configured():
            return {
                "ok": False,
                "error": (
                    "Jira not configured. "
                    "Set JIRA_SERVER, JIRA_EMAIL, JIRA_API_TOKEN, "
                    "and JIRA_PROJECT_KEY in your .env file."
                ),
            }
        try:
            myself = self.jira.myself()
            project = self.jira.project(self.project)
            return {
                "ok": True,
                "user": myself.get("displayName", self.email),
                "project_key": self.project,
                "project_name": str(project),
                "server": self.server,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _get_project_meta(self) -> dict[str, dict]:
        """Cache and return createmeta for the configured project."""
        if self._meta is not None:
            return self._meta
        try:
            meta = self.jira.createmeta(
                projectKeys=self.project,
                expand="projects.issuetypes.fields",
            )
            projects = meta.get("projects", [])
            if projects:
                self._meta = {
                    issue_type["name"]: issue_type
                    for issue_type in projects[0].get("issuetypes", [])
                }
            else:
                self._meta = {}
        except Exception as exc:
            logger.warning("Could not fetch project meta: %s", exc, exc_info=True)
            self._meta = {}
        return self._meta

    def _resolve_issue_type(self, preferred_list: list[str]) -> str:
        """Return the first issue type that exists in this project."""
        meta = self._get_project_meta()
        if not meta:
            return preferred_list[0]
        for name in preferred_list:
            if name in meta:
                return name
        available = list(meta.keys())
        logger.warning(
            "None of %s found in project. Available: %s. Using %s.",
            preferred_list,
            available,
            available[0] if available else preferred_list[0],
        )
        return available[0] if available else preferred_list[0]

    def _epic_link_field(self) -> Optional[str]:
        """Return the field id for Epic Link when available."""
        try:
            fields = self.jira.fields()
            for field in fields:
                name = (field.get("name") or "").lower()
                if name in ("epic link", "epic name", "parent epic"):
                    return field["id"]
        except Exception:
            pass

        for candidate in ["customfield_10014", "customfield_10008"]:
            try:
                meta = self._get_project_meta()
                for issue_type in meta.values():
                    if candidate in issue_type.get("fields", {}):
                        return candidate
            except Exception:
                pass
        return None

    @staticmethod
    def _wiki(text: str) -> str:
        """Convert simple markdown-ish syntax to Jira wiki markup."""
        import re

        text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
        text = re.sub(r"`([^`]+)`", r"{{\1}}", text)
        return text

    def _build_description(self, item: dict, repo_url: str) -> str:
        """Build a Jira-friendly issue description."""
        import re

        file_path = str(item.get("file") or "unknown")
        file_path = re.sub(r"^/tmp/repos/[^/]+/", "", file_path)
        file_path = re.sub(r":\?$|:\d+$", "", file_path)

        severity = (item.get("severity") or "medium").upper()
        category = (item.get("category") or "code_quality").replace("_", " ").title()
        cost = item.get("cost_usd", 0)
        base_cost = item.get("base_cost_usd", cost)
        hours = (item.get("adjusted_minutes") or 0) / 60
        multiplier = item.get("combined_multiplier", 1.0)
        complexity = item.get("complexity", "N/A")
        func_name = item.get("function") or ""
        explanation = item.get("cost_explanation") or ""

        drivers = item.get("cost_factors") or []
        driver_lines = (
            "\n".join(
                f"* {driver['label']}: {driver['value']}"
                for driver in drivers
                if isinstance(driver, dict)
            )
            if drivers
            else ""
        )

        description = f"""h2. Tech Debt Item

||Field||Value||
|File|{{{{+{file_path}+}}}}|
|Function|{func_name or 'N/A'}|
|Category|{category}|
|Severity|*{severity}*|

h2. Cost Estimate

||Metric||Value||
|Base Cost|${base_cost:,.0f}|
|Final Cost|*${cost:,.0f}*|
|Remediation Hours|{hours:.1f} h|
|Risk Multiplier|{multiplier:.2f}x|
|Complexity Score|{complexity}|

h2. Repository

{repo_url}

"""
        if explanation:
            description += f"h2. Why This Costs More\n\n{self._wiki(explanation)}\n\n"

        if driver_lines:
            description += f"h2. Cost Drivers\n\n{driver_lines}\n\n"

        description += "_Generated by Tech Debt Quantifier_"
        return description

    def _build_epic_description(self, result: dict, analysis: dict) -> str:
        """Build a Jira-friendly epic description."""
        repo = result.get("github_url", "Unknown")
        cost = analysis.get("total_cost_usd", 0)
        score = analysis.get("debt_score", 0)
        hours = analysis.get("total_remediation_hours", 0)
        sprints = analysis.get("total_remediation_sprints", 0)
        summary = (
            result.get("executive_summary")
            or analysis.get("executive_summary")
            or "N/A"
        )

        return f"""h2. Technical Debt Audit

||Metric||Value||
|Repository|{repo}|
|Total Estimated Cost|*${cost:,.0f}*|
|Debt Score|*{score:.1f} / 10*|
|Remediation Hours|{hours:.0f} h|
|Sprints Required|{sprints:.1f}|

h2. Executive Summary

{summary}

_Generated by Tech Debt Quantifier_"""

    def _safe_labels(self, raw: list[str]) -> list[str]:
        """Normalize Jira labels to Jira-safe values."""
        cleaned = [label.replace(" ", "-") for label in raw if label]
        return cleaned[:10]

    def _create_epic(self, result: dict, analysis: dict) -> Optional[str]:
        """Create an epic when the project supports it."""
        try:
            repo = result.get("github_url", "Unknown")
            repo_name = repo.split("/")[-1] if "/" in repo else repo
            cost = analysis.get("total_cost_usd", 0)
            score = analysis.get("debt_score", 0)
            summary = (
                f"[Tech Debt] {repo_name} - "
                f"${cost:,.0f} total (score {score:.1f}/10)"
            )[:255]

            epic_type = self._resolve_issue_type(EPIC_TYPE_FALLBACK)
            fields: dict = {
                "project": {"key": self.project},
                "summary": summary,
                "description": self._build_epic_description(result, analysis),
                "issuetype": {"name": epic_type},
                "labels": self._safe_labels(["tech-debt", "automated"]),
            }

            if epic_type == "Epic":
                fields["customfield_10011"] = repo_name

            epic = self.jira.create_issue(fields=fields)
            logger.info("Created Epic: %s", epic.key)
            return epic.key

        except Exception as exc:
            logger.warning("Could not create Epic (non-fatal): %s", exc, exc_info=True)
            return None

    def _create_single_ticket(
        self,
        item: dict,
        repo_url: str,
        epic_key: Optional[str],
    ):
        """Create a Jira issue for a single debt item."""
        import re

        file_path = str(item.get("file") or "unknown")
        file_path = re.sub(r"^/tmp/repos/[^/]+/", "", file_path)
        file_path = re.sub(r":\?$|:\d+$", "", file_path)

        category = (item.get("category") or "code_quality").replace("_", " ").title()
        severity = (item.get("severity") or "medium").lower()
        cost = item.get("cost_usd", 0)
        func_name = item.get("function") or ""

        priority_name = SEVERITY_TO_PRIORITY.get(severity, "Medium")
        label = CATEGORY_TO_LABEL.get(item.get("category", "code_quality"), "tech-debt")

        summary = (
            f"[{category}] {file_path}"
            + (f" - {func_name}" if func_name else "")
            + f" (${cost:,.0f})"
        )[:255]

        issue_type = self._resolve_issue_type(ISSUE_TYPE_FALLBACK)

        fields: dict = {
            "project": {"key": self.project},
            "summary": summary,
            "description": self._build_description(item, repo_url),
            "issuetype": {"name": issue_type},
            "priority": {"name": priority_name},
            "labels": self._safe_labels([label, "tech-debt", "automated"]),
        }

        if epic_key:
            epic_field = self._epic_link_field()
            if epic_field:
                fields[epic_field] = epic_key
            else:
                fields["parent"] = {"key": epic_key}

        return self.jira.create_issue(fields=fields)

    def create_tickets_for_analysis(
        self,
        result: dict,
        max_tickets: int = 10,
        min_severity: str = "medium",
    ) -> dict:
        """Create Jira tickets for the highest-cost eligible debt items."""
        if not self.is_configured():
            return {
                "ok": False,
                "error": (
                    "Jira not configured. "
                    "Set JIRA_SERVER, JIRA_EMAIL, JIRA_API_TOKEN, "
                    "JIRA_PROJECT_KEY in your .env file."
                ),
            }

        analysis = result.get("raw_analysis") or {}
        repo_url = result.get("github_url", "Unknown")
        debt_items = analysis.get("debt_items") or []

        if not debt_items:
            return {
                "ok": False,
                "error": (
                    "No debt items found in this analysis result. "
                    "The scan may have completed with 0 findings."
                ),
            }

        severity_order = [
            "critical",
            "blocker",
            "high",
            "major",
            "medium",
            "low",
            "minor",
            "info",
        ]
        try:
            min_idx = severity_order.index(min_severity.lower())
        except ValueError:
            min_idx = severity_order.index("medium")

        eligible = [
            item
            for item in debt_items
            if severity_order.index(
                (item.get("severity") or "medium").lower()
                if (item.get("severity") or "medium").lower() in severity_order
                else "medium"
            )
            <= min_idx
        ]

        eligible.sort(key=lambda item: item.get("cost_usd", 0), reverse=True)
        eligible = eligible[:max_tickets]

        if not eligible:
            return {
                "ok": False,
                "error": (
                    f"No items found at or above severity '{min_severity}'. "
                    "Try min_severity=low to include all items."
                ),
            }

        epic_key = self._create_epic(result, analysis)

        created = []
        failed = []

        for item in eligible:
            try:
                ticket = self._create_single_ticket(item, repo_url, epic_key)
                created.append(
                    {
                        "key": ticket.key,
                        "url": f"{self.server}/browse/{ticket.key}",
                        "file": item.get("file", ""),
                        "cost": item.get("cost_usd", 0),
                        "summary": ticket.fields.summary,
                    }
                )
                logger.info("Created ticket: %s", ticket.key)
            except Exception as exc:
                failed.append(
                    {
                        "file": item.get("file", "unknown"),
                        "error": str(exc),
                    }
                )
                logger.error("Failed ticket for %s: %s", item.get("file", "?"), exc)

        if not created:
            return {
                "ok": False,
                "error": "Jira did not create any tickets. Check project issue types and permissions.",
                "epic_key": epic_key,
                "epic_url": f"{self.server}/browse/{epic_key}" if epic_key else None,
                "created": created,
                "failed": failed,
                "total_created": 0,
                "total_failed": len(failed),
            }

        return {
            "ok": True,
            "epic_key": epic_key,
            "epic_url": f"{self.server}/browse/{epic_key}" if epic_key else None,
            "created": created,
            "failed": failed,
            "total_created": len(created),
            "total_failed": len(failed),
        }
