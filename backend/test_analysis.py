"""Test script for Tech Debt Quantifier analysis.

Validates all analysis tools by running them against the Flask repository.
Prints a formatted summary box with all results.
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tools.cost_estimator import CostEstimator
from tools.git_mining import GitMiner
from tools.static_analysis import StaticAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

REPOS_DIR = Path("/tmp/repos")
FLASK_REPO_ID = "flask-test"
FLASK_GITHUB_URL = "https://github.com/pallets/flask"


def clone_flask() -> Path:
    """Clone Flask repository if not already present."""
    repo_path = REPOS_DIR / FLASK_REPO_ID
    
    if repo_path.exists():
        logger.info(f"Flask repo already exists at {repo_path}")
        return repo_path
    
    logger.info(f"Cloning Flask repository to {repo_path}")
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        subprocess.run(
            ["git", "clone", "--depth", "50", FLASK_GITHUB_URL, str(repo_path)],
            check=True,
            capture_output=True,
        )
        logger.info("Flask repository cloned successfully")
        return repo_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone Flask: {e}")
        raise


def print_summary_box(report: dict) -> None:
    """Print formatted summary box with analysis results."""
    total_cost = report.get("total_cost_usd", 0)
    debt_score = report.get("debt_score", 0)
    total_hours = report.get("total_remediation_hours", 0)
    total_sprints = report.get("total_remediation_sprints", 0)
    
    summary = report.get("summary", {})
    files_scanned = summary.get("files_scanned", 0)
    issues_found = summary.get("issues_found", 0)
    
    cost_by_category = report.get("cost_by_category", {})
    code_quality_cost = cost_by_category.get("code_quality", {}).get("cost_usd", 0)
    security_cost = cost_by_category.get("security", {}).get("cost_usd", 0)
    doc_cost = cost_by_category.get("documentation", {}).get("cost_usd", 0)
    dep_cost = cost_by_category.get("dependency", {}).get("cost_usd", 0)
    
    data_sources = report.get("data_sources_used", [])
    rates_status = "LIVE" if any("hourly_rates:live" in s for s in data_sources) else "FALLBACK"
    sonar_status = "LIVE" if any("sonar_rules:live" in s for s in data_sources) else "FALLBACK"
    vuln_status = "LIVE" if any("vulnerability:live" in s for s in data_sources) else "FALLBACK"
    
    sanity = report.get("sanity_check", {})
    is_reasonable = sanity.get("is_reasonable", False)
    your_avg = sanity.get("your_cost_per_function", 0)
    industry_avg = sanity.get("industry_avg", 1083)
    
    total_cost_pct = total_cost if total_cost > 0 else 1
    cq_pct = (code_quality_cost / total_cost_pct) * 100
    sec_pct = (security_cost / total_cost_pct) * 100
    doc_pct = (doc_cost / total_cost_pct) * 100
    dep_pct = (dep_cost / total_cost_pct) * 100
    
    rates_icon = "[OK]" if rates_status == "LIVE" else "[!!]"
    sonar_icon = "[OK]" if sonar_status == "LIVE" else "[!!]"
    vuln_icon = "[OK]" if vuln_status == "LIVE" else "[!!]"
    check_icon = "[OK]" if is_reasonable else "[!!]"
    
    print()
    print("+==================================================+")
    print("|         FLASK REPO - DEBT ANALYSIS              |")
    print("+==================================================+")
    print(f"|  Total Cost:        ${total_cost:>12,.2f}           |")
    print(f"|  Debt Score:        {debt_score:>5.1f} / 10                |")
    print(f"|  Remediation Time:  {total_hours:>6.1f} hours ({total_sprints:.1f} sprints)    |")
    print(f"|  Files Scanned:     {files_scanned:>6}                    |")
    print(f"|  Issues Found:      {issues_found:>6}                    |")
    print("+==================================================+")
    print("|  Cost Breakdown:                               |")
    print(f"|    Code Quality:    ${code_quality_cost:>10,.2f} ({cq_pct:4.0f}%)          |")
    print(f"|    Security:        ${security_cost:>10,.2f} ({sec_pct:4.0f}%)          |")
    print(f"|    Documentation:   ${doc_cost:>10,.2f} ({doc_pct:4.0f}%)          |")
    print(f"|    Dependencies:    ${dep_cost:>10,.2f} ({dep_pct:4.0f}%)          |")
    print("+==================================================+")
    print("|  Data Sources:                               |")
    print(f"|    Hourly Rates:    {rates_icon} {rates_status:<8}                  |")
    print(f"|    Sonar Rules:     {sonar_icon} {sonar_status:<8}                  |")
    print(f"|    Vuln Data:       {vuln_icon} {vuln_status:<8}                  |")
    print("+==================================================+")
    print(f"|  Sanity Check:      {check_icon} Within industry range     |")
    print(f"|  Industry avg/fn:   ${industry_avg:>8,.2f} (CISQ 2022)       |")
    print(f"|  Your avg/fn:       ${your_avg:>8,.2f}              |")
    print("+==================================================+")
    print()


def main() -> None:
    """Run full analysis on Flask repository."""
    import logging
    logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
    
    print("=" * 60)
    print("Tech Debt Quantifier - Test Analysis")
    print("=" * 60)
    
    repo_path = clone_flask()
    
    print("\n" + "=" * 60)
    print("DEBUG INFO - Step by Step Analysis")
    print("=" * 60)
    
    print("\n--- Step 1: Static Analysis (Complexity) ---")
    analyzer = StaticAnalyzer()
    summary = analyzer.get_summary(str(repo_path))
    
    total_funcs = summary.get("total_functions", 0)
    print(f"  Total functions found: {total_funcs}")
    print(f"  Files scanned: {summary.get('total_files_scanned', 0)}")
    
    print(f"\n  Top 5 Complex Functions:")
    all_funcs = summary.get("all_functions", [])
    sorted_funcs = sorted(all_funcs, key=lambda x: x["complexity"], reverse=True)
    for func in sorted_funcs[:5]:
        print(f"    {func['full_name']} - complexity {func['complexity']} ({func['severity']})")
    
    print(f"\n  Complexity Distribution:")
    dist = summary.get("complexity_distribution", {})
    for sev, count in dist.items():
        print(f"    {sev}: {count}")
    
    print("\n--- Step 2: Git Hotspot Analysis ---")
    miner = GitMiner()
    hotspots = miner.get_hotspots(str(repo_path))
    
    print(f"  Hotspot files found: {len(hotspots)}")
    print(f"\n  Top 5 Hotspot Files:")
    for hotspot in hotspots[:5]:
        print(f"    {hotspot['file']} - {hotspot['change_count']} commits")
    
    print("\n--- Step 3: Cost Estimation ---")
    print("  Running full cost estimation (this may show debug logs above)...")
    estimator = CostEstimator()
    report = estimator.estimate_total_cost(str(repo_path))
    
    print("\n" + "=" * 60)
    print("ANALYSIS RESULTS")
    print("=" * 60)
    print_summary_box(report)
    
    print("\nData Sources Used:")
    for source in report.get("data_sources_used", []):
        parts = source.split(":")
        status_icon = "[OK]" if parts[1] == "live" else "[!!]"
        print(f"  {status_icon} {parts[0]}: {parts[1]}")
    
    print("\nAdditional Info:")
    print(f"  Function count used for debt score: {report['summary']['functions_analyzed']}")
    print(f"  Avg complexity: {report['summary']['avg_complexity']}")


if __name__ == "__main__":
    main()
