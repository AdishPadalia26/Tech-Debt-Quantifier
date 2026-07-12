"""Cost estimator for technical debt quantification.

Produces comprehensive dollar-based cost estimates for technical debt.
Combines complexity, security, documentation, and dependency analysis.

Uses the intelligence layer for dynamic data:
- RepoProfiler for tech stack detection
- RateIntelligenceAgent for market rates
- BenchmarkAgent for industry benchmarks
- SecurityCostAgent for risk-weighted security costs
"""

import concurrent.futures
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable

from constants import (
    FUNCTION_BASELINE_MINUTES,
    HOURS_PER_SPRINT,
    MAINTENANCE_OVERHEAD_MULTIPLIER,
    SANITY_CHECK_VARIANCE_THRESHOLD,
)
from tools.llm_estimator import LLMEstimator
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

        # --- Hybrid LLM estimation setup ---
        self._hybrid_enabled = os.getenv(
            "HYBRID_ESTIMATION_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        self.model_name = os.getenv("GROQ_MODEL_ID", os.getenv("OLLAMA_MODEL", "llama-3.3-70b-versatile"))
        self.llm_estimator: LLMEstimator | None = None
        if self._hybrid_enabled:
            try:
                from agents.llm_factory import get_llm
                self.llm_estimator = LLMEstimator(llm=get_llm("json"))
                logger.info(
                    "[COST EST] Hybrid LLM estimation enabled via %s (model=%s)",
                    os.getenv("LLM_PROVIDER", "groq"),
                    self.model_name,
                )
            except Exception as exc:
                logger.warning(
                    "[COST EST] Could not initialise LLM for hybrid estimation: %s. "
                    "Falling back to formula-only estimation.",
                    exc,
                    exc_info=True,
                )
                self.llm_estimator = None

    def _track_data_source(self, source_name: str, used_fallback: bool) -> None:
        """Track which data sources were used and whether fallbacks were needed."""
        status = "fallback" if used_fallback else "live"
        key = f"{source_name}:{status}"
        if key not in self._data_sources:
            self._data_sources.append(key)

    def calculate_debt_score(
        self,
        total_cost: float,
        function_count: int,
        cisq_per_function: float,
        files_scanned: int = 0,
        doc_function_floor: int = 0,
    ) -> float:
        """Calculate normalized debt score (0-10)."""
        logger.info(
            "[DEBT SCORE DEBUG] total_cost=%s, function_count=%s, files_scanned=%s, doc_floor=%s",
            total_cost, function_count, files_scanned, doc_function_floor,
        )
        debt_score = aggregate_repo_score(
            total_cost=total_cost,
            function_count=function_count,
            cisq_per_function=cisq_per_function,
            files_scanned=files_scanned,
            doc_function_floor=doc_function_floor,
        )
        effective = max(function_count, files_scanned * 5, doc_function_floor, 1)
        logger.info(
            "[DEBT SCORE] effective_count=%s, cost_per_unit=$%.2f, final=%.2f",
            effective, total_cost / effective, debt_score,
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

    # ------------------------------------------------------------------
    # Hybrid LLM estimation helpers
    # ------------------------------------------------------------------

    def _estimate_single_item(
        self,
        item: dict[str, Any],
        churn_data: dict[str, int],
        repo_risk: float,
        hourly_rate: float,
    ) -> dict[str, Any]:
        """Hybrid estimation for one debt item.

        LLM provides hours + reasoning, formula applies multipliers.

        Args:
            item: Original debt item dict.
            churn_data: Mapping of file path to change count.
            repo_risk: Repository-level risk multiplier.
            hourly_rate: Blended hourly engineering rate.

        Returns:
            Enriched debt item with hybrid cost fields.
        """
        if self.llm_estimator is None:
            llm_result = LLMEstimator._fallback_estimates(
                item.get("category", "code_quality"),
                item.get("severity", "medium"),
            )
        else:
            llm_result = self.llm_estimator.estimate_debt_item(
                file_path=item.get("file", ""),
                category=item.get("category", "code_quality"),
                severity=item.get("severity", "medium"),
                description=item.get("description", item.get("issue_text", "")),
                code_snippet=item.get("code_snippet", ""),
                function_name=item.get("function", ""),
                language=item.get("language", ""),
            )

        return self._apply_formula(item, llm_result, churn_data, repo_risk, hourly_rate)

    def _apply_formula(
        self,
        item: dict[str, Any],
        llm_result: dict[str, Any],
        churn_data: dict[str, int],
        repo_risk: float,
        hourly_rate: float,
    ) -> dict[str, Any]:
        """Apply deterministic formula multipliers on top of LLM hours.

        Args:
            item: Original debt item dict.
            llm_result: Dict returned by LLMEstimator.
            churn_data: File path -> change count mapping.
            repo_risk: Repo-level risk multiplier.
            hourly_rate: Blended hourly rate.

        Returns:
            Enriched debt item dict.
        """
        base_hours = llm_result["realistic_hours"]

        # --- churn multiplier ---
        file_path = item.get("file", "")
        churn_count = churn_data.get(file_path, 0)
        if churn_count >= 20:
            churn_multiplier = 2.5
        elif churn_count >= 10:
            churn_multiplier = 1.8
        elif churn_count >= 5:
            churn_multiplier = 1.3
        elif churn_count >= 1:
            churn_multiplier = 1.1
        else:
            churn_multiplier = 1.0

        # --- severity multiplier from LLM score ---
        severity_score = llm_result["severity_score"]
        severity_multiplier = 1.0 + (severity_score - 5) * 0.08
        severity_multiplier = max(0.7, min(2.0, severity_multiplier))

        repo_multiplier = max(1.0, min(2.0, repo_risk))

        combined_multiplier = (
            churn_multiplier * severity_multiplier * repo_multiplier
        )
        adjusted_hours = base_hours * combined_multiplier
        base_cost_usd = base_hours * hourly_rate
        cost_usd = adjusted_hours * hourly_rate

        # --- explanation builder ---
        cost_factors: list[dict[str, str]] = []
        cost_factors.append({
            "label": "LLM-estimated base effort",
            "value": f"{base_hours:.1f} hrs",
            "impact": "high",
            "source": "llm",
        })
        if llm_result["confidence"] != "high":
            cost_factors.append({
                "label": "Estimation confidence",
                "value": llm_result["confidence"],
                "impact": "medium",
                "source": "llm",
            })
        cost_factors.append({
            "label": "Severity score",
            "value": f"{severity_score}/10 → {severity_multiplier:.2f}x",
            "impact": "high" if severity_score >= 7 else "medium",
            "source": "hybrid",
        })
        if churn_count > 0:
            cost_factors.append({
                "label": "Git churn",
                "value": f"{churn_count} changes → {churn_multiplier:.1f}x",
                "impact": "high" if churn_multiplier >= 1.8 else "medium",
                "source": "formula",
            })
        if repo_multiplier > 1.05:
            cost_factors.append({
                "label": "Repo/team risk",
                "value": f"{repo_multiplier:.2f}x",
                "impact": "medium",
                "source": "formula",
            })
        cost_factors.append({
            "label": "Hourly rate",
            "value": f"${hourly_rate}/hr",
            "impact": "medium",
            "source": "config",
        })

        explanation_parts: list[str] = []
        cost_rationale = llm_result.get("cost_rationale", "")
        if cost_rationale:
            explanation_parts.append(cost_rationale)
        if churn_multiplier > 1.1:
            explanation_parts.append(
                f"This file changed {churn_count} times recently, "
                f"adding a {churn_multiplier:.1f}x maintenance risk multiplier."
            )
        if severity_multiplier > 1.15:
            explanation_parts.append(
                f"Severity score of {severity_score}/10 increased effort by "
                f"{severity_multiplier:.2f}x."
            )
        explanation_parts.append(
            f"At ${hourly_rate}/hr, base cost is ${base_cost_usd:,.0f}. "
            f"After multipliers ({combined_multiplier:.2f}x total), "
            f"final estimate is ${cost_usd:,.0f}."
        )
        cost_explanation = " ".join(explanation_parts)

        hours_by_level = {
            "junior": round(adjusted_hours * 2.0, 2),
            "mid": round(adjusted_hours, 2),
            "senior": round(adjusted_hours * 0.5, 2),
        }

        return {
            **item,
            "base_hours": round(base_hours, 2),
            "adjusted_hours": round(adjusted_hours, 2),
            "base_minutes": round(base_hours * 60, 1),
            "adjusted_minutes": round(adjusted_hours * 60, 1),
            "base_cost_usd": round(base_cost_usd, 2),
            "cost_usd": round(cost_usd, 2),
            "hourly_rate": hourly_rate,
            "remediation_hours": round(adjusted_hours, 2),
            "hours_by_level": hours_by_level,
            "severity_multiplier": round(severity_multiplier, 3),
            "churn_multiplier": round(churn_multiplier, 2),
            "repo_multiplier": round(repo_multiplier, 2),
            "combined_multiplier": round(combined_multiplier, 3),
            "severity_score": severity_score,
            "business_risk_score": llm_result["business_risk_score"],
            "fix_complexity_score": llm_result["fix_complexity_score"],
            "estimation_confidence": llm_result["confidence"],
            "primary_risk": llm_result.get("primary_risk", ""),
            "fix_summary": llm_result.get("fix_summary", ""),
            "cost_factors": cost_factors,
            "cost_explanation": cost_explanation,
        }

    def _estimate_single_item_with_timeout(
        self,
        item: dict[str, Any],
        churn_data: dict[str, int],
        repo_risk: float,
        hourly_rate: float,
        timeout_sec: int = 30,
    ) -> dict[str, Any]:
        """Wrap single-item estimation with a per-item timeout.

        Args:
            item: Debt item dict.
            churn_data: File path -> change count.
            repo_risk: Repo risk multiplier.
            hourly_rate: Blended hourly rate.
            timeout_sec: Max seconds per item.

        Returns:
            Enriched debt item dict (fallback on timeout).
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(
                self._estimate_single_item,
                item, churn_data, repo_risk, hourly_rate,
            )
            try:
                return future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "LLM estimation timed out for %s — using fallback",
                    item.get("file", "?"),
                )
                fallback = LLMEstimator._fallback_estimates(
                    item.get("category", "code_quality"),
                    item.get("severity", "medium"),
                )
                return self._apply_formula(
                    item, fallback, churn_data, repo_risk, hourly_rate,
                )

    def _estimate_batch(
        self,
        batch: list[dict[str, Any]],
        churn_data: dict[str, int],
        repo_risk: float,
        hourly_rate: float,
    ) -> list[dict[str, Any]]:
        """Hybrid estimation for a batch of items via ONE LLM call.

        The LLM estimates effort for every item in the batch in a single
        request (cutting request count by ~batch_size×); the deterministic
        formula is then applied per item.
        """
        if self.llm_estimator is None:
            llm_results = [
                LLMEstimator._fallback_estimates(
                    it.get("category", "code_quality"),
                    it.get("severity", "medium"),
                )
                for it in batch
            ]
        else:
            inputs = [
                {
                    "file_path": it.get("file", ""),
                    "category": it.get("category", "code_quality"),
                    "severity": it.get("severity", "medium"),
                    "description": it.get("description", it.get("issue_text", "")),
                    "code_snippet": it.get("code_snippet", ""),
                    "function_name": it.get("function", ""),
                    "language": it.get("language", ""),
                }
                for it in batch
            ]
            llm_results = self.llm_estimator.estimate_debt_items_batch(inputs)

        return [
            self._apply_formula(item, llm_results[i], churn_data, repo_risk, hourly_rate)
            for i, item in enumerate(batch)
        ]

    def _estimate_batch_with_timeout(
        self,
        batch: list[dict[str, Any]],
        churn_data: dict[str, int],
        repo_risk: float,
        hourly_rate: float,
        timeout_sec: int = 90,
    ) -> list[dict[str, Any]]:
        """Wrap batch estimation with a timeout; per-item fallback on timeout."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(
                self._estimate_batch, batch, churn_data, repo_risk, hourly_rate,
            )
            try:
                return future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "Batch LLM estimation timed out (%d items) — using fallback",
                    len(batch),
                )
                return [
                    self._apply_formula(
                        item,
                        LLMEstimator._fallback_estimates(
                            item.get("category", "code_quality"),
                            item.get("severity", "medium"),
                        ),
                        churn_data, repo_risk, hourly_rate,
                    )
                    for item in batch
                ]

    def _estimate_all_items(
        self,
        debt_items: list[dict[str, Any]],
        churn_data: dict[str, int],
        repo_risk: float,
        hourly_rate: float,
        max_workers: int = 4,
        batch_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Estimate all items in batched, parallel LLM calls, preserving order.

        Items are grouped into batches of ``batch_size`` (env HYBRID_BATCH_SIZE,
        default 20) and each batch is estimated in a single LLM call, so a
        34k-item repo makes ~1.7k requests instead of 34k — staying well under
        provider rate limits. Batches run across ``max_workers`` threads.

        Args:
            debt_items: List of debt item dicts.
            churn_data: File path -> change count mapping.
            repo_risk: Repo risk multiplier.
            hourly_rate: Blended hourly rate.
            max_workers: Max parallel LLM calls.
            batch_size: Items per LLM call (defaults to env HYBRID_BATCH_SIZE).

        Returns:
            List of enriched debt items.
        """
        if not debt_items:
            return []

        if batch_size is None:
            try:
                batch_size = int(os.getenv("HYBRID_BATCH_SIZE", "20"))
            except ValueError:
                batch_size = 20
        batch_size = max(1, batch_size)

        batches = [
            debt_items[i:i + batch_size]
            for i in range(0, len(debt_items), batch_size)
        ]
        logger.info(
            "[COST EST] Estimating %d items in %d batches of up to %d (%d workers)",
            len(debt_items), len(batches), batch_size, max_workers,
        )

        results: list[dict[str, Any] | None] = [None] * len(debt_items)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._estimate_batch_with_timeout,
                    batch, churn_data, repo_risk, hourly_rate,
                ): b_idx * batch_size
                for b_idx, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                start = futures[future]
                try:
                    enriched = future.result()
                except Exception as e:
                    logger.error(
                        "Batch estimation failed at offset %d: %s", start, e, exc_info=True,
                    )
                    enriched = [
                        {
                            **it,
                            "cost_usd": 0,
                            "cost_explanation": f"Estimation failed: {e}",
                            "estimation_confidence": "failed",
                        }
                        for it in debt_items[start:start + batch_size]
                    ]
                for j, item in enumerate(enriched):
                    results[start + j] = item

        return [r for r in results if r is not None]

    def estimate_total_cost(
        self,
        repo_path: str,
        github_url: str = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
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
        from intelligence.ownership_analyzer import OwnershipAnalyzer
        from intelligence.repo_profiler import RepoProfiler
        from intelligence.security_cost_agent import SecurityCostAgent
        from services.finding_aggregator import FindingAggregator
        from tools.architecture_analysis import ArchitectureAnalyzer
        from tools.dead_code_analysis import DeadCodeAnalyzer
        from tools.dependency_analysis import DependencyDebtAnalyzer
        from tools.duplication_analysis import DuplicationAnalyzer
        from tools.git_mining import GitMiner
        from tools.performance_analysis import PerformanceAnalyzer
        from tools.reliability_analysis import ReliabilityAnalyzer
        from tools.static_analysis import StaticAnalyzer
        from tools.test_debt_analysis import TestDebtAnalyzer

        self._data_sources = []
        debt_items = []

        def publish_progress(progress: int, phase: str) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(progress, phase)
            except Exception:
                logger.debug("Progress callback failed", exc_info=True)

        logger.info("[COST EST] Step 0: Profiling repository...")
        publish_progress(25, "Profiling repository")
        profiler = RepoProfiler()
        profile = profiler.profile(repo_path, github_url)
        stack_rates = profile["rates"]["rates_by_category"]
        multipliers = profile["multipliers"]
        ai_files = profile["ai_detection"]["suspected_files"]
        ai_file_paths = {f["file"] for f in ai_files}
        logger.info(f"[COST EST] Profile complete - uses_ai: {profile['rates']['uses_ai']}")

        logger.info("[COST EST] Step 0b: Fetching dynamic benchmarks...")
        publish_progress(30, "Fetching benchmarks and rates")
        benchmarks = BenchmarkAgent().get_current_benchmarks(
            profile["tech_stack"]["primary_language"]
        )
        cisq_per_function = benchmarks["cost_per_function_usd"]
        self._track_data_source("benchmarks", benchmarks.get("confidence") != "high")
        logger.info(f"[COST EST] CISQ benchmark: ${cisq_per_function:.2f}/function ({benchmarks.get('cost_per_function_source')})")
        
        rates_source = stack_rates.get("code_quality", {}).get("confidence", "low")
        self._track_data_source("hourly_rates", rates_source == "low")

        logger.info("[COST EST] Step 1: Running static analysis...")
        publish_progress(35, "Running static analysis")
        static_analyzer = StaticAnalyzer()
        complexity_results = static_analyzer.get_summary(repo_path)

        logger.info("[COST EST] Step 2: Running GitMiner for code quality...")
        publish_progress(42, "Mining git hotspots")
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

        logger.info("[COST EST] Step 2a: Analyzing ownership concentration...")
        publish_progress(48, "Analyzing ownership concentration")
        hotspot_files = [item["file"] for item in risky_files]
        ownership_analysis = OwnershipAnalyzer().analyze(
            repo_path,
            hotspot_files,
        )
        ownership_files = ownership_analysis.get("files", {})
        for item in debt_items:
            ownership = ownership_files.get(item.get("file", ""))
            if not ownership:
                continue
            item["owner_count"] = ownership.get("owner_count")
            item["top_contributor_share"] = ownership.get("top_contributor_share")
            item["ownership_risk"] = ownership.get("ownership_risk")
            item["ownership_bus_factor"] = ownership.get("bus_factor")
            item["top_author"] = ownership.get("top_author")
            item["ownership_confidence"] = ownership.get("ownership_confidence")

        logger.info("[COST EST] Step 2b: Running architecture analysis...")
        publish_progress(54, "Analyzing architecture debt")
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

        logger.info("[COST EST] Step 2c: Running duplication analysis...")
        publish_progress(58, "Analyzing duplication debt")
        duplication_items = DuplicationAnalyzer().analyze(repo_path, base_rate)
        duplication_cost = 0.0
        for item in duplication_items:
            item["rate"] = round(base_rate, 2)
            item["rate_source"] = "Dynamic blend"
            debt_items.append(item)
            duplication_cost += item["cost_usd"]
        logger.info(
            f"[COST EST] Duplication: {len(duplication_items)} issues, ${duplication_cost:.2f}"
        )

        logger.info("[COST EST] Step 2d: Running reliability analysis...")
        publish_progress(62, "Analyzing reliability debt")
        reliability_items = ReliabilityAnalyzer().analyze(repo_path, base_rate)
        reliability_cost = 0.0
        for item in reliability_items:
            item["rate"] = round(base_rate, 2)
            item["rate_source"] = "Dynamic blend"
            debt_items.append(item)
            reliability_cost += item["cost_usd"]
        logger.info(
            f"[COST EST] Reliability: {len(reliability_items)} issues, ${reliability_cost:.2f}"
        )

        logger.info("[COST EST] Step 2e: Running performance analysis...")
        publish_progress(66, "Analyzing performance debt")
        performance_items = PerformanceAnalyzer().analyze(repo_path, base_rate)
        performance_cost = 0.0
        for item in performance_items:
            item["rate"] = round(base_rate, 2)
            item["rate_source"] = "Dynamic blend"
            debt_items.append(item)
            performance_cost += item["cost_usd"]
        logger.info(
            f"[COST EST] Performance: {len(performance_items)} issues, ${performance_cost:.2f}"
        )

        logger.info("[COST EST] Step 2f: Running dead code analysis...")
        publish_progress(70, "Analyzing dead code")
        dead_code_items = DeadCodeAnalyzer().analyze(repo_path, base_rate)
        dead_code_cost = 0.0
        for item in dead_code_items:
            item["rate"] = round(base_rate, 2)
            item["rate_source"] = "Dynamic blend"
            debt_items.append(item)
            dead_code_cost += item["cost_usd"]
        logger.info(
            f"[COST EST] Dead code: {len(dead_code_items)} issues, ${dead_code_cost:.2f}"
        )

        logger.info("[COST EST] Step 3: Running security scan with risk weighting...")
        publish_progress(74, "Running security scan")
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
        publish_progress(78, "Analyzing documentation debt")
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
        publish_progress(81, "Analyzing test debt")
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
        publish_progress(84, "Checking dependency vulnerabilities")
        vuln_fetcher = VulnerabilityFetcher()
        dep_vulns = vuln_fetcher.check_dependencies_sync(repo_path)
        dep_cost = 0.0

        logger.info("[COST EST] Step 5a: Checking dependency hygiene...")
        publish_progress(86, "Checking dependency hygiene")
        dependency_hygiene_items = DependencyDebtAnalyzer().analyze(repo_path, base_rate)
        dependency_hygiene_cost = 0.0
        for item in dependency_hygiene_items:
            item["rate"] = round(base_rate, 2)
            item["rate_source"] = "Dynamic blend"
            debt_items.append(item)
            dependency_hygiene_cost += item["cost_usd"]

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
        logger.info(
            "[COST EST] Dependencies: %s hygiene issues + %s vulnerabilities, $%.2f",
            len(dependency_hygiene_items),
            len(dep_vulns),
            dependency_hygiene_cost + dep_cost,
        )

        for item in debt_items:
            ownership = ownership_files.get(item.get("file", ""))
            if not ownership:
                continue
            item["owner_count"] = ownership.get("owner_count")
            item["top_contributor_share"] = ownership.get("top_contributor_share")
            item["ownership_risk"] = ownership.get("ownership_risk")
            item["ownership_bus_factor"] = ownership.get("bus_factor")
            item["top_author"] = ownership.get("top_author")
            item["ownership_confidence"] = ownership.get("ownership_confidence")

        # --- Hybrid LLM estimation pass ---
        combined_multiplier = multipliers.get(
            "combined_multiplier", MAINTENANCE_OVERHEAD_MULTIPLIER,
        )
        repo_risk_value = max(1.0, min(2.0, combined_multiplier / 3.0))

        churn_data: dict[str, int] = {}
        for rf in risky_files:
            churn_data[rf.get("file", "")] = rf.get("change_count", 0)

        if self._hybrid_enabled and self.llm_estimator is not None:
            publish_progress(88, "Running hybrid LLM effort estimates")
            logger.info(
                "[COST EST] Running hybrid LLM estimation on %d items...",
                len(debt_items),
            )
            debt_items = self._estimate_all_items(
                debt_items, churn_data, repo_risk_value, base_rate,
            )
            logger.info("[COST EST] Hybrid estimation complete.")
        else:
            logger.info("[COST EST] Hybrid estimation disabled — using formula only.")

        publish_progress(90, "Aggregating findings and costs")
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
        total_cost = total_cost_with_baseline * combined_multiplier
        logger.info(f"[COST EST] Total with baseline and multipliers: ${total_cost:.2f}")

        files_scanned = complexity_results.get("total_files_scanned", 0)
        # doc_issues scans all Python files (no limit), so its length is a reliable
        # floor for the true function count when static analysis undersampled.
        doc_function_floor = len(doc_issues)
        debt_score = self.calculate_debt_score(
            total_cost, function_count, cisq_per_function,
            files_scanned=files_scanned, doc_function_floor=doc_function_floor,
        )
        sanity = self.sanity_check(total_cost, function_count, cisq_per_function)
        cost_by_category = self._categorize_costs(debt_items)
        aggregated = FindingAggregator().aggregate(
            debt_items,
            ownership_context=ownership_analysis,
        )

        cost_by_category["code_quality"]["cost_usd"] += baseline_cost * combined_multiplier
        cost_by_category["code_quality"]["hours"] += baseline_hours * combined_multiplier

        total_hours = sum(item.get("remediation_hours", 0) for item in debt_items)
        total_hours = total_hours + baseline_hours * combined_multiplier
        total_sprints = total_hours / HOURS_PER_SPRINT

        total_hours_by_level = {
            "junior": round(sum(item.get("hours_by_level", {}).get("junior", item.get("remediation_hours", 0) * 2.0) for item in debt_items), 2),
            "mid": round(total_hours, 2),
            "senior": round(sum(item.get("hours_by_level", {}).get("senior", item.get("remediation_hours", 0) * 0.5) for item in debt_items), 2),
        }

        # --- Estimation method metadata ---
        items_by_llm = sum(
            1 for item in debt_items
            if item.get("estimation_confidence") not in ("low", "failed", None)
        )
        items_by_formula = len(debt_items) - items_by_llm

        logger.info(f"[COST EST] ========== TOTALS ==========")
        logger.info(f"[COST EST] Total debt items: {len(debt_items)}")
        logger.info(f"[COST EST] Total cost: ${total_cost:.2f}")
        logger.info(f"[COST EST] Total hours: {total_hours:.2f}")
        logger.info(f"[COST EST] Function count: {function_count}")
        logger.info(f"[COST EST] Combined multiplier: {combined_multiplier}x")
        logger.info(
            "[COST EST] Estimation: %d by LLM, %d by formula",
            items_by_llm, items_by_formula,
        )

        return {
            "repo_path": repo_path,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_sources_used": self._data_sources,
            "total_cost_usd": round(total_cost, 2),
            "total_remediation_hours": round(total_hours, 2),
            "total_remediation_sprints": round(total_sprints, 2),
            "total_hours_by_level": total_hours_by_level,
            "cost_by_category": cost_by_category,
            "debt_score": debt_score,
            "sanity_check": sanity,
            "debt_items": debt_items,
            "findings": aggregated["findings"],
            "module_summaries": aggregated["module_summaries"],
            "roadmap": aggregated["roadmap"],
            "ownership_summary": ownership_analysis.get("summary", {}),
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
            "estimation_method": (
                "hybrid_llm_formula" if self._hybrid_enabled else "formula_only"
            ),
            "llm_model": self.model_name if self._hybrid_enabled else None,
            "items_estimated_by_llm": items_by_llm,
            "items_estimated_by_formula": items_by_formula,
            "hourly_rates": {
                "blended_rate": round(base_rate, 2),
                "confidence": rates_source or "medium",
                "sources_used": self._data_sources or ["BLS fallback"]
            },
            "data_sources": {
                "rates": "Dynamic: BLS + Levels.fyi + SO + DuckDuckGo",
                "remediation_times": "Hybrid: LLM + SonarCloud API",
                "security_costs": "IBM breach report + Verizon DBIR",
                "benchmarks": "CISQ via web search",
                "vulnerabilities": "OSV.dev live",
            },
        }
