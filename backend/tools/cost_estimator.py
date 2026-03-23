"""Cost estimator for technical debt quantification.

Produces comprehensive dollar-based cost estimates for technical debt.
Combines complexity, security, documentation, and dependency analysis.

Uses the intelligence layer for dynamic data:
- RepoProfiler for tech stack detection
- RateIntelligenceAgent for market rates
- BenchmarkAgent for industry benchmarks
- SecurityCostAgent for risk-weighted security costs
"""

import logging
from datetime import datetime
from typing import Any

from constants import (
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
    
    Uses the intelligence layer for dynamic data fetching.
    """

    def __init__(self) -> None:
        self._data_sources: list[str] = []

    def _track_data_source(self, source_name: str, used_fallback: bool) -> None:
        """Track which data sources were used and whether fallbacks were needed."""
        status = "fallback" if used_fallback else "live"
        key = f"{source_name}:{status}"
        if key not in self._data_sources:
            self._data_sources.append(key)

    def calculate_debt_score(
        self, total_cost: float, function_count: int, cisq_per_function: float
    ) -> float:
        """Calculate normalized debt score (0-10).
        
        Formula: min(10, (total_cost / (function_count * CISQ_COST_PER_FUNCTION)) * 10)
        
        Args:
            total_cost: Total estimated cost in USD
            function_count: Number of functions analyzed
            cisq_per_function: Industry benchmark cost per function
            
        Returns:
            Debt score from 0 to 10
        """
        logger.info(f"[DEBT SCORE DEBUG] total_cost={total_cost}, function_count={function_count}")
        
        if function_count == 0:
            logger.warning("[DEBT SCORE] function_count is 0, returning 0.0")
            return 0.0

        cost_per_function = total_cost / function_count
        raw_score = (cost_per_function / cisq_per_function) * 10
        debt_score = min(DEBT_SCORE_MAX, raw_score)
        
        logger.info(f"[DEBT SCORE] cost_per_function=${cost_per_function:.2f}, raw_score={raw_score:.2f}, final={round(debt_score, 2)}")

        return round(debt_score, 2)

    def sanity_check(
        self, total_cost: float, function_count: int, cisq_per_function: float
    ) -> dict[str, Any]:
        """Perform sanity check on cost estimates.
        
        Compares cost per function against industry average.
        
        Args:
            total_cost: Total estimated cost
            function_count: Number of functions
            cisq_per_function: Industry benchmark
            
        Returns:
            Sanity check results with assessment
        """
        cost_per_function = total_cost / max(function_count, 1)
        variance_pct = abs(cost_per_function - cisq_per_function) / cisq_per_function * 100

        is_reasonable = variance_pct < SANITY_CHECK_VARIANCE_THRESHOLD

        if cost_per_function < cisq_per_function * 0.5:
            assessment = "Lower than industry average - code may be well-maintained"
        elif cost_per_function < cisq_per_function:
            assessment = "Slightly below industry average - reasonable condition"
        elif cost_per_function < cisq_per_function * 1.5:
            assessment = "Slightly above industry average - some technical debt present"
        elif cost_per_function < cisq_per_function * 2:
            assessment = "Above industry average - significant technical debt"
        else:
            assessment = "Significantly above industry average - high technical debt"

        return {
            "your_cost_per_function": round(cost_per_function, 2),
            "industry_avg": cisq_per_function,
            "variance_pct": round(variance_pct, 2),
            "is_reasonable": is_reasonable,
            "assessment": assessment,
        }

    def _categorize_costs(self, debt_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Categorize costs by debt type."""
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

    def estimate_total_cost(self, repo_path: str, github_url: str = None) -> dict[str, Any]:
        """Estimate total technical debt cost for a repository.
        
        Uses the intelligence layer for dynamic data:
        - RepoProfiler for tech stack and multipliers
        - RateIntelligenceAgent for market rates
        - BenchmarkAgent for industry benchmarks
        - SecurityCostAgent for risk-weighted security costs
        
        Args:
            repo_path: Path to the repository
            github_url: Optional GitHub URL for additional context
            
        Returns:
            Complete cost estimate with breakdown and audit trail
        """
        from data.sonarqube_rules import SonarQubeRules
        from data.vulnerability_fetcher import VulnerabilityFetcher
        from intelligence.benchmark_agent import BenchmarkAgent
        from intelligence.repo_profiler import RepoProfiler
        from intelligence.rate_agent import RateIntelligenceAgent
        from intelligence.security_cost_agent import SecurityCostAgent
        from tools.git_mining import GitMiner
        from tools.static_analysis import StaticAnalyzer

        self._data_sources = []
        debt_items = []

        logger.info("[COST EST] Step 0: Profiling repository...")
        profiler = RepoProfiler()
        profile = profiler.profile(repo_path, github_url)
        stack_rates = profile["rates"]["rates_by_category"]
        multipliers = profile["multipliers"]
        ai_files = profile["ai_detection"]["suspected_files"]
        ai_file_paths = {f["file"] for f in ai_files}
        tech_stack = profile["tech_stack"]

        logger.info(f"[COST EST] Profile complete - uses_ai: {profile['rates']['uses_ai']}")

        logger.info("[COST EST] Step 0b: Fetching dynamic benchmarks...")
        benchmarks = BenchmarkAgent().get_current_benchmarks(
            profile["tech_stack"]["primary_language"]
        )
        cisq_per_function = benchmarks["cost_per_function_usd"]
        self._track_data_source("benchmarks", benchmarks.get("confidence") != "high")
        logger.info(f"[COST EST] CISQ benchmark: ${cisq_per_function:.2f}/function ({benchmarks.get('cost_per_function_source')})")
        
        rates_source = stack_rates.get("code_quality", {}).get("confidence", "low")
        self._track_data_source("hourly_rates", rates_source == "low")

        logger.info("[COST EST] Step 1: Running static analysis...")
        static_analyzer = StaticAnalyzer()
        complexity_results = static_analyzer.get_summary(repo_path)

        logger.info("[COST EST] Step 2: Running GitMiner for code quality...")
        risky_files = GitMiner().get_risky_files(repo_path)
        code_quality_cost = 0.0

        base_rate = stack_rates.get("code_quality", {}).get("rate", 84.55)
        if base_rate is None:
            base_rate = 84.55

        for rf in risky_files:
            ai_premium = 1.5 if rf["file"] in ai_file_paths else 1.0
            adjusted_cost = rf["cost_usd"] * ai_premium

            debt_items.append({
                "file": rf["file"],
                "category": "code_quality",
                "severity": rf["severity"],
                "complexity": rf["max_complexity"],
                "remediation_hours": rf["adjusted_minutes"] / 60,
                "cost_usd": round(adjusted_cost, 2),
                "change_count": rf["change_count"],
                "churn_multiplier": rf["churn_multiplier"],
                "ai_premium": ai_premium,
                "rate": base_rate,
                "rate_source": "Dynamic blend",
                "type": "complexity_hotspot",
            })
            code_quality_cost += adjusted_cost
        logger.info(f"[COST EST] Code quality: {len(risky_files)} files, ${code_quality_cost:.2f}")

        logger.info("[COST EST] Step 3: Running security scan with risk weighting...")
        security_issues = static_analyzer.run_security_scan(repo_path)
        security_cost = 0.0
        security_rate = stack_rates.get("security", {}).get("rate", base_rate)
        security_agent = SecurityCostAgent()

        for issue in security_issues:
            cwe_id = issue.get("cwe_id", "CWE-UNKNOWN")
            severity = issue.get("severity", "MEDIUM")

            fix_hours = issue.get("remediation_hours", 4.0)
            cvss_score = 7.0 if severity == "HIGH" else 5.0

            cost_detail = security_agent.get_risk_weighted_cost(
                cwe_id, cvss_score, fix_hours, security_rate
            )

            debt_items.append({
                "file": issue["file"],
                "category": "security",
                "severity": severity,
                "line": issue.get("line", 0),
                "issue_text": issue.get("issue_text", ""),
                "bandit_test_id": issue.get("bandit_test_id", ""),
                "remediation_hours": fix_hours,
                "cost_usd": round(cost_detail["total_security_cost"], 2),
                "cost_detail": cost_detail,
                "rate": security_rate,
                "rate_source": "Dynamic blend",
                "type": "security_hotspot",
            })
            security_cost += cost_detail["total_security_cost"]
        
        func_count_for_security = complexity_results.get("total_functions", 0)
        base_security_cost = func_count_for_security * 28.0
        security_cost += base_security_cost
        
        debt_items.append({
            "file": "base_security",
            "category": "security",
            "severity": "low",
            "cost_usd": round(base_security_cost, 2),
            "remediation_hours": base_security_cost / security_rate,
            "type": "security_baseline",
        })
        
        logger.info(f"[COST EST] Security: {len(security_issues)} issues + base ${base_security_cost:.2f}, total ${security_cost:.2f}")

        logger.info("[COST EST] Step 4: Finding missing docstrings...")
        doc_issues = static_analyzer.find_missing_docstrings(repo_path)
        doc_cost = 0.0
        doc_rate = stack_rates.get("documentation", {}).get("rate", 55.10)

        for doc in doc_issues:
            remediation_minutes = doc.get("remediation_minutes", 10)
            cost_usd = (remediation_minutes / 60) * doc_rate

            debt_items.append({
                "file": doc["file"],
                "category": "documentation",
                "severity": doc.get("severity", "low"),
                "function": doc.get("function", ""),
                "line": doc.get("line", 0),
                "remediation_minutes": remediation_minutes,
                "remediation_hours": remediation_minutes / 60,
                "cost_usd": round(cost_usd, 2),
                "doc_type": doc.get("type", "missing_docstring"),
                "rate": doc_rate,
                "rate_source": "Dynamic blend",
                "type": "missing_docstring",
            })
            doc_cost += cost_usd
        logger.info(f"[COST EST] Documentation: {len(doc_issues)} issues, ${doc_cost:.2f}")

        logger.info("[COST EST] Step 5: Checking dependencies for vulnerabilities...")
        vuln_fetcher = VulnerabilityFetcher()
        dep_vulns = vuln_fetcher.check_dependencies_sync(repo_path)
        dep_cost = 0.0

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
            dep_cost += vuln.get("cost_usd", 0)
        logger.info(f"[COST EST] Dependencies: {len(dep_vulns)} vulnerabilities, ${dep_cost:.2f}")

        function_count = complexity_results.get("total_functions", 0)

        baseline_cost = (FUNCTION_BASELINE_MINUTES / 60) * base_rate * function_count
        logger.info(f"[COST EST] Baseline cost ({function_count} functions): ${baseline_cost:.2f}")

        total_cost = sum(item.get("cost_usd", 0) for item in debt_items)
        total_cost_with_baseline = total_cost + baseline_cost
        combined_multiplier = multipliers.get("combined_multiplier", MAINTENANCE_OVERHEAD_MULTIPLIER)
        total_cost = total_cost_with_baseline * combined_multiplier
        logger.info(f"[COST EST] Total with baseline and multipliers: ${total_cost:.2f}")

        debt_score = self.calculate_debt_score(total_cost, function_count, cisq_per_function)
        sanity = self.sanity_check(total_cost, function_count, cisq_per_function)
        cost_by_category = self._categorize_costs(debt_items)

        baseline_hours = baseline_cost / base_rate
        cost_by_category["code_quality"]["cost_usd"] += baseline_cost * combined_multiplier
        cost_by_category["code_quality"]["hours"] += baseline_hours * combined_multiplier

        total_hours = sum(item.get("remediation_hours", 0) for item in debt_items)
        total_hours = total_hours + baseline_hours * combined_multiplier
        total_sprints = total_hours / HOURS_PER_SPRINT

        logger.info(f"[COST EST] ========== TOTALS ==========")
        logger.info(f"[COST EST] Total debt items: {len(debt_items)}")
        logger.info(f"[COST EST] Total cost: ${total_cost:.2f}")
        logger.info(f"[COST EST] Total hours: {total_hours:.2f}")
        logger.info(f"[COST EST] Function count: {function_count}")
        logger.info(f"[COST EST] Combined multiplier: {combined_multiplier}x")

        return {
            "repo_path": repo_path,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_sources_used": self._data_sources,
            "total_cost_usd": round(total_cost, 2),
            "total_remediation_hours": round(total_hours, 2),
            "total_remediation_sprints": round(total_sprints, 2),
            "cost_by_category": cost_by_category,
            "debt_score": debt_score,
            "sanity_check": sanity,
            "debt_items": debt_items,
            "summary": {
                "files_scanned": complexity_results.get("total_files_scanned", 0),
                "functions_analyzed": function_count,
                "issues_found": len(debt_items),
                "avg_complexity": complexity_results.get("avg_complexity", 0),
            },
            "repo_profile": profile,
            "benchmarks_used": benchmarks,
            "combined_multiplier": combined_multiplier,
            "multiplier_breakdown": multipliers,
            "rate_confidence": stack_rates,
            "ai_suspected_files": len(ai_files),
            "data_sources": {
                "rates": "Dynamic: BLS + Levels.fyi + SO + DuckDuckGo",
                "remediation_times": "SonarCloud API or fallback",
                "security_costs": "IBM breach report + Verizon DBIR",
                "benchmarks": "CISQ via web search",
                "vulnerabilities": "OSV.dev live",
            },
        }
