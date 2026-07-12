"""Analyzer agent for Tech Debt Quantifier."""

import asyncio

from agents.state import AgentState
from services.job_service import update_job
from tools.cost_estimator import CostEstimator


class AnalyzerAgent:
    """Agent that runs static analysis, git mining, and cost estimation."""

    async def run(self, state: AgentState) -> AgentState:
        """Run full analysis pipeline on cloned repo."""
        if state.get("status") == "failed":
            return state

        repo_path = state["repo_path"]
        github_url = state["github_url"]

        try:
            state["status"] = "analyzing"

            estimator = CostEstimator()
            repo_path_str = repo_path or ""

            def update_analysis_progress(progress: int, phase: str) -> None:
                """Publish analyzer substep progress for the polling UI."""
                job_id = state.get("job_id")
                if job_id:
                    update_job(job_id, progress=progress, phase=phase)

            analysis = await asyncio.to_thread(
                estimator.estimate_total_cost,
                repo_path_str,
                github_url,
                update_analysis_progress,
            )

            state["raw_analysis"] = analysis
            state["repo_profile"] = analysis.get("repo_profile", {})
            state["status"] = "analysis_complete"

        except Exception as e:
            state["error"] = str(e)
            state["status"] = "failed"

        return state
