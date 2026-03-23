"""Debug script for JSON extraction."""

import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

from agents.llm_factory import get_llm
from agents.reporter import ReporterAgent


async def test_json_extraction():
    llm = get_llm()
    reporter = ReporterAgent()

    context = """Repository: test
Primary Language: Python
Total Technical Debt Cost: $100,000"""

    prompt_text = """You are a JSON API. Return ONLY a JSON array with 3 items.
No markdown. No explanation. Just the raw JSON array.

Each item needs: rank, title, file_or_module, why, estimated_hours, estimated_cost, saves_per_month, sprint

Example: [{"rank": 1, "title": "Fix auth", "file_or_module": "auth.py", "why": "High bug rate", "estimated_hours": 37, "estimated_cost": 3219, "saves_per_month": 1400, "sprint": "Sprint 1"}]

Technical debt data:
""" + context

    print("=== CALLING LLM ===")
    raw_result = llm._call(prompt_text)
    print("RAW OUTPUT:")
    print(repr(raw_result))
    print()

    print("=== EXTRACTING JSON ===")
    extracted = reporter._extract_json(raw_result)
    print("EXTRACTED:")
    print(repr(extracted))
    print()

    print("=== PARSING ===")
    try:
        parsed = json.loads(extracted)
        print("SUCCESS:")
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError as e:
        print(f"PARSE ERROR: {e}")
        print(f"Position: {e.pos}, Line: {e.lineno}, Col: {e.colno}")


if __name__ == "__main__":
    asyncio.run(test_json_extraction())