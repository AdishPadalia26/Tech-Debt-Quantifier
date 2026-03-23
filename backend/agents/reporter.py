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
        import logging
        logger = logging.getLogger(__name__)
        
        prompt_text = """You are a JSON API. Return ONLY a JSON array with 3 items.
No markdown. No explanation. Just the raw JSON array.

IMPORTANT: Use plain numbers only, NO expressions like "x / y" or "x - y".
For example: use "242" not "24220 / 100".

Each item needs: rank (integer), title (string), file_or_module (string), why (string), estimated_hours (number), estimated_cost (number), saves_per_month (number), sprint (string)

Example: [{"rank": 1, "title": "Fix auth", "file_or_module": "auth.py", "why": "High bug rate", "estimated_hours": 37, "estimated_cost": 3219, "saves_per_month": 1400, "sprint": "Sprint 1"}]

Technical debt data:
""" + context

        try:
            result = self.llm._call(prompt_text)
            logger.debug(f"[PRIORITIES] Raw LLM result: {repr(result)[:500]}")
            json_str = self._extract_json(result)
            logger.debug(f"[PRIORITIES] Extracted JSON: {repr(json_str)[:500]}")
            import json
            parsed = json.loads(json_str)
            logger.debug(f"[PRIORITIES] Parsed result: {parsed}")
            return parsed if isinstance(parsed, list) else []
        except Exception as e:
            logger.error(f"[PRIORITIES] Error: {e}")
            return [{"error": f"Priority generation failed: {str(e)}"}]

    def _extract_json(self, text: str) -> str:
        """Extract JSON from text that may have markdown wrapping or escaped characters."""
        import re
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        text = text.strip()
        text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'```$', '', text, flags=re.MULTILINE)
        text = text.strip()
        
        # Fix Windows backslashes in file paths (e.g., \tmp\repos -> /tmp/repos)
        text = re.sub(r'\\([^"\\/bfnrtu])', r'/\1', text)
        
        start = text.find('[')
        if start != -1:
            bracket_count = 0
            end = start
            in_string = False
            escape_next = False
            for i, c in enumerate(text[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\' and in_string:
                    escape_next = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if c == '[':
                        bracket_count += 1
                    elif c == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end = i + 1
                            break
            result = text[start:end]
            try:
                json.loads(result)
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"[EXTRACT] First parse failed: {e}")
            try:
                result = result.replace('\\"', '"')
                result = result.replace('\\\\', '\\')
                json.loads(result)
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"[EXTRACT] Second parse failed: {e}")
        
        start = text.find('{')
        if start != -1:
            brace_count = 0
            end = start
            in_string = False
            escape_next = False
            for i, c in enumerate(text[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\' and in_string:
                    escape_next = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if c == '{':
                        brace_count += 1
                    elif c == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break
            result = text[start:end]
            try:
                json.loads(result)
                return f"[{result}]"
            except json.JSONDecodeError:
                pass
        
        return text

    async def _generate_roi(self, context: str, analysis: dict) -> dict:
        """Generate ROI analysis for fixing the debt."""
        prompt_text = """You are a JSON API. Return ONLY a JSON object with these fields:
total_fix_cost, annual_maintenance_savings, payback_months, 3_year_roi_pct, recommended_budget, recommendation

Example: {"total_fix_cost": 131546, "annual_maintenance_savings": 52619, "payback_months": 24, "3_year_roi_pct": 180, "recommended_budget": 10962, "recommendation": "Allocate budget"}

Technical debt data:
""" + context

        try:
            result = self.llm._call(prompt_text)
            json_str = self._extract_json(result)
            import json
            parsed = json.loads(json_str)
            if isinstance(parsed, list) and len(parsed) == 1:
                parsed = parsed[0]
            return parsed if isinstance(parsed, dict) else {}
        except Exception as e:
            return {"error": f"ROI generation failed: {str(e)}"}
