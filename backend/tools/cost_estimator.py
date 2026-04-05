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
    FUNCTION_BASELINE_MINUTES,
    HOURS_PER_SPRINT,
    MAINTENANCE_OVERHEAD_MULTIPLIER,
    SANITY_CHECK_VARIANCE_THRESHOLD,
)
from tools.scoring import (
    aggregate_repo_score,
    build_finding_payload,
    calculate_confidence,
    calculate_cost,
    classify_business_impact,
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
        debt_score = aggregate_repo_score(
            total_cost=total_cost,
            function_count=function_count,
            cisq_per_function=cisq_per_function,
        )

        logger.info(
            f"[DEBT SCORE] cost_per_function=${cost_per_function:.2f}, final={debt_score}"
        )

        return debt_score

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
        variance_pct = (cost_per_function - cisq_per_function) / cisq_per_function * 100
        
        # Being below industry average is always reasonable
        # Only flag as unreasonable if significantly above average
        is_reasonable = cost_per_function <= cisq_per_function or variance_pct < SANITY_CHECK_VARIANCE_THRESHOLD

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
            "architecture": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
            "security": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
            "documentation": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
            "dependency": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
            "test_debt": {"cost_usd": 0.0, "hours": 0.0, "item_count": 0},
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
        from data.vulnerability_fetcher import VulnerabilityFetcher
        from intelligence.benchmark_agent import BenchmarkAgent
        from intelligence.repo_profiler import RepoProfiler
        from intelligence.security_cost_agent import SecurityCostAgent
        from services.finding_aggregator import FindingAggregator
        from tools.architecture_analysis import ArchitectureAnalyzer
        from tools.git_mining import GitMiner
        from tools.static_analysis import StaticAnalyzer
        from tools.test_debt_analysis import TestDebtAnalyzer

        self._data_sources = []
        debt_items = []

        logger.info("[COST EST] Step 0: Profiling repository...")
        profiler = RepoProfiler()
        profile = profiler.profile(repo_path, github_url)
        stack_rates = profile["rates"]["rates_by_category"]
        multipliers = profile["multipliers"]
        ai_files = profile["ai_detection"]["suspected_files"]
        ai_file_paths = {f["file"] for f in ai_files}
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
                **rf,
                "complexity": rf["max_complexity"],
                "cost_usd": round(adjusted_cost, 2),
                "ai_premium": ai_premium,
                "rate": base_rate,
                "rate_source": "Dynamic blend",
            })
            code_quality_cost += adjusted_cost
        logger.info(f"[COST EST] Code quality: {len(risky_files)} files, ${code_quality_cost:.2f}")

        logger.info("[COST EST] Step 2b: Running architecture analysis...")
        architecture_items = ArchitectureAnalyzer().analyze(repo_path, base_rate * 1.2)
        architecture_cost = 0.0
        for arch_item in architecture_items:
            arch_item["rate"] = round(base_rate * 1.2, 2)
            arch_item["rate_source"] = "Dynamic blend"
            debt_items.append(arch_item)
            architecture_cost += arch_item["cost_usd"]
        logger.info(
            f"[COST EST] Architecture: {len(architecture_items)} issues, ${architecture_cost:.2f}"
        )

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

            confidence = calculate_confidence(category="security_scan")
            business_impact = classify_business_impact(
                severity=severity.lower(),
                churn_multiplier=1.0,
                change_count=0,
            )
            finding = build_finding_payload(
                file_path=issue["file"],
                category="security",
                severity=severity.lower(),
                remediation_hours=fix_hours,
                hourly_rate=security_rate,
                confidence=confidence,
                business_impact=business_impact,
                extra={
                    "line": issue.get("line", 0),
                    "issue_text": issue.get("issue_text", ""),
                    "bandit_test_id": issue.get("bandit_test_id", ""),
                    "cost_detail": cost_detail,
                    "rate": security_rate,
                    "rate_source": "Dynamic blend",
                    "type": "security_hotspot",
                },
            )
            finding["cost_usd"] = round(cost_detail["total_security_cost"], 2)
            debt_items.append(finding)
            security_cost += cost_detail["total_security_cost"]

        logger.info(f"[COST EST] Security: {len(security_issues)} issues, total ${security_cost:.2f}")

        logger.info("[COST EST] Step 4: Finding missing docstrings...")
        doc_issues = static_analyzer.find_missing_docstrings(repo_path)
        doc_cost = 0.0
        doc_rate = stack_rates.get("documentation", {}).get("rate", 55.10)

        for doc in doc_issues:
            remediation_minutes = doc.get("remediation_minutes", 10)
            cost_usd = (remediation_minutes / 60) * doc_rate

            confidence = calculate_confidence(category="documentation")
            severity = doc.get("severity", "low")
            business_impact = classify_business_impact(severity=severity)
            debt_items.append(
                build_finding_payload(
                    file_path=doc["file"],
                    category="documentation",
                    severity=severity,
                    remediation_hours=remediation_minutes / 60,
                    hourly_rate=doc_rate,
                    confidence=confidence,
                    business_impact=business_impact,
                    extra={
                        "function": doc.get("function", ""),
                        "line": doc.get("line", 0),
                        "remediation_minutes": remediation_minutes,
                        "doc_type": doc.get("type", "missing_docstring"),
                        "rate": doc_rate,
                        "rate_source": "Dynamic blend",
                        "type": "missing_docstring",
                    },
                )
            )
            doc_cost += cost_usd
        logger.info(f"[COST EST] Documentation: {len(doc_issues)} issues, ${doc_cost:.2f}")

        logger.info("[COST EST] Step 4b: Checking test debt...")
        hotspot_files = [item["file"] for item in risky_files]
        test_debt_items = TestDebtAnalyzer().find_test_gaps(repo_path, hotspot_files)
        test_debt_cost = 0.0

        for test_item in test_debt_items:
            test_item["rate"] = base_rate
            test_item["rate_source"] = "Dynamic blend"
            debt_items.append(test_item)
            test_debt_cost += test_item["cost_usd"]

        logger.info(
            f"[COST EST] Test debt: {len(test_debt_items)} issues, ${test_debt_cost:.2f}"
        )

        logger.info("[COST EST] Step 5: Checking dependencies for vulnerabilities...")
        vuln_fetcher = VulnerabilityFetcher()
        dep_vulns = vuln_fetcher.check_dependencies_sync(repo_path)
        dep_cost = 0.0

        for vuln in dep_vulns:
            severity = str(vuln.get("severity", "UNKNOWN")).lower()
            confidence = calculate_confidence(category="dependency")
            business_impact = classify_business_impact(severity=severity)
            finding = build_finding_payload(
                file_path="requirements.txt",
                category="dependency",
                severity=severity,
                remediation_hours=vuln.get("remediation_hours", 0),
                hourly_rate=base_rate,
                confidence=confidence,
                business_impact=business_impact,
                extra={
                    "package": vuln.get("package", ""),
                    "installed_version": vuln.get("installed_version", ""),
                    "cve_id": vuln.get("cve_id", ""),
                    "cvss_score": vuln.get("cvss_score"),
                    "fixed_version": vuln.get("fixed_version"),
                    "type": "vulnerability",
                },
            )
            finding["cost_usd"] = vuln.get("cost_usd", 0)
            debt_items.append(finding)
            dep_cost += vuln.get("cost_usd", 0)
        logger.info(f"[COST EST] Dependencies: {len(dep_vulns)} vulnerabilities, ${dep_cost:.2f}")

        function_count = complexity_results.get("total_functions", 0)

        baseline_hours = (FUNCTION_BASELINE_MINUTES / 60) * function_count
        baseline_cost = calculate_cost(
            effort_hours=baseline_hours,
            hourly_rate=base_rate,
            business_impact="low",
            confidence=0.35,
        )
        logger.info(f"[COST EST] Baseline cost ({function_count} functions): ${baseline_cost:.2f}")

        total_cost = sum(item.get("cost_usd", 0) for item in debt_items)
        total_cost_with_baseline = total_cost + baseline_cost
        combined_multiplier = multipliers.get("combined_multiplier", MAINTENANCE_OVERHEAD_MULTIPLIER)
        total_cost = total_cost_with_baseline * combined_multiplier
        logger.info(f"[COST EST] Total with baseline and multipliers: ${total_cost:.2f}")

        debt_score = self.calculate_debt_score(total_cost, function_count, cisq_per_function)
        sanity = self.sanity_check(total_cost, function_count, cisq_per_function)
        cost_by_category = self._categorize_costs(debt_items)
        aggregated = FindingAggregator().aggregate(debt_items)

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
            "findings": aggregated["findings"],
            "module_summaries": aggregated["module_summaries"],
            "roadmap": aggregated["roadmap"],
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
            "hourly_rates": {
                "blended_rate": round(base_rate, 2),
                "confidence": rates_source or "medium",
                "sources_used": self._data_sources or ["BLS fallback"]
            },
            "data_sources": {
                "rates": "Dynamic: BLS + Levels.fyi + SO + DuckDuckGo",
                "remediation_times": "SonarCloud API or fallback",
                "security_costs": "IBM breach report + Verizon DBIR",
                "benchmarks": "CISQ via web search",
                "vulnerabilities": "OSV.dev live",
            },
        }
