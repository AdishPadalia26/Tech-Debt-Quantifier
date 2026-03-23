"""Test script for full agent pipeline."""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from agents.orchestrator import TechDebtOrchestrator


async def main() -> None:
    print("Testing full agent pipeline...")
    print("=" * 60)

    orchestrator = TechDebtOrchestrator()

    print("Step 1: Crawling github.com/pallets/flask...")
    print("Step 2: Running analysis (uses cached data if available)...")
    print("Step 3: Generating executive report with LLM...")
    print()

    result = await orchestrator.run_analysis(
        github_url="https://github.com/pallets/flask",
        repo_id="flask-test",
    )

    report = orchestrator.format_report(result)
    print(report)

    print("\nPIPELINE STATUS CHECK:")
    print(f"  Clone:      {result.get('clone_status')}")
    print(f"  Analysis:   {'OK' if result.get('raw_analysis') else 'FAILED'}")
    print(f"  Summary:    {'OK' if result.get('executive_summary') else 'FAILED'}")
    print(f"  Priorities: {'OK' if result.get('priority_actions') else 'FAILED'}")
    print(f"  ROI:        {'OK' if result.get('roi_analysis') else 'FAILED'}")
    print(f"  Status:     {result.get('status')}")


if __name__ == "__main__":
    asyncio.run(main())
