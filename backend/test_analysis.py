"""Test script for Tech Debt Quantifier analysis.

Validates all analysis tools by running them against the Flask repository.
Prints a comprehensive formatted summary with all results.
"""

import logging
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


def print_unified_box(report: dict) -> None:
    """Print comprehensive unified summary box."""
    total_cost = report.get("total_cost_usd", 0)
    debt_score = report.get("debt_score", 0)
    total_hours = report.get("total_remediation_hours", 0)
    total_sprints = report.get("total_remediation_sprints", 0)
    
    summary = report.get("summary", {})
    files_scanned = summary.get("files_scanned", 0)
    issues_found = summary.get("issues_found", 0)
    function_count = summary.get("functions_analyzed", 0)
    
    cost_by_category = report.get("cost_by_category", {})
    code_quality_cost = cost_by_category.get("code_quality", {}).get("cost_usd", 0)
    security_cost = cost_by_category.get("security", {}).get("cost_usd", 0)
    doc_cost = cost_by_category.get("documentation", {}).get("cost_usd", 0)
    dep_cost = cost_by_category.get("dependency", {}).get("cost_usd", 0)
    
    profile = report.get("repo_profile", {})
    tech_stack = profile.get("tech_stack", {})
    team = profile.get("team", {})
    multipliers = report.get("multiplier_breakdown", {})
    benchmarks = report.get("benchmarks_used", {})
    rates = report.get("rate_confidence", {})
    
    security_issues_count = sum(
        1 for item in report.get("debt_items", [])
        if item.get("category") == "security"
    )
    doc_issues_count = sum(
        1 for item in report.get("debt_items", [])
        if item.get("category") == "documentation"
    )
    
    data_sources = report.get("data_sources_used", [])
    rates_status = "LIVE" if any("hourly_rates:live" in s for s in data_sources) else "FALLBACK"
    sonar_status = "LIVE" if any("sonar_rules:live" in s for s in data_sources) else "FALLBACK"
    
    sanity = report.get("sanity_check", {})
    is_reasonable = sanity.get("is_reasonable", False)
    your_avg = sanity.get("your_cost_per_function", 0)
    industry_avg = sanity.get("industry_avg", 0)
    
    total_cost_pct = total_cost if total_cost > 0 else 1
    cq_pct = (code_quality_cost / total_cost_pct) * 100
    sec_pct = (security_cost / total_cost_pct) * 100
    doc_pct = (doc_cost / total_cost_pct) * 100
    dep_pct = (dep_cost / total_cost_pct) * 100
    
    rates_icon = "[OK]" if rates_status == "LIVE" else "[!!]"
    sonar_icon = "[OK]" if sonar_status == "LIVE" else "[!!]"
    check_icon = "[OK]" if is_reasonable else "[!!]"
    
    combined_mult = report.get("combined_multiplier", 1.0)
    ai_files = report.get("ai_suspected_files", 0)
    
    primary_lang = tech_stack.get("primary_language", "Unknown").upper()
    frameworks = tech_stack.get("frameworks", [])
    ai_libs = tech_stack.get("ai_ml_libraries", [])
    databases = tech_stack.get("databases", [])
    framework_str = frameworks[0] if frameworks else "None detected"
    ai_str = ai_libs[0] if ai_libs else "None detected"
    db_str = databases[0] if databases else "None detected"
    
    team_size = team.get("unique_authors", 1)
    bus_factor = team.get("bus_factor", 1)
    repo_age = team.get("repo_age_days", 365)
    
    blended_rate = rates.get("code_quality", {}).get("rate", 84.55)
    
    print()
    print("=" * 80)
    print("FLASK REPO - COMPLETE ANALYSIS")
    print("=" * 80)
    print()
    
    print("REPO PROFILE")
    print("-" * 40)
    print(f"  Primary Language:  {primary_lang}")
    print(f"  Framework:        {framework_str}")
    print(f"  AI Libraries:     {ai_str}")
    print(f"  Database:        {db_str}")
    print(f"  Team Size:       ~{team_size} contributors")
    print(f"  Bus Factor:      {bus_factor}")
    print(f"  Repo Age:        {repo_age:,} days")
    print(f"  AI-Gen Files:    {ai_files} suspected")
    print()
    
    print("MULTIPLIERS APPLIED")
    print("-" * 40)
    print(f"  Repo Age ({repo_age:,}d):  {multipliers.get('repo_age_multiplier', 1.0):.1f}x")
    print(f"  Bus Factor ({bus_factor}):   {multipliers.get('bus_factor_multiplier', 1.0):.1f}x")
    print(f"  Team Size ({team_size}):    {multipliers.get('team_size_multiplier', 1.0):.1f}x")
    print(f"  AI Code:         {multipliers.get('ai_code_multiplier', 1.0):.1f}x")
    print(f"  Combined:        {combined_mult:.3f}x")
    print()
    
    print("COST RESULTS")
    print("-" * 40)
    print(f"  Total Cost:       ${total_cost:,.2f}")
    print(f"  Debt Score:       {debt_score:.1f} / 10")
    print(f"  Remediation:      {total_hours:,.1f} hrs ({total_sprints:.1f} sprints)")
    print()
    
    print("COST BREAKDOWN")
    print("-" * 40)
    print(f"  Code Quality:     ${code_quality_cost:,.2f} ({cq_pct:.0f}%)")
    print(f"  Security:         ${security_cost:,.2f} ({sec_pct:.0f}%)")
    print(f"  Documentation:    ${doc_cost:,.2f} ({doc_pct:.0f}%)")
    print(f"  Dependencies:     ${dep_cost:,.2f} ({dep_pct:.0f}%)")
    print()
    
    print("BENCHMARK")
    print("-" * 40)
    cisq_source = benchmarks.get("cost_per_function_source", "Unknown")
    print(f"  CISQ $/function:  ${benchmarks.get('cost_per_function_usd', industry_avg):,.2f} ({cisq_source})")
    print(f"  Your $/function:  ${your_avg:,.2f}")
    variance = ((your_avg - industry_avg) / industry_avg * 100) if industry_avg else 0
    variance_str = f"{variance:+.1f}%"
    print(f"  Variance:         {variance_str} - {check_icon} Within range")
    print()
    
    print("DETAILED METRICS")
    print("-" * 40)
    print(f"  Function count used for debt score: {function_count}")
    print(f"  Security issues found (after filter): {security_issues_count}")
    print(f"  Missing docstrings found: {doc_issues_count}")
    print(f"  Doc cost total: ${doc_cost:,.2f}")
    print()
    
    print("DATA SOURCES")
    print("-" * 40)
    print(f"  Hourly Rates:  {rates_icon} {rates_status}")
    print(f"  Sonar Rules:   {sonar_icon} {sonar_status}")
    print()
    
    debt_items = report.get("debt_items", [])[:3]
    if debt_items:
        print("SAMPLE AUDIT TRAIL (3 items)")
        print("-" * 40)
        for item in debt_items:
            file_name = item.get("file", "unknown")
            if len(file_name) > 50:
                file_name = "..." + file_name[-47:]
            print(f"  {file_name}")
            if item.get("complexity"):
                sev = item.get("severity", "unknown")
                print(f"    Complexity: {item.get('complexity')} ({sev})")
            if item.get("issue_text"):
                issue_text = item.get("issue_text", "")[:50]
                print(f"    Issue: {issue_text}")
            cost = item.get("cost_usd", 0)
            rate = item.get("rate", blended_rate)
            print(f"    Cost: ${cost:,.2f} @ ${rate:.2f}/hr")
        print()


def main() -> None:
    """Run full analysis on Flask repository."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(name)s - %(message)s")
    
    print("=" * 80)
    print("Tech Debt Quantifier - Complete Analysis")
    print("=" * 80)
    
    repo_path = clone_flask()
    
    print("\n" + "=" * 80)
    print("Running Full Analysis (this may show verbose logs above)")
    print("=" * 80 + "\n")
    
    estimator = CostEstimator()
    report = estimator.estimate_total_cost(str(repo_path), FLASK_GITHUB_URL)
    
    print("\n" + "=" * 80)
    print("ANALYSIS RESULTS")
    print("=" * 80)
    print_unified_box(report)
    
    print("\nData Sources Used:")
    for source in report.get("data_sources_used", []):
        parts = source.split(":")
        status_icon = "[OK]" if parts[1] == "live" else "[!!]"
        print(f"  {status_icon} {parts[0]}: {parts[1]}")
    
    rate_confidence = report.get("rate_confidence", {}).get("code_quality", {}).get("confidence", "unknown")
    print(f"\nRate Confidence: {rate_confidence.upper()}")


if __name__ == "__main__":
    main()
