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

        # Post-process: fix garbled paths, generate readable titles, compute ROI fallback
        priorities = self._sanitize_priorities(priorities, analysis)
        roi = self._sanitize_roi(roi, analysis)

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

    def _mathematical_priorities(self, analysis: dict) -> list:
        """Generate priorities from actual data without LLM, filtering aggregates."""
        import os
        import re

        all_items = analysis.get("debt_items", [])
        total_cost = analysis.get("total_cost_usd", 1)

        def is_valid_item(item):
            file_path = item.get('file', '')
            adjusted_minutes = item.get('adjusted_minutes', 0) or 0
            hours = adjusted_minutes / 60
            cost = item.get('cost_usd', 0) or 0

            # Reject aggregate items (cost > 20% of total)
            if cost > (total_cost * 0.20):
                return False

            # Reject items with no real file path
            if not file_path or file_path in ['unknown', '', 'base_security']:
                return False

            # Reject items with unrealistic hours (>200hrs = aggregate)
            if hours > 200:
                return False

            return True

        valid_items = [i for i in all_items if is_valid_item(i)]

        # If no valid items after filtering, use top items but cap hours
        if not valid_items:
            valid_items = sorted(
                all_items, key=lambda x: x.get('cost_usd', 0), reverse=True
            )
            valid_items = [i for i in valid_items if
                          (i.get('adjusted_minutes', 0) or 0) / 60 < 200]

        # Sort by cost and take top 3
        top_items = sorted(
            valid_items,
            key=lambda x: x.get('cost_usd', 0),
            reverse=True
        )[:3]

        priorities = []
        sprint_names = ["Sprint 1", "Sprint 2", "Sprint 3"]

        for i, item in enumerate(top_items):
            adjusted_minutes = item.get('adjusted_minutes', 0) or 0
            hours = adjusted_minutes / 60
            cost = item.get('cost_usd', 0) or 0

            # Clean file path
            raw_file = item.get('file', '')
            clean_path = re.sub(r'^/tmp/repos/[^/]+/', '', str(raw_file))
            clean_path = re.sub(r':\?$|:\d+$', '', clean_path).strip()
            file_name = os.path.splitext(os.path.basename(clean_path))[0]

            category = (item.get('category') or 'code_quality').replace('_', ' ')
            severity = (item.get('severity') or 'high').capitalize()
            complexity = item.get('complexity', 0) or 0
            churn = item.get('churn_multiplier', 1.0) or 1.0

            # Readable title
            if file_name and file_name not in ['unknown', '']:
                if category == 'security':
                    title = f"Fix security issues in {file_name}"
                elif int(complexity) > 10:
                    title = f"Refactor complex {file_name} module"
                elif churn > 1.5:
                    title = f"Stabilize high-churn {file_name}"
                else:
                    title = f"Fix {severity.lower()} {category} in {file_name}"
            else:
                title = f"Fix {severity.lower()} {category} issue"

            # Meaningful why sentence
            why_parts = []
            if churn > 1.5:
                why_parts.append(f"changes frequently ({churn:.1f}x churn)")
            if int(complexity) > 10:
                why_parts.append(f"high complexity ({complexity})")
            if category == 'security':
                why_parts.append("security vulnerability increases breach risk")
            why_parts.append(f"costs ${cost:,.0f} to remediate")
            why = f"This file {', '.join(why_parts)}."

            # Monthly savings: assume fixing removes 15% of ongoing maintenance
            saves_per_month = round((cost * 0.15) / 12, 2)

            priorities.append({
                "rank": i + 1,
                "title": title,
                "file_or_module": clean_path or file_name or 'unknown',
                "why": why,
                "estimated_hours": round(hours, 1),
                "estimated_cost": round(cost, 2),
                "saves_per_month": saves_per_month,
                "sprint": sprint_names[i],
                "source": "mathematical_fallback"
            })

        return priorities

    def _sanitize_priorities(self, priorities: list, analysis: dict) -> list:
        """Fix garbled LLM output: clean file paths, generate readable titles."""
        import re

        if not priorities or not isinstance(priorities, list):
            return self._mathematical_priorities(analysis)

        # Build lookup from actual debt items for clean file paths and metadata
        debt_items = analysis.get("debt_items", [])
        # Group by file basename for lookup
        items_by_basename: dict[str, list[dict]] = {}
        for item in debt_items:
            basename = item.get("file", "").split("/")[-1].split("\\")[-1]
            if basename:
                items_by_basename.setdefault(basename, []).append(item)

        # Collect top items per category for title generation
        category_top: dict[str, list[dict]] = {}
        for item in debt_items:
            cat = item.get("category", "code_quality")
            category_top.setdefault(cat, []).append(item)
        for cat in category_top:
            category_top[cat].sort(key=lambda x: x.get("cost_usd", 0), reverse=True)

        # Category display names
        cat_names = {
            "code_quality": "Code Quality",
            "security": "Security",
            "documentation": "Documentation",
            "dependency": "Dependencies",
            "test_debt": "Test Coverage",
        }

        sanitized = []
        for action in priorities:
            if not isinstance(action, dict) or "error" in action:
                return self._mathematical_priorities(analysis)

            file_or_module = action.get("file_or_module", "")
            title = action.get("title", "")

            # Detect garbled paths: contain emoji, unusual chars, or nonsensical segments
            is_garbled = bool(re.search(r'[🅰-🆑🌀-🗿🚀-🛿🤀-🧿]', file_or_module))
            is_garbled = is_garbled or bool(re.search(r'[🅰-🆑🌀-🗿🚀-🛿🤀-🧿]', title))

            # Try to find a clean file path from actual debt items
            clean_file = file_or_module
            matched_items = []

            # Extract any recognizable filename from the garbled text
            basename_match = re.findall(r'[\w]+\.(?:py|js|ts|java|go|rb|php|rs)', file_or_module)
            if basename_match:
                for bm in basename_match:
                    if bm in items_by_basename:
                        matched_items = items_by_basename[bm]
                        # Use the actual relative path from debt items
                        clean_file = matched_items[0].get("file", bm)
                        break

            # If still garbled or no file found, use top debt items by rank
            rank = action.get("rank", len(sanitized) + 1)
            if is_garbled or not matched_items:
                # Find the top item matching this rank's category
                sorted_items = sorted(debt_items, key=lambda x: x.get("cost_usd", 0), reverse=True)
                idx = min(rank - 1, len(sorted_items) - 1) if sorted_items else 0
                if sorted_items:
                    top_item = sorted_items[idx]
                    clean_file = top_item.get("file", file_or_module)
                    matched_items = [top_item]

            # Generate readable title from file/function context
            clean_title = title
            if is_garbled or re.search(r'[/\\]', title):
                clean_title = self._make_readable_title(clean_file, matched_items, rank)

            # Clean up file_or_module display
            display_file = clean_file.replace("\\", "/")
            # Strip long temp paths like /tmp/repos/xxx/...
            if "/tmp/repos/" in display_file:
                display_file = re.sub(r'^.*/repos/[^/]+/', '', display_file)

            action["file_or_module"] = display_file
            action["title"] = clean_title
            sanitized.append(action)

        return sanitized

    def _make_readable_title(self, file_path: str, items: list[dict], rank: int) -> str:
        """Generate a human-readable action title from file path and debt items."""
        basename = file_path.split("/")[-1].split("\\")[-1].replace(".py", "").replace(".js", "")
        # Convert snake_case to readable
        name = basename.replace("_", " ").replace("-", " ").title()

        if items:
            cat = items[0].get("category", "")
            severity = items[0].get("severity", "")
            func = items[0].get("function", "")

            if cat == "security":
                return f"Fix security vulnerabilities in {name}"
            elif cat == "documentation":
                return f"Add missing documentation to {name}"
            elif cat == "dependency":
                return f"Update vulnerable dependencies"
            elif func:
                func_readable = func.replace("_", " ").title()
                return f"Refactor {func_readable} in {name}"
            elif severity in ("critical", "high"):
                return f"Address critical complexity in {name}"
            else:
                return f"Reduce technical debt in {name}"
        return f"Refactor {name}"

    def _sanitize_roi(self, roi: dict, analysis: dict) -> dict:
        """Compute ROI from code if LLM returned zero/nonsense values."""
        if not roi or not isinstance(roi, dict) or "error" in roi:
            return self._compute_roi_fallback(analysis)

        # Check if LLM returned valid non-zero values
        savings = roi.get("annual_maintenance_savings", 0)
        roi_pct = roi.get("3_year_roi_pct", 0)
        fix_cost = roi.get("total_fix_cost", 0)

        # If all key values are zero or missing, use code-based fallback
        if (not savings or savings == 0) and (not roi_pct or roi_pct == 0):
            return self._compute_roi_fallback(analysis)

        # Fill in any missing fields from fallback
        fallback = self._compute_roi_fallback(analysis)
        for key in ["total_fix_cost", "annual_maintenance_savings", "payback_months",
                     "3_year_roi_pct", "recommended_budget", "recommendation"]:
            if not roi.get(key):
                roi[key] = fallback.get(key)

        return roi

    def _compute_roi_fallback(self, analysis: dict) -> dict:
        """Compute ROI from actual analysis data."""
        total_cost = analysis.get("total_cost_usd", 0)
        total_hours = analysis.get("total_remediation_hours", 0)
        hourly_rate = 85  # Default engineer rate

        fix_cost = total_cost
        # Industry estimate: maintenance overhead is ~40% of debt cost annually
        annual_savings = round(total_cost * 0.40, 2)
        payback_months = round((fix_cost / annual_savings) * 12) if annual_savings > 0 else 99
        three_yr_return = round(((annual_savings * 3 - fix_cost) / fix_cost) * 100) if fix_cost > 0 else 0
        quarterly_budget = round(fix_cost / 4, 2)

        if three_yr_return > 100:
            rec = "Strong ROI — prioritize top 3 items this quarter for maximum impact."
        elif three_yr_return > 0:
            rec = "Positive ROI — recommend phased remediation over 2-3 quarters."
        else:
            rec = "Low ROI — focus on highest-severity items only to contain costs."

        return {
            "total_fix_cost": round(fix_cost),
            "annual_maintenance_savings": round(annual_savings),
            "payback_months": payback_months,
            "3_year_roi_pct": three_yr_return,
            "recommended_budget": round(quarterly_budget),
            "recommendation": rec,
        }

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
