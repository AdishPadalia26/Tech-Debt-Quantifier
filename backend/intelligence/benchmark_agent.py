"""Benchmark Agent - live cost-per-function lookup with cited fallback.

Pages that quote a per-function remediation cost are fetched in parallel
under a hard time box. A figure is accepted only if a dollar amount is
immediately tied to "per function" / "per function point" in one sentence and
falls in a sane range; otherwise the cited table value is used. Successes are
cached 24h, failures 1h.
"""

import logging
import re
from datetime import datetime
from typing import Any

import httpx

from data.reference_tables import (
    BENCHMARK_TABLE,
    COST_PER_FUNCTION_USD,
    REFERENCE_TABLES_VERSION,
    cached_call,
    run_parallel,
)

logger = logging.getLogger(__name__)

CISQ_FALLBACK = COST_PER_FUNCTION_USD
CISQ_YEAR = 2022

BENCHMARK_TIME_BOX_SECONDS = 8.0
REQUEST_TIMEOUT_SECONDS = 4.0

# Accepted range for a per-function(-point) dollar figure.
MIN_COST_PER_FUNCTION = 50.0
MAX_COST_PER_FUNCTION = 5_000.0

# Secondary sources that may quote the per-function cost. Tried in parallel;
# the first URL (in this order) with a strict match wins.
_CISQ_SCRAPE_URLS = [
    "https://www.it-cisq.org/",
    "https://www.castsoftware.com/glossary/cost-of-poor-quality-software",
    "https://linearb.io/blog/technical-debt-cost",
]

# Strict: "$<amount> per function [point]" (or "/function") with the amount
# directly adjacent to the unit.
_PER_FUNCTION_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:per|/|each)\s*function(?:\s+point)?\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def parse_per_function_cost(text: str) -> tuple[float, str] | None:
    """Strictly extract a per-function dollar cost from page text.

    Returns (value, sentence) for the first in-range match whose dollar
    amount is directly tied to "per function"/"per function point"; else None.
    """
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        for m in _PER_FUNCTION_RE.finditer(sentence):
            value = float(m.group(1).replace(",", ""))
            if MIN_COST_PER_FUNCTION <= value <= MAX_COST_PER_FUNCTION:
                return value, sentence.strip()[:300]
    return None


class BenchmarkAgent:
    """Fetches industry benchmarks live, with cited table fallbacks."""

    def _scrape_url(self, url: str) -> dict[str, Any] | None:
        """Fetch one page and strictly parse a per-function cost."""
        from bs4 import BeautifulSoup

        resp = httpx.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code != 200:
            return None
        text = BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True)
        parsed = parse_per_function_cost(text)
        if not parsed:
            return None
        value, snippet = parsed
        return {
            "cost_per_function_usd": value,
            "source": f"Scraped from {url}",
            "citation": f'{url}: "{snippet}"',
            "year": datetime.now().year,
            "url": url,
            "live": True,
            "fetched_at": datetime.now().isoformat(),
        }

    def _scrape_cisq_from_secondary_sources(self) -> dict[str, Any] | None:
        """Scrape all candidate pages in parallel under the time box."""
        results = run_parallel(
            {u: (lambda u=u: self._scrape_url(u)) for u in _CISQ_SCRAPE_URLS},
            BENCHMARK_TIME_BOX_SECONDS,
        )
        for url in _CISQ_SCRAPE_URLS:
            if results.get(url):
                logger.info("Per-function cost found at %s", url)
                return results[url]
        return None

    def get_cisq_benchmark(self) -> dict[str, Any]:
        """Return the cost-per-function figure: live scrape, else the table."""
        result = cached_call("cost_per_function", self._scrape_cisq_from_secondary_sources)
        if result:
            return result
        logger.warning("No live cost-per-function figure; using reference table")
        entry = BENCHMARK_TABLE["cost_per_function_usd"]
        return {
            "cost_per_function_usd": entry["value"],
            "source": entry["source"],
            "citation": entry["citation"],
            "year": CISQ_YEAR,
            "url": "https://www.it-cisq.org/",
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

    def get_current_benchmarks(self, language: str = "python") -> dict[str, Any]:
        """Get benchmarks for a language (live cost/function, table otherwise).

        Args:
            language: Programming language

        Returns:
            Benchmark data with per-source details and live flags
        """
        cisq = self.get_cisq_benchmark()
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
