"""Cost estimator for technical debt quantification.

Produces comprehensive dollar-based cost estimates for technical debt.
Combines complexity, security, documentation, and dependency analysis.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from constants import (
    CISQ_COST_PER_FUNCTION,
    DEBT_TYPE_TO_ROLE,
    DEBT_SCORE_MAX,
    FUNCTION_BASELINE_MINUTES,
    HOURS_PER_SPRINT,
    MAINTENANCE_OVERHEAD_MULTIPLIER,
    SANITY_CHECK_VARIANCE_THRESHOLD,
)

logger = logging.getLogger(__name__)


class CostEstimator:
    """Estimates technical debt costs in dollar and time terms.
    
    Runs all analysis tools and combines results into a comprehensive
    cost report with audit trail and sanity checks.
    """

    def __init__(self) -> None:
        self._data_sources: list[str] = []

    def _track_data_source(self, source_name: str, used_fallback: bool) -> None:
        """Track which data sources were used and whether fallbacks were needed."""
        status = "fallback" if used_fallback else "live"
        key = f"{source_name}:{status}"
        if key not in self._data_sources:
            self._data_sources.append(key)

    def _get_role_for_category(self, category: str) -> str:
        """Get engineer role required for a debt category.
        
        Args:
            category: Debt category (code_quality, security, documentation, etc.)
            
        Returns:
            Role: junior, mid, or senior
        """
        return DEBT_TYPE_TO_ROLE.get(category, "mid")

    def calculate_debt_score(
        self, total_cost: float, function_count: int
    ) -> float:
        """Calculate normalized debt score (0-10).
        
        Formula: min(10, (total_cost / (function_count * CISQ_COST_PER_FUNCTION)) * 10)
        Source: normalized against CISQ 2022 industry average of $1,083/function
        
        Args:
            total_cost: Total estimated cost in USD
            function_count: Number of functions analyzed
            
        Returns:
            Debt score from 0 to 10
        """
        logger.info(f"[DEBT SCORE DEBUG] total_cost={total_cost}, function_count={function_count}")
        
        if function_count == 0:
            logger.warning("[DEBT SCORE] function_count is 0, returning 0.0")
            return 0.0

        cost_per_function = total_cost / function_count
        raw_score = (cost_per_function / CISQ_COST_PER_FUNCTION) * 10
        debt_score = min(DEBT_SCORE_MAX, raw_score)
        
        logger.info(f"[DEBT SCORE] cost_per_function=${cost_per_function:.2f}, raw_score={raw_score:.2f}, final={round(debt_score, 2)}")

        return round(debt_score, 2)

    def sanity_check(
        self, total_cost: float, function_count: int
    ) -> dict[str, Any]:
        """Perform sanity check on cost estimates.
        
        Compares cost per function against industry average from CISQ 2022.
        
        Args:
            total_cost: Total estimated cost
            function_count: Number of functions
            
        Returns:
            Sanity check results with assessment
        """
        cost_per_function = total_cost / max(function_count, 1)
        variance_pct = abs(cost_per_function - CISQ_COST_PER_FUNCTION) / CISQ_COST_PER_FUNCTION * 100

        is_reasonable = variance_pct < SANITY_CHECK_VARIANCE_THRESHOLD

        if cost_per_function < CISQ_COST_PER_FUNCTION * 0.5:
            assessment = "Lower than industry average - code may be well-maintained"
        elif cost_per_function < CISQ_COST_PER_FUNCTION:
            assessment = "Slightly below industry average - reasonable condition"
        elif cost_per_function < CISQ_COST_PER_FUNCTION * 1.5:
            assessment = "Slightly above industry average - some technical debt present"
        elif cost_per_function < CISQ_COST_PER_FUNCTION * 2:
            assessment = "Above industry average - significant technical debt"
        else:
            assessment = "Significantly above industry average - high technical debt"

        return {
            "your_cost_per_function": round(cost_per_function, 2),
            "industry_avg": CISQ_COST_PER_FUNCTION,
            "variance_pct": round(variance_pct, 2),
            "is_reasonable": is_reasonable,
            "assessment": assessment,
        }

    def _calculate_baseline_cost(self, function_count: int) -> float:
        """Calculate baseline tech debt cost for all functions.
        
        Every function has some baseline technical debt due to:
        - Code that could be cleaner
        - Minor inefficiencies
        - Technical decisions that weren't documented
        
        Args:
            function_count: Number of functions analyzed
            
        Returns:
            Baseline cost in USD
        """
        from data.rate_fetcher import RateFetcher
        
        rate_fetcher = RateFetcher()
        baseline_rate = rate_fetcher.get_rate("mid")
        baseline_minutes = FUNCTION_BASELINE_MINUTES
        baseline_cost = (baseline_minutes / 60) * baseline_rate * function_count
        
        return baseline_cost

    def _categorize_costs(self, debt_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Categorize costs by debt type.
        
        Args:
            debt_items: List of all debt items
            
        Returns:
            Costs grouped by category
        """
        categories = {
            "code_quality": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
            "security": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
            "documentation": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
            "dependency": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
        }

        for item in debt_items:
            category = item.get("category", "code_quality")
            if category not in categories:
                categories[category] = {"cost_usd": 0.0, "hours": 0.0, "item_count": 0}

            categories[category]["cost_usd"] += item.get("cost_usd", 0)
            categories[category]["hours"] += item.get("remediation_hours", 0)
            categories[category]["item_count"] += 1

        for cat in categories:
            categories[cat]["cost_usd"] = round(categories[cat]["cost_usd"], 2)
            categories[cat]["hours"] = round(categories[cat]["hours"], 2)

        return categories

    def estimate_total_cost(self, repo_path: str) -> dict[str, Any]:
        """Estimate total technical debt cost for a repository.
        
        Runs all analysis tools and produces comprehensive cost report.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Complete cost estimate with breakdown and audit trail
        """
        self._data_sources = []
        debt_items = []

        from data.rate_fetcher import RateFetcher
        from data.sonarqube_rules import SonarQubeRules
        from data.vulnerability_fetcher import VulnerabilityFetcher
        from tools.git_mining import GitMiner
        from tools.static_analysis import StaticAnalyzer

        rate_fetcher = RateFetcher()
        sonar_rules = SonarQubeRules()

        rates_data = rate_fetcher.fetch_bls_rates()
        self._track_data_source("hourly_rates", rates_data.get("used_fallback", True))
        logger.info(f"[COST EST] Hourly rates - Senior: ${rates_data.get('junior', 0)}/junior, ${rates_data.get('mid', 0)}/mid, ${rates_data.get('senior', 0)}/senior")

        sonar_data = sonar_rules.fetch_rules()
        self._track_data_source("sonar_rules", sonar_data.get("used_fallback", True))
        logger.info(f"[COST EST] Sonar rules loaded: {sonar_data.get('count', 0)} rules, source: {sonar_data.get('source', 'unknown')}")

        logger.info("[COST EST] Step 1: Running GitMiner for code quality...")
        risky_files = GitMiner().get_risky_files(repo_path)
        code_quality_cost = 0.0
        for rf in risky_files:
            debt_items.append({
                "file": rf["file"],
                "category": "code_quality",
                "severity": rf["severity"],
                "complexity": rf["max_complexity"],
                "remediation_hours": rf["adjusted_minutes"] / 60,
                "cost_usd": rf["cost_usd"],
                "change_count": rf["change_count"],
                "churn_multiplier": rf["churn_multiplier"],
                "type": "complexity_hotspot",
            })
            code_quality_cost += rf["cost_usd"]
        logger.info(f"[COST EST] Code quality: {len(risky_files)} files, ${code_quality_cost:.2f}")

        logger.info("[COST EST] Step 2: Running security scan...")
        static_analyzer = StaticAnalyzer()
        security_issues = static_analyzer.run_security_scan(repo_path)
        security_cost = 0.0
        for issue in security_issues:
            role = self._get_role_for_category("security")
            hourly_rate = rate_fetcher.get_rate(role)
            cost_usd = issue.get("remediation_hours", 0) * hourly_rate

            debt_items.append({
                "file": issue["file"],
                "category": "security",
                "severity": issue["severity"],
                "line": issue.get("line", 0),
                "issue_text": issue.get("issue_text", ""),
                "bandit_test_id": issue.get("bandit_test_id", ""),
                "remediation_hours": issue.get("remediation_hours", 0),
                "cost_usd": round(cost_usd, 2),
                "type": "security_hotspot",
            })
            security_cost += cost_usd
        logger.info(f"[COST EST] Security: {len(security_issues)} issues, ${security_cost:.2f}")

        logger.info("[COST EST] Step 3: Finding missing docstrings...")
        doc_issues = static_analyzer.find_missing_docstrings(repo_path)
        doc_cost = 0.0
        for doc in doc_issues:
            role = self._get_role_for_category("documentation")
            hourly_rate = rate_fetcher.get_rate(role)
            cost_usd = (doc.get("remediation_minutes", 10) / 60) * hourly_rate

            debt_items.append({
                "file": doc["file"],
                "category": "documentation",
                "severity": doc.get("severity", "low"),
                "function": doc.get("function", ""),
                "line": doc.get("line", 0),
                "remediation_minutes": doc.get("remediation_minutes", 10),
                "remediation_hours": doc.get("remediation_minutes", 10) / 60,
                "cost_usd": round(cost_usd, 2),
                "type": "missing_docstring",
            })
            doc_cost += cost_usd
        logger.info(f"[COST EST] Documentation: {len(doc_issues)} issues, ${doc_cost:.2f}")

        logger.info("[COST EST] Step 4: Checking dependencies for vulnerabilities...")
        vuln_fetcher = VulnerabilityFetcher()
        dep_vulns = vuln_fetcher.check_dependencies_sync(repo_path)
        for vuln in dep_vulns:
            debt_items.append({
                "file": "requirements.txt",
                "category": "dependency",
                "severity": vuln.get("severity", "UNKNOWN"),
                "package": vuln.get("package", ""),
                "installed_version": vuln.get("installed_version", ""),
                "cve_id": vuln.get("cve_id", ""),
                "cvss_score": vuln.get("cvss_score"),
                "remediation_hours": vuln.get("remediation_hours", 0),
                "cost_usd": vuln.get("cost_usd", 0),
                "fixed_version": vuln.get("fixed_version"),
                "type": "vulnerability",
            })
        dep_cost = sum(v.get("cost_usd", 0) for v in dep_vulns)
        logger.info(f"[COST EST] Dependencies: {len(dep_vulns)} vulnerabilities, ${dep_cost:.2f}")

        summary = static_analyzer.get_summary(repo_path)
        function_count = summary.get("total_functions", 0)

        baseline_cost = self._calculate_baseline_cost(function_count)
        logger.info(f"[COST EST] Baseline cost ({function_count} functions): ${baseline_cost:.2f}")

        total_cost = sum(item.get("cost_usd", 0) for item in debt_items)
        total_cost_with_baseline = total_cost + baseline_cost
        total_cost = total_cost_with_baseline * MAINTENANCE_OVERHEAD_MULTIPLIER
        logger.info(f"[COST EST] Total with baseline and multiplier: ${total_cost:.2f}")

        debt_score = self.calculate_debt_score(total_cost, function_count)
        sanity = self.sanity_check(total_cost, function_count)
        cost_by_category = self._categorize_costs(debt_items)
        baseline_hours = baseline_cost / rate_fetcher.get_rate("mid")
        cost_by_category["code_quality"]["cost_usd"] += baseline_cost * MAINTENANCE_OVERHEAD_MULTIPLIER
        cost_by_category["code_quality"]["hours"] += baseline_hours * MAINTENANCE_OVERHEAD_MULTIPLIER
        total_hours = sum(item.get("remediation_hours", 0) for item in debt_items)
        total_hours = total_hours + baseline_hours * MAINTENANCE_OVERHEAD_MULTIPLIER
        total_sprints = total_hours / HOURS_PER_SPRINT
        
        logger.info(f"[COST EST] ========== TOTALS ==========")
        logger.info(f"[COST EST] Total debt items: {len(debt_items)}")
        logger.info(f"[COST EST] Total cost: ${total_cost:.2f}")
        logger.info(f"[COST EST] Total hours: {total_hours:.2f}")
        logger.info(f"[COST EST] Function count: {function_count}")
        logger.info(f"[COST EST] Cost by category: {cost_by_category}")

        return {
            "repo_path": repo_path,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_sources_used": self._data_sources,
            "hourly_rates": rates_data,
            "total_cost_usd": round(total_cost, 2),
            "total_remediation_hours": round(total_hours, 2),
            "total_remediation_sprints": round(total_sprints, 2),
            "cost_by_category": cost_by_category,
            "debt_score": debt_score,
            "sanity_check": sanity,
            "debt_items": debt_items,
            "summary": {
                "files_scanned": summary.get("total_files_scanned", 0),
                "functions_analyzed": function_count,
                "issues_found": len(debt_items),
                "avg_complexity": summary.get("avg_complexity", 0),
            },
        }
