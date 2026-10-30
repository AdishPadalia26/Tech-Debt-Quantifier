"""Benchmark Agent - live-derived cost-per-function with cited fallback.

No public source publishes a machine-readable "$ per function" figure, so the
benchmark is derived from live inputs instead of scraped:

    cost per function = live blended hourly rate x remediation hours per function

The hourly rate comes from RateIntelligenceAgent (BLS OES + web salary data).
Remediation hours per function is anchored so the cited reference rate yields
exactly the cited reference cost per function; only the rate moves with the
market. When no live rate is available the cited table value is used.
"""

import logging
from datetime import datetime
from typing import Any

from data.reference_tables import (
    BENCHMARK_TABLE,
    COST_PER_FUNCTION_USD,
    HOURLY_RATE_TABLE,
    REFERENCE_TABLES_VERSION,
)

logger = logging.getLogger(__name__)

CISQ_FALLBACK = COST_PER_FUNCTION_USD
CISQ_YEAR = 2022

REFERENCE_MID_RATE_USD = HOURLY_RATE_TABLE["mid"]["value"]

# Effort per function implied by the reference table: $310 / $90.30/h ~= 3.43 h.
REMEDIATION_HOURS_PER_FUNCTION = COST_PER_FUNCTION_USD / REFERENCE_MID_RATE_USD


class BenchmarkAgent:
    """Derives industry benchmarks from live rates, with cited table fallbacks."""

    def _fetch_live_rate(self, language: str) -> dict[str, Any] | None:
        """Return the mid-level blended rate for a language, or None on failure."""
        try:
            from intelligence.rate_agent import RateIntelligenceAgent

            return RateIntelligenceAgent().blend_rates(language.title(), "mid")
        except Exception:
            logger.warning("Live rate lookup for benchmark failed", exc_info=True)
            return None

    def get_cost_per_function_benchmark(
        self,
        language: str = "python",
        rate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the cost-per-function figure: live-derived, else the table.

        Args:
            language: Primary language, used when the rate must be fetched
            rate: Pre-fetched ``RateIntelligenceAgent.blend_rates`` result

        Returns:
            Benchmark entry with value, source, citation and live flag
        """
        if rate is None:
            rate = self._fetch_live_rate(language)

        hourly = float((rate or {}).get("blended_rate") or 0)
        if rate and rate.get("live") and hourly > 0:
            value = round(hourly * REMEDIATION_HOURS_PER_FUNCTION, 2)
            return {
                "cost_per_function_usd": value,
                "source": f"Live-derived: {rate.get('source', 'live rate blend')}",
                "citation": (
                    f"${hourly:.2f}/h live blended mid-level rate x "
                    f"{REMEDIATION_HOURS_PER_FUNCTION:.2f} remediation h/function "
                    f"(reference ${COST_PER_FUNCTION_USD:.0f} at "
                    f"${REFERENCE_MID_RATE_USD:.2f}/h). "
                    f"Rate sources: {rate.get('citation', '')}"
                ),
                "year": datetime.now().year,
                "url": "https://www.bls.gov/oes/current/oes151252.htm",
                "hourly_rate_usd": round(hourly, 2),
                "hours_per_function": round(REMEDIATION_HOURS_PER_FUNCTION, 2),
                "live": True,
                "fetched_at": datetime.now().isoformat(),
            }

        logger.warning("No live rate for cost-per-function benchmark; using reference table")
        entry = BENCHMARK_TABLE["cost_per_function_usd"]
        return {
            "cost_per_function_usd": entry["value"],
            "source": entry["source"],
            "citation": entry["citation"],
            "year": CISQ_YEAR,
            "url": "https://www.it-cisq.org/",
            "hourly_rate_usd": REFERENCE_MID_RATE_USD,
            "hours_per_function": round(REMEDIATION_HOURS_PER_FUNCTION, 2),
            "live": False,
            "fetched_at": datetime.now().isoformat(),
        }

    def get_sonarqube_language_benchmark(self, language: str) -> dict[str, Any]:
        """Return SonarQube-style debt benchmarks (cited table; not scraped).

        No reliable machine-readable public source exists, so these stay
        table values with live=False.
        """
        days = BENCHMARK_TABLE["avg_debt_days"]
        pct = BENCHMARK_TABLE["avg_debt_ratio_pct"]
        return {
            "language": language,
            "avg_debt_days": days["value"],
            "avg_debt_ratio_pct": pct["value"],
            "source": days["source"],
            "citation": days["citation"],
            "live": False,
            "fetched_at": datetime.now().isoformat(),
        }

    def get_current_benchmarks(
        self,
        language: str = "python",
        rate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get benchmarks for a language (live-derived cost/function, table otherwise).

        Args:
            language: Programming language
            rate: Optional pre-fetched blended rate to avoid a second lookup

        Returns:
            Benchmark data with per-source details and live flags
        """
        cisq = self.get_cost_per_function_benchmark(language, rate)
        sonar = self.get_sonarqube_language_benchmark(language)
        live_sources = int(bool(cisq["live"])) + int(bool(sonar["live"]))

        return {
            "cost_per_function_usd": cisq["cost_per_function_usd"],
            "cost_per_function_source": cisq["source"],
            "cost_per_function_year": cisq["year"],
            "avg_debt_days": sonar["avg_debt_days"],
            "avg_debt_ratio_pct": sonar["avg_debt_ratio_pct"],
            "language": language,
            "confidence": "high" if cisq["live"] else "low",
            "last_updated": cisq["fetched_at"],
            "sources": {
                "cisq": cisq["source"],
                "sonar": sonar["source"],
            },
            "source_details": {
                "cost_per_function": {
                    "value": cisq["cost_per_function_usd"],
                    "live": cisq["live"],
                    "source": cisq["source"],
                    "citation": cisq["citation"],
                    "hourly_rate_usd": cisq["hourly_rate_usd"],
                    "hours_per_function": cisq["hours_per_function"],
                    "fetched_at": cisq["fetched_at"],
                },
                "avg_debt_days": {
                    "value": sonar["avg_debt_days"],
                    "live": sonar["live"],
                    "source": sonar["source"],
                    "citation": sonar["citation"],
                    "fetched_at": sonar["fetched_at"],
                },
            },
            "citation": cisq["citation"],
            "live": bool(cisq["live"]),
            "live_sources": live_sources,
            "sources_used": live_sources,
            "reference_version": REFERENCE_TABLES_VERSION,
        }

    def get_cost_per_function(self, language: str = "python") -> float:
        """Convenience method to get just the cost per function."""
        return self.get_current_benchmarks(language)["cost_per_function_usd"]
