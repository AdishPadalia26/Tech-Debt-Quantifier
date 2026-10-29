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
    HOURLY_RATES,
    HOURS_PER_SPRINT,
    SANITY_CHECK_VARIANCE_THRESHOLD,
)
from tools.estimate_buckets import build_buckets, scale_factor
from tools.llm_estimator import LLMEstimator
from tools.path_filters import is_non_principal_path
from tools.scoring import (
    aggregate_repo_score,
    build_finding_payload,
    calculate_confidence,
    classify_business_impact,
    cost_range_for,
)

logger = logging.getLogger(__name__)

MODEL_VERSION = "2026.10-p1"
FALLBACK_RATIO_WARN_THRESHOLD = 0.10
DEGENERATE_MIN_FILES = 20
NON_PRINCIPAL_KINDS: tuple[str, ...] = ("test", "docs", "example", "generated")
FIXED_COST_TYPES: frozenset[str] = frozenset({"security_hotspot", "vulnerability"})
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "code_quality", "architecture", "security",
    "documentation", "dependency", "test_debt",
)

# Bandit severity -> representative CVSS base score (used only when no real
# CVSS score is available).
BANDIT_SEVERITY_CVSS: dict[str, float] = {"HIGH": 7.5, "MEDIUM": 5.0, "LOW": 2.5}
# OSV severity label -> representative CVSS (only when no numeric score).
OSV_SEVERITY_CVSS: dict[str, float] = {
    "CRITICAL": 9.0, "HIGH": 7.5, "MEDIUM": 5.0, "LOW": 2.5,
}
# Numeric confidence for LLM confidence labels (drives cost_range width only).
LLM_CONFIDENCE_SCORES: dict[str, float] = {"high": 0.85, "medium": 0.6, "low": 0.35}


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
        self.model_name: str | None = None
        self.llm_provider: str | None = None
        self.llm_estimator: LLMEstimator | None = None
        # Multi-provider pool: names of keyed providers (empty -> legacy path).
        self.pool_providers: list[str] = []
        self._pool_factory: Callable[[], Any] | None = None
        self._pool_stats: dict[str, Any] | None = None
        # Bucket estimation: only representatives of near-identical items go
        # to the LLM (see tools/estimate_buckets.py).
        from app_config import LLM_BUCKETING_ENABLED, LLM_MAX_BUCKETS

        self._bucketing_enabled: bool = LLM_BUCKETING_ENABLED
        self._max_buckets: int = LLM_MAX_BUCKETS
        if self._hybrid_enabled:
            try:
                from agents.llm_factory import available_pool_providers

                self.pool_providers = available_pool_providers()
            except Exception:
                logger.warning(
                    "[COST EST] Could not list LLM pool providers", exc_info=True
                )
            try:
                from agents.llm_factory import get_active_model_info, get_llm
                self.llm_estimator = LLMEstimator(llm=get_llm("json"))
                info = get_active_model_info()
                self.model_name = info.get("model")
                self.llm_provider = info.get("provider")
                logger.info(
                    "[COST EST] Hybrid LLM estimation enabled via %s (model=%s)",
                    self.llm_provider,
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
        """Calculate normalized debt score (0-10).

        ``function_count`` must be the full-repo estimate
        (``functions_estimated_total``) so it matches the scope of ``total_cost``.
        """
        debt_score = aggregate_repo_score(
            total_cost=total_cost,
            function_count=function_count,
            cisq_per_function=cisq_per_function,
            files_scanned=files_scanned,
            doc_function_floor=doc_function_floor,
        )
        logger.info(
            "[DEBT SCORE] functions=%s, cost_per_function=$%.2f, final=%.2f",
            function_count, total_cost / max(function_count, 1), debt_score,
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

    def _categorize_costs(
        self, debt_items: list[dict[str, Any]], repo_factor: float = 1.0
    ) -> dict[str, dict[str, Any]]:
        """Categorize principal costs by debt type, applying the repo factor.

        Items flagged ``principal: False`` are skipped. The repo factor is
        applied to both cost and hours so categories sum to the total.
        """
        categories: dict[str, dict[str, Any]] = {
            name: {"cost_usd": 0.0, "hours": 0.0, "item_count": 0}
            for name in DEFAULT_CATEGORIES
        }

        for item in debt_items:
            if item.get("principal") is False:
                continue
            category = item.get("category", "code_quality")
            if category not in categories:
                categories[category] = {"cost_usd": 0.0, "hours": 0.0, "item_count": 0}

            categories[category]["cost_usd"] += item.get("cost_usd", 0) * repo_factor
            categories[category]["hours"] += (
                item.get("remediation_hours", 0) * repo_factor
            )
            categories[category]["item_count"] += 1

        for cat in categories:
            categories[cat]["cost_usd"] = round(categories[cat]["cost_usd"], 2)
            categories[cat]["hours"] = round(categories[cat]["hours"], 2)

        return categories

    # ------------------------------------------------------------------
    # Hybrid LLM estimation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_fixed_cost(item: dict[str, Any]) -> bool:
        """Return True for items whose cost is set by a dedicated agent.

        Security findings and OSV vulnerabilities carry a risk-weighted cost
        that the hybrid pass must never overwrite.
        """
        return item.get("type") in FIXED_COST_TYPES

    def _estimate_single_item(
        self,
        item: dict[str, Any],
        churn_data: dict[str, int],
        hourly_rate: float,
    ) -> dict[str, Any]:
        """Hybrid estimation for one debt item.

        LLM provides hours + reasoning, formula applies churn and severity.

        Args:
            item: Original debt item dict.
            churn_data: Mapping of file path to change count.
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

        return self._apply_formula(item, llm_result, churn_data, hourly_rate)

    def _apply_formula(
        self,
        item: dict[str, Any],
        llm_result: dict[str, Any],
        churn_data: dict[str, int],
        hourly_rate: float,
    ) -> dict[str, Any]:
        """Apply churn and severity multipliers on top of LLM hours.

        Severity is applied exactly once, here. The repo-level factor is NOT
        applied per item; it is applied once to totals.

        Args:
            item: Original debt item dict.
            llm_result: Dict returned by LLMEstimator.
            churn_data: File path -> change count mapping.
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

        # --- severity multiplier from LLM score (the ONLY severity application) ---
        severity_score = llm_result["severity_score"]
        severity_multiplier = 1.0 + (severity_score - 5) * 0.08
        severity_multiplier = max(0.7, min(2.0, severity_multiplier))

        combined_multiplier = churn_multiplier * severity_multiplier
        adjusted_hours = base_hours * combined_multiplier
        base_cost_usd = base_hours * hourly_rate
        cost_usd = adjusted_hours * hourly_rate

        confidence_label = llm_result.get("confidence", "low")
        confidence_score = LLM_CONFIDENCE_SCORES.get(confidence_label, 0.35)
        source = llm_result.get("estimation_source", "llm")

        # --- explanation builder ---
        cost_factors: list[dict[str, str]] = []
        cost_factors.append({
            "label": "LLM-estimated base effort" if source == "llm"
            else "Category-default base effort",
            "value": f"{base_hours:.1f} hrs",
            "impact": "high",
            "source": source,
        })
        if confidence_label != "high":
            cost_factors.append({
                "label": "Estimation confidence",
                "value": confidence_label,
                "impact": "medium",
                "source": source,
            })
        cost_factors.append({
            "label": "Severity score",
            "value": f"{severity_score}/10 -> {severity_multiplier:.2f}x",
            "impact": "high" if severity_score >= 7 else "medium",
            "source": "hybrid",
        })
        if churn_count > 0:
            cost_factors.append({
                "label": "Git churn",
                "value": f"{churn_count} changes -> {churn_multiplier:.1f}x",
                "impact": "high" if churn_multiplier >= 1.8 else "medium",
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
            f"After churn and severity ({combined_multiplier:.2f}x), "
            f"the estimate is ${cost_usd:,.0f} before the repo-level factor."
        )
        cost_explanation = " ".join(explanation_parts)

        hours_by_level = {
            "junior": round(adjusted_hours * 2.0, 2),
            "mid": round(adjusted_hours, 2),
            "senior": round(adjusted_hours * 0.5, 2),
        }

        enriched: dict[str, Any] = {
            **item,
            "formula_applied": True,
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
            "combined_multiplier": round(combined_multiplier, 3),
            "severity_score": severity_score,
            "business_risk_score": llm_result["business_risk_score"],
            "fix_complexity_score": llm_result["fix_complexity_score"],
            "estimation_confidence": confidence_label,
            "confidence": confidence_score,
            "estimation_source": source,
            "primary_risk": llm_result.get("primary_risk", ""),
            "fix_summary": llm_result.get("fix_summary", ""),
            "cost_factors": cost_factors,
            "cost_explanation": cost_explanation,
        }
        if llm_result.get("estimation_error"):
            enriched["estimation_error"] = llm_result["estimation_error"]
        for key in ("estimation_provider", "estimation_model"):
            if llm_result.get(key):
                enriched[key] = llm_result[key]
        if llm_result.get("cached"):
            enriched["cached"] = True
        enriched["cost_range"] = cost_range_for(enriched["cost_usd"], confidence_score)
        return enriched

    def _estimate_single_item_with_timeout(
        self,
        item: dict[str, Any],
        churn_data: dict[str, int],
        hourly_rate: float,
        timeout_sec: int = 30,
    ) -> dict[str, Any]:
        """Wrap single-item estimation with a per-item timeout.

        Args:
            item: Debt item dict.
            churn_data: File path -> change count.
            hourly_rate: Blended hourly rate.
            timeout_sec: Max seconds per item.

        Returns:
            Enriched debt item dict (fallback on timeout).
        """
        # No ``with``: its shutdown(wait=True) would block on a hung LLM call
        # and defeat the timeout.
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = ex.submit(
                self._estimate_single_item, item, churn_data, hourly_rate,
            )
            try:
                return future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "LLM estimation timed out for %s - using fallback",
                    item.get("file", "?"),
                )
                fallback = LLMEstimator._fallback_estimates(
                    item.get("category", "code_quality"),
                    item.get("severity", "medium"),
                    error=f"TimeoutError: no response within {timeout_sec}s",
                )
                return self._apply_formula(item, fallback, churn_data, hourly_rate)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    def _estimate_batch(
        self,
        batch: list[dict[str, Any]],
        churn_data: dict[str, int],
        hourly_rate: float,
    ) -> list[dict[str, Any]]:
        """Hybrid estimation for a batch of items via ONE LLM call.

        The LLM estimates effort for every item in the batch in a single
        request (cutting request count by ~batch_size x); the deterministic
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
            self._apply_formula(item, llm_results[i], churn_data, hourly_rate)
            for i, item in enumerate(batch)
        ]

    def _estimate_batch_with_timeout(
        self,
        batch: list[dict[str, Any]],
        churn_data: dict[str, int],
        hourly_rate: float,
        timeout_sec: int = 90,
    ) -> list[dict[str, Any]]:
        """Wrap batch estimation with a timeout; per-item fallback on timeout."""
        # No ``with``: its shutdown(wait=True) would block on a hung LLM call
        # and defeat the timeout.
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = ex.submit(self._estimate_batch, batch, churn_data, hourly_rate)
            try:
                return future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "Batch LLM estimation timed out (%d items) - using fallback",
                    len(batch),
                )
                error = f"TimeoutError: batch not completed within {timeout_sec}s"
                return [
                    self._apply_formula(
                        item,
                        LLMEstimator._fallback_estimates(
                            item.get("category", "code_quality"),
                            item.get("severity", "medium"),
                            error=error,
                        ),
                        churn_data, hourly_rate,
                    )
                    for item in batch
                ]
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    def _preserve_fixed_cost(
        self, original: dict[str, Any], enriched: dict[str, Any]
    ) -> dict[str, Any]:
        """Keep an agent-priced item's cost; attach LLM output as metadata only.

        Args:
            original: Item before the hybrid pass (carries the real cost).
            enriched: Same item after ``_apply_formula``.

        Returns:
            The original item plus estimation metadata and ``llm_hours``.
        """
        metadata_keys = (
            "estimation_source", "estimation_error", "estimation_confidence",
            "estimation_provider", "estimation_model", "cached",
            "severity_score", "business_risk_score", "fix_complexity_score",
            "primary_risk", "fix_summary",
        )
        merged = dict(original)
        for key in metadata_keys:
            if key in enriched:
                merged[key] = enriched[key]
        merged["llm_hours"] = enriched.get("base_hours")
        confidence = enriched.get("confidence")
        if isinstance(confidence, (int, float)):
            merged["confidence"] = confidence
        merged["cost_range"] = cost_range_for(
            float(original.get("cost_usd", 0) or 0),
            float(merged.get("confidence", 0.5) or 0.5),
        )
        return merged

    @staticmethod
    def _pool_input(item: dict[str, Any]) -> dict[str, Any]:
        """Map a debt item to the dict shape LLMEstimator/LLMPool expect."""
        return {
            "file_path": item.get("file", ""),
            "category": item.get("category", "code_quality"),
            "severity": item.get("severity", "medium"),
            "description": item.get("description", item.get("issue_text", "")),
            "code_snippet": item.get("code_snippet", ""),
            "function_name": item.get("function", ""),
            "language": item.get("language", ""),
        }

    def _estimate_all_items(
        self,
        debt_items: list[dict[str, Any]],
        churn_data: dict[str, int],
        hourly_rate: float,
        max_workers: int = 4,
        batch_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Estimate all principal items, bucketing near-identical ones.

        Security and OSV items are always estimated individually (they keep
        their agent-computed cost). The remaining items are grouped into
        buckets; only each bucket's representative reaches the LLM and the
        other members reuse its hours scaled by their size metric. With
        bucketing disabled every item is estimated individually.

        Args:
            debt_items: Principal debt items.
            churn_data: File path -> change count mapping.
            hourly_rate: Blended hourly rate.
            max_workers: Max parallel LLM calls (single-LLM path).
            batch_size: Items per LLM call (single-LLM path).

        Returns:
            Enriched items in input order, each tagged ``estimation_method``.
        """
        self._pool_stats = None
        if not debt_items:
            return []
        if self._bucketing_enabled:
            results = self._estimate_with_buckets(
                debt_items, churn_data, hourly_rate, max_workers, batch_size
            )
        else:
            results = self._estimate_items_direct(
                debt_items, churn_data, hourly_rate, max_workers, batch_size
            )
        for item in results:
            item.setdefault("estimation_method", "individual")
        return results

    @staticmethod
    def _item_label(item: dict[str, Any]) -> str:
        """Return ``file:function`` (or just ``file``) for display."""
        file_path = str(item.get("file", "") or "")
        function = str(item.get("function", "") or "")
        return f"{file_path}:{function}" if function else file_path

    def _estimate_with_buckets(
        self,
        debt_items: list[dict[str, Any]],
        churn_data: dict[str, int],
        hourly_rate: float,
        max_workers: int = 4,
        batch_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Estimate fixed-cost items individually and the rest via buckets."""
        fixed_idx = [i for i, it in enumerate(debt_items) if self._is_fixed_cost(it)]
        loose_idx = [
            i for i, it in enumerate(debt_items) if not self._is_fixed_cost(it)
        ]
        buckets = build_buckets(
            [debt_items[i] for i in loose_idx], self._max_buckets
        )
        # Bucket member indices are relative to ``loose_idx``.
        rep_idx = {loose_idx[b.representative] for b in buckets}
        send_idx = sorted(set(fixed_idx) | rep_idx)
        send_items = [debt_items[i] for i in send_idx]
        logger.info(
            "[COST EST] Bucketing: %d items -> %d LLM inputs "
            "(%d buckets, %d fixed-cost items sent individually)",
            len(debt_items), len(send_items), len(buckets), len(fixed_idx),
        )

        sent = self._estimate_items_direct(
            send_items, churn_data, hourly_rate, max_workers, batch_size
        )
        if len(sent) != len(send_items):
            logger.error(
                "[COST EST] Bucket estimation returned %d of %d results; "
                "re-estimating individually", len(sent), len(send_items),
            )
            return self._estimate_items_direct(
                debt_items, churn_data, hourly_rate, max_workers, batch_size
            )
        by_idx = dict(zip(send_idx, sent))

        results: list[dict[str, Any] | None] = [None] * len(debt_items)
        for i in fixed_idx:
            results[i] = by_idx[i]
        for bucket in buckets:
            members = [loose_idx[m] for m in bucket.members]
            rep = loose_idx[bucket.representative]
            rep_enriched = by_idx[rep]
            if len(members) == 1:
                results[rep] = rep_enriched
                continue
            rep_label = self._item_label(debt_items[rep])
            for m in members:
                if m == rep:
                    enriched = rep_enriched
                    scale = 1.0
                else:
                    scale = scale_factor(debt_items[m], debt_items[rep])
                    enriched = self._apply_formula(
                        debt_items[m],
                        self._bucket_llm_result(rep_enriched, scale, rep_label),
                        churn_data, hourly_rate,
                    )
                enriched["estimation_method"] = "bucket"
                enriched["bucket_id"] = bucket.key
                enriched["bucket_size"] = len(members)
                enriched["bucket_representative"] = rep_label
                enriched["bucket_scale"] = round(scale, 3)
                results[m] = enriched
        return [r for r in results if r is not None]

    @staticmethod
    def _bucket_llm_result(
        rep_enriched: dict[str, Any], scale: float, rep_label: str
    ) -> dict[str, Any]:
        """Rebuild an LLM-result dict for a bucket member from its representative."""
        result: dict[str, Any] = {
            "realistic_hours": float(rep_enriched.get("base_hours", 0) or 0) * scale,
            "severity_score": rep_enriched.get("severity_score", 5),
            "business_risk_score": rep_enriched.get("business_risk_score", 4),
            "fix_complexity_score": rep_enriched.get("fix_complexity_score", 5),
            "confidence": rep_enriched.get("estimation_confidence", "low"),
            "primary_risk": rep_enriched.get("primary_risk", ""),
            "fix_summary": rep_enriched.get("fix_summary", ""),
            "cost_rationale": (
                f"Bucket estimate: representative {rep_label} scaled "
                f"{scale:.2f}x by size."
            ),
            "estimation_source": rep_enriched.get("estimation_source", "fallback"),
        }
        for key in ("estimation_error", "estimation_provider", "estimation_model"):
            if rep_enriched.get(key):
                result[key] = rep_enriched[key]
        if rep_enriched.get("cached"):
            result["cached"] = True
        return result

    def _estimate_items_direct(
        self,
        debt_items: list[dict[str, Any]],
        churn_data: dict[str, int],
        hourly_rate: float,
        max_workers: int = 4,
        batch_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Estimate every given item via the LLM pool, else the single-LLM path.

        When at least one pool provider is keyed (``self.pool_providers``) every
        item goes through ``LLMPool``; otherwise the single-LLM batched path
        (``_estimate_all_items_single``) is used. Security and OSV items keep
        their agent-computed cost either way.
        """
        self._pool_stats = None
        if not debt_items:
            return []
        if self.pool_providers or self._pool_factory is not None:
            try:
                return self._estimate_all_items_pool(
                    debt_items, churn_data, hourly_rate
                )
            except Exception:
                logger.error(
                    "[COST EST] LLM pool failed; using single-LLM path",
                    exc_info=True,
                )
                self._pool_stats = None
        return self._estimate_all_items_single(
            debt_items, churn_data, hourly_rate, max_workers, batch_size
        )

    def _estimate_all_items_pool(
        self,
        debt_items: list[dict[str, Any]],
        churn_data: dict[str, int],
        hourly_rate: float,
    ) -> list[dict[str, Any]]:
        """Run all items through ``LLMPool`` and apply the cost formula."""
        if self._pool_factory is not None:
            pool = self._pool_factory()
        else:
            from agents.llm_pool import LLMPool

            pool = LLMPool(self.pool_providers)
        inputs = [self._pool_input(it) for it in debt_items]
        logger.info(
            "[COST EST] Estimating %d items via LLM pool (%s)",
            len(inputs), ",".join(pool.providers),
        )
        llm_results, pool_stats = pool.estimate_items(inputs)
        self._pool_stats = pool_stats

        final: list[dict[str, Any]] = []
        for original, llm_result in zip(debt_items, llm_results):
            item = self._apply_formula(original, llm_result, churn_data, hourly_rate)
            if self._is_fixed_cost(original):
                item = self._preserve_fixed_cost(original, item)
            final.append(item)
        return final

    def _estimate_all_items_single(
        self,
        debt_items: list[dict[str, Any]],
        churn_data: dict[str, int],
        hourly_rate: float,
        max_workers: int = 4,
        batch_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Estimate all items in batched, parallel LLM calls, preserving order.

        Items are grouped into batches of ``batch_size`` (env HYBRID_BATCH_SIZE,
        default 20) and each batch is estimated in a single LLM call. Security
        and OSV items keep their agent-computed cost; the LLM output is only
        attached as metadata.

        Args:
            debt_items: List of debt item dicts.
            churn_data: File path -> change count mapping.
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
                    self._estimate_batch_with_timeout, batch, churn_data, hourly_rate,
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
                    error = f"{type(e).__name__}: {e}"
                    enriched = [
                        self._apply_formula(
                            it,
                            LLMEstimator._fallback_estimates(
                                it.get("category", "code_quality"),
                                it.get("severity", "medium"),
                                error=error,
                            ),
                            churn_data, hourly_rate,
                        )
                        for it in debt_items[start:start + batch_size]
                    ]
                for j, item in enumerate(enriched):
                    results[start + j] = item

        final: list[dict[str, Any]] = []
        for idx, item in enumerate(results):
            if item is None:
                continue
            original = debt_items[idx]
            if self._is_fixed_cost(original):
                item = self._preserve_fixed_cost(original, item)
            final.append(item)
        return final

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _item_cost_range(item: dict[str, Any]) -> dict[str, float]:
        """Return an item's cost_range, computing it from confidence if absent."""
        existing = item.get("cost_range")
        if isinstance(existing, dict) and {"p10", "p50", "p90"} <= set(existing):
            return existing
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = LLM_CONFIDENCE_SCORES.get(
                str(item.get("estimation_confidence", "")).lower(), 0.5
            )
        return cost_range_for(float(item.get("cost_usd", 0) or 0), float(confidence))

    @staticmethod
    def tag_principal(debt_items: list[dict[str, Any]]) -> None:
        """Flag each item ``principal`` and record its ``non_principal_kind``."""
        for item in debt_items:
            kind = is_non_principal_path(str(item.get("file", "") or ""))
            item["principal"] = kind is None
            if kind is not None:
                item["non_principal_kind"] = kind

    def _aggregate_costs(
        self, debt_items: list[dict[str, Any]], repo_factor: float
    ) -> dict[str, Any]:
        """Roll items up into totals, applying the repo factor exactly once.

        Args:
            debt_items: Items (already tagged via ``tag_principal``).
            repo_factor: Repo-level multiplier applied once at total level.

        Returns:
            Dict with total_cost_usd, total_cost_range, cost_by_category,
            total_remediation_hours, total_hours_by_level, non_principal_cost
            and waterfall.
        """
        if repo_factor <= 0:
            repo_factor = 1.0
        principal = [i for i in debt_items if i.get("principal") is not False]

        raw_total = sum(float(i.get("cost_usd", 0) or 0) for i in principal)
        total_cost = round(raw_total * repo_factor, 2)

        cost_by_category = self._categorize_costs(principal, repo_factor)
        total_hours = round(sum(c["hours"] for c in cost_by_category.values()), 2)

        junior = senior = 0.0
        for item in principal:
            hrs = float(item.get("remediation_hours", 0) or 0)
            levels = item.get("hours_by_level") or {}
            junior += float(levels.get("junior", hrs * 2.0))
            senior += float(levels.get("senior", hrs * 0.5))
        total_hours_by_level = {
            "junior": round(junior * repo_factor, 2),
            "mid": total_hours,
            "senior": round(senior * repo_factor, 2),
        }

        p10 = p90 = 0.0
        for item in principal:
            rng = self._item_cost_range(item)
            p10 += float(rng["p10"])
            p90 += float(rng["p90"])
        total_cost_range = {
            "p10": round(p10 * repo_factor, 2),
            "p50": total_cost,
            "p90": round(p90 * repo_factor, 2),
        }

        non_principal_cost = {kind: 0.0 for kind in NON_PRINCIPAL_KINDS}
        for item in debt_items:
            if item.get("principal") is False:
                kind = item.get("non_principal_kind", "generated")
                non_principal_cost[kind] = non_principal_cost.get(kind, 0.0) + float(
                    item.get("cost_usd", 0) or 0
                ) * repo_factor
        non_principal_cost = {k: round(v, 2) for k, v in non_principal_cost.items()}

        base = churn = severity = 0.0
        for item in principal:
            cost = float(item.get("cost_usd", 0) or 0)
            if item.get("formula_applied") and not self._is_fixed_cost(item):
                item_base = float(item.get("base_cost_usd", cost) or 0)
                churn_mult = float(item.get("churn_multiplier", 1.0) or 1.0)
                item_churn = item_base * (churn_mult - 1.0)
                base += item_base
                churn += item_churn
                severity += cost - item_base - item_churn
            else:
                base += cost
        waterfall_base = round(base, 2)
        waterfall_churn = round(churn, 2)
        waterfall_severity = round(severity, 2)
        waterfall = {
            "base": waterfall_base,
            "churn": waterfall_churn,
            "severity": waterfall_severity,
            "repo": round(
                total_cost - waterfall_base - waterfall_churn - waterfall_severity, 2
            ),
            "total": total_cost,
        }

        return {
            "total_cost_usd": total_cost,
            "total_cost_range": total_cost_range,
            "cost_by_category": cost_by_category,
            "total_remediation_hours": total_hours,
            "total_hours_by_level": total_hours_by_level,
            "non_principal_cost": non_principal_cost,
            "waterfall": waterfall,
        }

    def _estimation_stats(self, debt_items: list[dict[str, Any]]) -> dict[str, Any]:
        """Count LLM vs fallback estimates from each item's ``estimation_source``."""
        llm = sum(1 for i in debt_items if i.get("estimation_source") == "llm")
        per_provider: dict[str, int] = {}
        llm_models: dict[str, list[str]] = {}
        for i in debt_items:
            provider = i.get("estimation_provider")
            if i.get("estimation_source") == "llm" and provider:
                per_provider[provider] = per_provider.get(provider, 0) + 1
                model = i.get("estimation_model")
                if model and model not in llm_models.setdefault(provider, []):
                    llm_models[provider].append(model)
        pool_stats = self._pool_stats or {}
        fallback = sum(
            1 for i in debt_items if i.get("estimation_source") == "fallback"
        )
        total = llm + fallback
        llm_error: str | None = None
        for item in debt_items:
            if item.get("estimation_source") == "fallback" and item.get(
                "estimation_error"
            ):
                llm_error = str(item["estimation_error"])
                break
        if llm_error is None and self.llm_estimator is not None:
            llm_error = getattr(self.llm_estimator, "last_error", None)
        used = list(per_provider)
        bucket_items = [
            i for i in debt_items if i.get("estimation_method") == "bucket"
        ]
        buckets = len({i.get("bucket_id") for i in bucket_items})
        individual = sum(
            1 for i in debt_items
            if i.get("estimation_method") != "bucket"
            and i.get("estimation_source") in ("llm", "fallback")
        )
        return {
            "llm": llm,
            "fallback": fallback,
            "total": total,
            "fallback_ratio": round(fallback / total, 4) if total else 0.0,
            "llm_model": (
                ",".join(m for p in used for m in llm_models[p])
                if used else self.model_name
            ),
            "llm_provider": ",".join(used) if used else self.llm_provider,
            "llm_error": llm_error,
            "per_provider": per_provider,
            "llm_models": {p: ",".join(ms) for p, ms in llm_models.items()},
            "cache_hits": pool_stats.get("cache_hits", 0),
            "elapsed_s": pool_stats.get("elapsed_s"),
            "pool": pool_stats.get("per_provider", {}),
            "llm_calls_items": individual + buckets,
            "buckets": buckets,
            "items_via_bucket": len(bucket_items),
        }

    @staticmethod
    def _check_degenerate(files_scanned: int, functions_analyzed: int) -> str | None:
        """Flag static analysis that likely failed to find functions.

        Few functions per file is legitimate (class-only modules, config,
        empty ``__init__.py``), so that only yields a warning. Zero functions
        across many files means the analyzer broke, so the scan fails.

        Returns:
            Warning message, or None when the counts look sane.

        Raises:
            ValueError: When many files were scanned but no functions found.
        """
        if files_scanned <= DEGENERATE_MIN_FILES:
            return None
        if functions_analyzed == 0:
            raise ValueError(
                f"Degenerate analysis: {files_scanned} files scanned but "
                f"no functions analyzed"
            )
        if functions_analyzed < files_scanned:
            message = (
                f"Low function count: {functions_analyzed} functions in "
                f"{files_scanned} files; cost-per-function may be overstated"
            )
            logger.warning("[COST EST] %s", message)
            return message
        return None

    def _build_warnings(
        self,
        stats: dict[str, Any],
        benchmarks: dict[str, Any] | None,
        rates: dict[str, Any] | None,
        security_live: bool | None = None,
    ) -> list[str]:
        """Collect user-visible data-quality warnings."""
        warnings: list[str] = []
        if stats["total"] > 0 and stats["fallback_ratio"] > FALLBACK_RATIO_WARN_THRESHOLD:
            message = (
                f"{stats['fallback']} of {stats['total']} estimates "
                f"({stats['fallback_ratio']:.0%}) used category-default hours "
                f"because the LLM was unavailable"
            )
            if stats.get("llm_error"):
                message += f": {stats['llm_error']}"
            logger.error("[COST EST] %s", message)
            warnings.append(message)
        if rates is not None and rates.get("live") is False:
            if rates.get("source") == "env_fallback":
                warnings.append(
                    "Rates from ENGINEER_HOURLY_RATE in .env (live lookup failed)"
                )
            else:
                warnings.append("Rates from reference table (live lookup failed)")
        if benchmarks is not None and benchmarks.get("live") is False:
            warnings.append("Benchmarks from reference table (live lookup failed)")
        if security_live is False:
            warnings.append(
                "Security cost data from reference table (live lookup failed)"
            )
        return warnings

    @staticmethod
    def _build_data_sources(
        rates: dict[str, Any] | None,
        benchmarks: dict[str, Any] | None,
        security_detail: dict[str, Any] | None,
        reference_version: str | None,
    ) -> dict[str, Any]:
        """Describe data sources from actual citations and live flags."""

        def describe(label: str, data: dict[str, Any] | None) -> str:
            if not data:
                return f"{label}: unavailable"
            state = "live" if data.get("live") else "reference table"
            citation = data.get("citation") or data.get("source") or ""
            return f"{label} ({state}): {citation}".strip()

        sec_citations = (security_detail or {}).get("citations") or []
        security_live = (security_detail or {}).get("live")
        return {
            "rates": describe("Rates", rates),
            "remediation_times": "LLM estimate per item; category defaults when unavailable",
            "security_costs": (
                f"Security ({'live' if security_live else 'reference table'}): "
                + ("; ".join(str(c) for c in sec_citations) or "n/a")
            ),
            "benchmarks": describe("Benchmarks", benchmarks),
            "vulnerabilities": "OSV.dev",
            "reference_version": reference_version,
        }

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
        ai_files = profile.get("ai_detection", {}).get("suspected_files", [])
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

        rate_blend: dict[str, Any] | None = None
        try:
            from intelligence.rate_agent import RateIntelligenceAgent

            rate_blend = RateIntelligenceAgent().blend_rates(
                profile["tech_stack"]["primary_language"].title(), "mid"
            )
        except Exception:
            logger.warning("[COST EST] Rate blend metadata unavailable", exc_info=True)

        logger.info("[COST EST] Step 1: Running static analysis...")
        publish_progress(35, "Running static analysis")
        static_analyzer = StaticAnalyzer()
        complexity_results = static_analyzer.get_summary(repo_path)
        files_scanned = complexity_results.get("total_files_scanned", 0)
        function_count = complexity_results.get("total_functions", 0)
        degenerate_warning = self._check_degenerate(files_scanned, function_count)
        functions_total = (
            complexity_results.get("functions_estimated_total") or function_count
        )

        logger.info("[COST EST] Step 2: Running GitMiner for code quality...")
        publish_progress(42, "Mining git hotspots")
        risky_files = GitMiner().get_risky_files(
            repo_path, summary=complexity_results
        )
        code_quality_cost = 0.0

        base_rate = stack_rates.get("code_quality", {}).get("rate")
        if base_rate is None:
            base_rate = HOURLY_RATES["mid"]

        for rf in risky_files:
            debt_items.append({
                **rf,
                "complexity": rf["max_complexity"],
                "cost_usd": round(rf["cost_usd"], 2),
                "rate": base_rate,
                "rate_source": "Dynamic blend",
            })
            code_quality_cost += rf["cost_usd"]
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
        security_agent = SecurityCostAgent()  # one per scan: live data fetched once
        security_detail: dict[str, Any] | None = None

        for issue in security_issues:
            cwe_id = issue.get("cwe_id", "CWE-UNKNOWN")
            severity = issue.get("severity", "MEDIUM")

            fix_hours = issue.get("remediation_hours", 4.0)
            real_cvss = issue.get("cvss_score")
            if isinstance(real_cvss, (int, float)):
                cvss_score = float(real_cvss)
            else:
                cvss_score = BANDIT_SEVERITY_CVSS.get(
                    str(severity).upper(), BANDIT_SEVERITY_CVSS["LOW"]
                )

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
            security_detail = security_detail or cost_detail

        logger.info(f"[COST EST] Security: {len(security_issues)} issues, total ${security_cost:.2f}")

        logger.info("[COST EST] Step 4: Finding missing docstrings...")
        publish_progress(78, "Analyzing documentation debt")
        doc_issues = static_analyzer.find_missing_docstrings(repo_path)
        doc_cost = 0.0
        doc_rate = stack_rates.get("documentation", {}).get("rate")
        if doc_rate is None:
            doc_rate = HOURLY_RATES["junior"]

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
            vuln_hours = vuln.get("remediation_hours", 0)
            vuln_cvss = vuln.get("cvss_score")
            if not isinstance(vuln_cvss, (int, float)):
                vuln_cvss = OSV_SEVERITY_CVSS.get(
                    severity.upper(), BANDIT_SEVERITY_CVSS["MEDIUM"]
                )
            vuln_cost_detail = security_agent.get_risk_weighted_cost(
                vuln.get("cwe_id"), float(vuln_cvss), vuln_hours, base_rate
            )
            security_detail = security_detail or vuln_cost_detail
            finding = build_finding_payload(
                file_path="requirements.txt",
                category="dependency",
                severity=severity,
                remediation_hours=vuln_hours,
                hourly_rate=base_rate,
                confidence=confidence,
                business_impact=business_impact,
                extra={
                    "package": vuln.get("package", ""),
                    "installed_version": vuln.get("installed_version", ""),
                    "cve_id": vuln.get("cve_id", ""),
                    "cvss_score": vuln.get("cvss_score"),
                    "cvss_used": float(vuln_cvss),
                    "cost_detail": vuln_cost_detail,
                    "fixed_version": vuln.get("fixed_version"),
                    "type": "vulnerability",
                },
            )
            vuln_cost = round(vuln_cost_detail["total_security_cost"], 2)
            finding["cost_usd"] = vuln_cost
            finding["cost_range"] = cost_range_for(vuln_cost, confidence)
            debt_items.append(finding)
            dep_cost += vuln_cost
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

        # --- Principal vs non-principal scoping ---
        self.tag_principal(debt_items)
        principal_items = [i for i in debt_items if i["principal"]]
        non_principal_items = [i for i in debt_items if not i["principal"]]

        # --- Hybrid LLM estimation pass (principal items only) ---
        repo_factor = float(multipliers.get("combined_multiplier") or 1.0)
        if repo_factor <= 0:
            repo_factor = 1.0

        churn_data: dict[str, int] = {}
        for rf in risky_files:
            churn_data[rf.get("file", "")] = rf.get("change_count", 0)

        if self._hybrid_enabled and (
            self.llm_estimator is not None
            or self.pool_providers
            or self._pool_factory is not None
        ):
            publish_progress(88, "Running hybrid LLM effort estimates")
            logger.info(
                "[COST EST] Running hybrid LLM estimation on %d items...",
                len(principal_items),
            )
            principal_items = self._estimate_all_items(
                principal_items, churn_data, base_rate,
            )
            logger.info("[COST EST] Hybrid estimation complete.")
        else:
            logger.info("[COST EST] Hybrid estimation disabled - using formula only.")
        debt_items = principal_items + non_principal_items
        for item in debt_items:
            item["cost_range"] = self._item_cost_range(item)

        publish_progress(90, "Aggregating findings and costs")
        totals = self._aggregate_costs(debt_items, repo_factor)
        total_cost = totals["total_cost_usd"]
        total_hours = totals["total_remediation_hours"]
        total_sprints = total_hours / HOURS_PER_SPRINT
        cost_by_category = totals["cost_by_category"]

        debt_score = self.calculate_debt_score(
            total_cost, functions_total, cisq_per_function,
            files_scanned=files_scanned,
        )
        sanity = self.sanity_check(total_cost, functions_total, cisq_per_function)
        aggregated = FindingAggregator().aggregate(
            principal_items,
            ownership_context=ownership_analysis,
        )

        # --- Estimation accounting & warnings ---
        stats = self._estimation_stats(debt_items)
        warnings = self._build_warnings(
            stats, benchmarks, rate_blend,
            security_live=(security_detail or {}).get("live"),
        )
        if degenerate_warning:
            warnings.append(degenerate_warning)
        reference_version = (
            (rate_blend or {}).get("reference_version")
            or benchmarks.get("reference_version")
        )

        logger.info("[COST EST] ========== TOTALS ==========")
        logger.info(f"[COST EST] Total debt items: {len(debt_items)}")
        logger.info(f"[COST EST] Total cost: ${total_cost:.2f}")
        logger.info(f"[COST EST] Total hours: {total_hours:.2f}")
        logger.info(f"[COST EST] Function count: {function_count} (est. {functions_total})")
        logger.info(f"[COST EST] Repo factor: {repo_factor}x")
        logger.info(
            "[COST EST] Estimation: %d by LLM, %d by fallback",
            stats["llm"], stats["fallback"],
        )

        return {
            "repo_path": repo_path,
            "analysis_timestamp": datetime.now().isoformat(),
            "model_version": MODEL_VERSION,
            "data_sources_used": self._data_sources,
            "total_cost_usd": total_cost,
            "total_cost": total_cost,
            "total_cost_range": totals["total_cost_range"],
            "total_remediation_hours": total_hours,
            "total_remediation_sprints": round(total_sprints, 2),
            "total_hours_by_level": totals["total_hours_by_level"],
            "cost_by_category": cost_by_category,
            "non_principal_cost": totals["non_principal_cost"],
            "waterfall": totals["waterfall"],
            "debt_score": debt_score,
            "sanity_check": sanity,
            "debt_items": debt_items,
            "findings": aggregated["findings"],
            "module_summaries": aggregated["module_summaries"],
            "roadmap": aggregated["roadmap"],
            "ownership_summary": ownership_analysis.get("summary", {}),
            "summary": {
                "files_scanned": files_scanned,
                "functions_analyzed": function_count,
                "functions_estimated_total": functions_total,
                "issues_found": len(debt_items),
                "avg_complexity": complexity_results.get("avg_complexity", 0),
            },
            "repo_profile": profile,
            "benchmarks_used": benchmarks,
            "combined_multiplier": repo_factor,
            "multiplier_breakdown": multipliers,
            "rate_confidence": stack_rates,
            "ai_suspected_files": len(ai_files),
            "estimation_method": (
                "hybrid_llm_formula" if self._hybrid_enabled else "formula_only"
            ),
            "llm_model": stats["llm_model"] if self._hybrid_enabled else None,
            "estimation_stats": stats,
            "warnings": warnings,
            "items_estimated_by_llm": stats["llm"],
            "items_estimated_by_formula": len(debt_items) - stats["llm"],
            "hourly_rates": {
                "blended_rate": round(base_rate, 2),
                "confidence": rates_source or "medium",
                "sources_used": self._data_sources or ["reference table"],
                "live": (rate_blend or {}).get("live"),
                "citation": (rate_blend or {}).get("citation"),
                "reference_version": (rate_blend or {}).get("reference_version"),
            },
            "data_sources": self._build_data_sources(
                rate_blend, benchmarks, security_detail, reference_version,
            ),
        }
