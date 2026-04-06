"""Orchestrator agent for Tech Debt Quantifier using LangGraph."""

import uuid
from typing import Literal

from langgraph.graph import END, StateGraph

from agents.analyzer import AnalyzerAgent
from agents.crawler import CrawlerAgent
from agents.reporter import ReporterAgent
from agents.state import AgentState


class TechDebtOrchestrator:
    """LangGraph orchestrator that runs the full analysis pipeline."""

    def __init__(self) -> None:
        self.crawler = CrawlerAgent()
        self.analyzer = AnalyzerAgent()
        self.reporter = ReporterAgent()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        workflow.add_node("crawler", self.crawler.run)
        workflow.add_node("analyzer", self.analyzer.run)
        workflow.add_node("reporter", self.reporter.run)

        workflow.set_entry_point("crawler")

        workflow.add_conditional_edges(
            "crawler",
            self._should_continue,
            {"continue": "analyzer", "end": END},
        )

        workflow.add_conditional_edges(
            "analyzer",
            self._should_continue,
            {"continue": "reporter", "end": END},
        )

        workflow.add_edge("reporter", END)

        return workflow.compile()

    def _should_continue(self, state: AgentState) -> Literal["continue", "end"]:
        """Route to next agent or end based on status."""
        if state.get("status") == "failed":
            return "end"
        return "continue"

    async def run_analysis(
        self, github_url: str, repo_id: str | None = None
    ) -> dict:
        """Run full analysis pipeline for a GitHub repo."""
        if not repo_id:
            repo_id = f"{github_url.split('/')[-1]}-{str(uuid.uuid4())[:8]}"

        initial_state: AgentState = {
            "github_url": github_url,
            "repo_id": repo_id,
            "repo_path": None,
            "clone_status": None,
            "raw_analysis": None,
            "repo_profile": None,
            "executive_summary": None,
            "priority_actions": None,
            "roi_analysis": None,
            "llm_insights": None,
            "job_id": str(uuid.uuid4()),
            "status": "queued",
            "error": None,
            "messages": [],
        }

        final_state = await self.graph.ainvoke(initial_state)
        return final_state

    def format_report(self, state: dict) -> str:
        """Format final state into a readable report string."""
        if state.get("status") == "failed":
            return f"Analysis failed: {state.get('error')}"

        analysis = state.get("raw_analysis", {})

        report = f"""
================================================================================
                    TECHNICAL DEBT ANALYSIS REPORT                 
================================================================================

Repository: {state.get('github_url', 'Unknown')}

--- FINANCIAL SUMMARY ---
  Total Debt Cost:     ${analysis.get('total_cost_usd', 0):>10,.2f}
  Remediation Time:    {analysis.get('total_remediation_hours', 0):>10.1f} hours
  Sprints Required:    {analysis.get('total_remediation_sprints', 0):>10.1f} sprints
  Debt Score:          {analysis.get('debt_score', 0):>10.1f} / 10

--- EXECUTIVE SUMMARY ---
{state.get('executive_summary', 'Not generated')}

--- TOP 3 PRIORITY ACTIONS ---
"""
        for action in state.get("priority_actions", []):
            if "error" not in action:
                report += f"""
  [{action.get('rank')}] {action.get('title')}
      File:     {action.get('file_or_module')}
      Why:      {action.get('why')}
      Fix Cost: ${action.get('estimated_cost', 0):,.0f} ({action.get('estimated_hours', 0)} hours)
      Saves:    ${action.get('saves_per_month', 0):,.0f}/month
      When:     {action.get('sprint')}
"""

        roi = state.get("roi_analysis", {})
        if roi and "error" not in roi:
            report += f"""
--- ROI ANALYSIS ---
  Fix Investment:      ${roi.get('total_fix_cost', 0):>10,.0f}
  Annual Savings:      ${roi.get('annual_maintenance_savings', 0):>10,.0f}
  Payback Period:      {roi.get('payback_months', 0):>10} months
  3-Year ROI:          {roi.get('3_year_roi_pct', 0):>9}%
  Quarterly Budget:    ${roi.get('recommended_budget', 0):>10,.0f}

  {roi.get('recommendation', '')}
"""

        report += "\n================================================================================"
        return report
