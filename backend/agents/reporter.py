"""Reporter agent for Tech Debt Quantifier."""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from agents.llm_factory import get_llm
from agents.state import AgentState


class ReporterAgent:
    """Agent that converts raw cost analysis into executive-ready insights."""

    def __init__(self) -> None:
        self.llm = get_llm()

    async def run(self, state: AgentState) -> AgentState:
        """Generate executive report from raw analysis data."""
        if state.get("status") == "failed":
            return state

        analysis = state.get("raw_analysis") or {}
        profile = state.get("repo_profile") or {}

        context = self._build_context(analysis, profile)

        summary = await self._generate_summary(context)
        priorities = await self._generate_priorities(context, analysis)
        roi = await self._generate_roi(context, analysis)

        state["executive_summary"] = summary
        state["priority_actions"] = priorities
        state["roi_analysis"] = roi
        state["status"] = "complete"

        return state

    def _build_context(self, analysis: dict, profile: dict) -> str:
        """Format analysis data into a clear context string for LLM."""
        tech_stack = profile.get("tech_stack", {})
        team = profile.get("team", {})
        multipliers = profile.get("multipliers", {})

        top_items = sorted(
            analysis.get("debt_items", []),
            key=lambda x: x.get("cost_usd", 0),
            reverse=True,
        )[:10]

        return f"""
REPOSITORY ANALYSIS RESULTS:

Repository: {analysis.get('repo_path', 'Unknown')}
Primary Language: {tech_stack.get('primary_language', 'Unknown')}
Framework: {', '.join(tech_stack.get('frameworks', ['Unknown']))}
Team Size: {team.get('estimated_team_size', 'Unknown')} engineers
Bus Factor: {team.get('bus_factor', 'Unknown')}
Repo Age: {team.get('repo_age_days', 0)} days

COST SUMMARY:
Total Technical Debt Cost: ${analysis.get('total_cost_usd', 0):,.2f}
Total Remediation Hours: {analysis.get('total_remediation_hours', 0):.1f} hours
Total Sprints Needed: {analysis.get('total_remediation_sprints', 0):.1f} sprints
Debt Score: {analysis.get('debt_score', 0):.1f} / 10

COST BY CATEGORY:
{self._format_categories(analysis.get('cost_by_category', {}))}

RISK MULTIPLIERS APPLIED:
{self._format_multipliers(multipliers)}

TOP 10 MOST EXPENSIVE DEBT ITEMS:
{self._format_top_items(top_items)}

RATE CONFIDENCE: {analysis.get('rate_confidence', {}).get('confidence', 'unknown')}
DATA SOURCES: {', '.join(analysis.get('data_sources_used', []))}
"""

    def _format_categories(self, categories: dict) -> str:
        lines = []
        for cat, data in categories.items():
            if isinstance(data, dict):
                lines.append(
                    f"  {cat}: ${data.get('cost_usd', 0):,.0f} "
                    f"({data.get('item_count', 0)} items, "
                    f"{data.get('hours', 0):.1f} hours)"
                )
        return "\n".join(lines)

    def _format_multipliers(self, multipliers: dict) -> str:
        lines = []
        for key, val in multipliers.items():
            if key != "combined_multiplier" and isinstance(val, (int, float)):
                lines.append(f"  {key}: {val}x")
        lines.append(f"  Combined: {multipliers.get('combined_multiplier', 1.0)}x")
        return "\n".join(lines)

    def _format_top_items(self, items: list) -> str:
        lines = []
        for i, item in enumerate(items, 1):
            lines.append(
                f"  {i}. {item.get('file', '?')}:{item.get('function', '?')} "
                f"— ${item.get('cost_usd', 0):,.0f} "
                f"({item.get('category', '?')}, {item.get('severity', '?')})"
            )
        return "\n".join(lines)

    async def _generate_summary(self, context: str) -> str:
        """Generate 3-sentence executive summary."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a senior engineering consultant 
             writing for a CTO or VP Engineering. 
             Be direct, specific, and use real numbers.
             Never use filler phrases like 'it is worth noting'.
             Write in present tense."""),
            ("human", """Based on this technical debt analysis, 
             write a 3-sentence executive summary that:
             1. States the total cost and what's driving it
             2. Identifies the single biggest risk
             3. States the most important action to take
             
             Use specific dollar amounts and timeframes.
             
             Analysis data:
             {context}"""),
        ])

        chain = prompt | self.llm
        result = await chain.ainvoke({"context": context})
        if isinstance(result, str):
            return result
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, str):
                return content
        return str(result)

    async def _generate_priorities(
        self, context: str, analysis: dict
    ) -> list:
        """Generate top 3 prioritized actions with costs."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a senior engineering consultant.
             Output valid JSON only. No markdown, no explanation."""),
            ("human", """Based on this analysis, return a JSON array 
             of exactly 3 priority actions.
             
             Each action must have:
             - rank: 1, 2, or 3
             - title: short action title (max 8 words)
             - file_or_module: specific file or module to fix
             - why: one sentence explaining the business reason
             - estimated_hours: realistic hours to fix
             - estimated_cost: cost to fix (hours × engineer rate)
             - saves_per_month: estimated monthly savings after fix
             - sprint: which sprint to do this in (Sprint 1, 2, or 3)
             
             Return ONLY a JSON array. Example:
             [
               {{
                 "rank": 1,
                 "title": "Refactor authentication module",
                 "file_or_module": "auth/login.py",
                 "why": "Changed 23 times last sprint, causing 40% of bug fixes",
                 "estimated_hours": 37,
                 "estimated_cost": 3219,
                 "saves_per_month": 1400,
                 "sprint": "Sprint 1"
               }}
             ]
             
             Analysis data:
             {context}"""),
        ])

        chain = prompt | self.llm | JsonOutputParser()
        try:
            result = await chain.ainvoke({"context": context})
            return result if isinstance(result, list) else []
        except Exception as e:
            return [{"error": f"Priority generation failed: {str(e)}"}]

    async def _generate_roi(self, context: str, analysis: dict) -> dict:
        """Generate ROI analysis for fixing the debt."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a senior engineering consultant.
             Output valid JSON only. No markdown."""),
            ("human", """Based on this analysis, return a JSON object
             with ROI analysis for fixing this technical debt.
             
             Include:
             - total_fix_cost: cost to fix all debt (from analysis)
             - annual_maintenance_savings: estimated annual savings
               (industry avg: 20-40% of debt cost saved per year)
             - payback_months: months to break even
             - 3_year_roi_pct: 3-year ROI percentage
             - recommended_budget: quarterly budget to allocate
             - recommendation: one sentence action recommendation
             
             Analysis data:
             {context}"""),
        ])

        chain = prompt | self.llm | JsonOutputParser()
        try:
            result = await chain.ainvoke({"context": context})
            return result if isinstance(result, dict) else {}
        except Exception as e:
            return {"error": f"ROI generation failed: {str(e)}"}
