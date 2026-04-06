"""Reporter agent for local-LLM-assisted executive outputs."""

from __future__ import annotations

from agents.state import AgentState
from intelligence.architecture_review_agent import ArchitectureReviewAgent
from intelligence.local_llm_service import LocalLLMService
from intelligence.report_writer_agent import ReportWriterAgent
from intelligence.semantic_triage_agent import SemanticTriageAgent
from intelligence.test_gap_agent import GapReviewAgent


class ReporterAgent:
    """Generate executive outputs and bounded local-LLM insights."""

    def __init__(self) -> None:
        llm_service = LocalLLMService()
        self.semantic_triage = SemanticTriageAgent(llm_service)
        self.architecture_review = ArchitectureReviewAgent(llm_service)
        self.test_gap_review = GapReviewAgent(llm_service)
        self.report_writer = ReportWriterAgent(llm_service)

    async def run(self, state: AgentState) -> AgentState:
        """Generate executive summary, priorities, ROI, and local-LLM insights."""
        if state.get("status") == "failed":
            return state

        analysis = state.get("raw_analysis") or {}
        findings = analysis.get("findings") or []
        modules = analysis.get("module_summaries") or []
        architecture_findings = [
            finding for finding in findings if finding.get("category") == "architecture"
        ]
        test_findings = [
            finding for finding in findings if finding.get("category") == "test_debt"
        ]

        triage_items = await self.semantic_triage.triage(findings)
        architecture_review = await self.architecture_review.review(
            architecture_findings,
            modules,
        )
        test_gap_review = await self.test_gap_review.review(test_findings)

        llm_insights = {
            "semantic_triage": triage_items,
            "architecture_review": architecture_review,
            "test_gap_review": test_gap_review,
            "provider": "local",
        }
        executive_summary = await self.report_writer.executive_summary(
            analysis,
            llm_insights,
        )
        priority_actions = await self.report_writer.priority_actions(
            findings,
            triage_items,
        )
        roi_analysis = self.report_writer.roi_analysis(analysis)

        state["executive_summary"] = executive_summary
        state["priority_actions"] = priority_actions
        state["roi_analysis"] = roi_analysis
        state["llm_insights"] = llm_insights

        if isinstance(state.get("raw_analysis"), dict):
            state["raw_analysis"]["llm_insights"] = llm_insights

        state["status"] = "complete"
        return state
