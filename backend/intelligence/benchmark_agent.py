"""Benchmark Agent - Dynamic industry benchmark fetching.

Fetches current industry benchmarks from multiple sources:
- CISQ cost of poor quality data
- SonarQube project benchmarks
- Language-specific debt metrics

Uses DuckDuckGo for web search to find latest figures.
"""

import logging
import re
from datetime import datetime
from typing import Any

from core.cache_manager import get_cache

logger = logging.getLogger(__name__)

CISQ_FALLBACK = 433.0
CISQ_YEAR = 2024


class BenchmarkAgent:
    """Fetches current industry benchmarks dynamically."""

    def __init__(self) -> None:
        self._cache = get_cache()
        self._search_count = 0
        self._max_searches = 10

    def get_cisq_benchmark(self) -> dict[str, Any]:
        """Search for latest CISQ cost of poor quality figure.
        
        Returns:
            Dict with CISQ benchmark data
        """
        cache_key = self._cache.make_key("cisq_benchmark")

        if self._cache.is_fresh(cache_key, "cisq_benchmarks"):
            cached = self._cache.get(cache_key, "cisq_benchmarks")
            if cached:
                return cached

        if self._search_count < self._max_searches:
            try:
                from duckduckgo_search import DDGS

                query = "CISQ cost poor software quality per function 2024 2025"
                
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))

                self._search_count += 1

                figures = []
                sources = []

                for r in results:
                    snippet = r.get("body", "")
                    sources.append(r.get("href", ""))

                    matches = re.findall(r"\$[\d,]+(?:\.\d+)?", snippet)
                    for match in matches:
                        try:
                            value = float(match.replace("$", "").replace(",", ""))
                            if 100 <= value <= 10000:
                                figures.append(value)
                        except ValueError:
                            continue

                if figures:
                    result = {
                        "cost_per_function_usd": max(figures),
                        "source": "CISQ via web search",
                        "year": 2025,
                        "url": sources[0] if sources else None,
                        "live": True,
                        "fetched_at": datetime.now().isoformat(),
                    }
                else:
                    result = self._cisq_fallback()

                self._cache.set(cache_key, "cisq_benchmarks", result)
                return result

            except Exception as e:
                logger.warning(f"CISQ search failed: {e}")

        result = self._cisq_fallback()
        self._cache.set(cache_key, "cisq_benchmarks", result)
        return result

    def _cisq_fallback(self) -> dict[str, Any]:
        """Return CISQ fallback benchmark."""
        return {
            "cost_per_function_usd": CISQ_FALLBACK,
            "source": "CISQ 2022 (fallback)",
            "year": CISQ_YEAR,
            "url": "https://www.it-cisq.org/measure-of-risk/",
            "live": False,
        }

    def get_sonarqube_language_benchmark(self, language: str) -> dict[str, Any]:
        """Search for SonarQube benchmarks for a language.
        
        Args:
            language: Programming language
            
        Returns:
            Dict with SonarQube benchmark data
        """
        cache_key = self._cache.make_key("sonar_benchmark", language)

        if self._cache.is_fresh(cache_key, "cisq_benchmarks"):
            cached = self._cache.get(cache_key, "cisq_benchmarks")
            if cached:
                return cached

        if self._search_count < self._max_searches:
            try:
                from duckduckgo_search import DDGS

                query = f"SonarQube average technical debt {language} projects days benchmark"

                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))

                self._search_count += 1

                days_figures = []
                pct_figures = []
                sources = []

                for r in results:
                    snippet = r.get("body", "")
                    sources.append(r.get("href", ""))

                    days_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:days|debt days)", snippet)
                    for match in days_matches:
                        try:
                            days_figures.append(float(match))
                        except ValueError:
                            continue

                    pct_matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", snippet)
                    for match in pct_matches:
                        try:
                            val = float(match)
                            if 1 <= val <= 50:
                                pct_figures.append(val)
                        except ValueError:
                            continue

                avg_days = sum(days_figures) / len(days_figures) if days_figures else 15.0
                avg_pct = sum(pct_figures) / len(pct_figures) if pct_figures else 10.0

                result = {
                    "language": language,
                    "avg_debt_days": round(avg_days, 1),
                    "avg_debt_ratio_pct": round(avg_pct, 1),
                    "source": "SonarQube via web search",
                    "url": sources[0] if sources else None,
                    "live": True,
                    "fetched_at": datetime.now().isoformat(),
                }

                self._cache.set(cache_key, "cisq_benchmarks", result)
                return result

            except Exception as e:
                logger.warning(f"SonarQube search failed: {e}")

        return self._sonar_fallback(language)

    def _sonar_fallback(self, language: str) -> dict[str, Any]:
        """Return SonarQube fallback benchmark."""
        return {
            "language": language,
            "avg_debt_days": 15.0,
            "avg_debt_ratio_pct": 10.0,
            "source": "SonarQube average (fallback)",
            "live": False,
        }

    def get_current_benchmarks(self, language: str = "python") -> dict[str, Any]:
        """Get all current benchmarks for a language.
        
        Args:
            language: Programming language
            
        Returns:
            Complete benchmark data
        """
        cisq = self.get_cisq_benchmark()
        sonar = self.get_sonarqube_language_benchmark(language)

        confidence = "high" if cisq.get("live") else "low"

        return {
            "cost_per_function_usd": cisq.get("cost_per_function_usd", CISQ_FALLBACK),
            "cost_per_function_source": cisq.get("source", "CISQ 2022"),
            "cost_per_function_year": cisq.get("year", CISQ_YEAR),
            "avg_debt_days": sonar.get("avg_debt_days", 15.0),
            "avg_debt_ratio_pct": sonar.get("avg_debt_ratio_pct", 10.0),
            "language": language,
            "confidence": confidence,
            "last_updated": cisq.get("fetched_at", datetime.now().isoformat()),
            "sources": {
                "cisq": cisq.get("source"),
                "sonar": sonar.get("source"),
            },
        }

    def get_cost_per_function(self, language: str = "python") -> float:
        """Convenience method to get just the cost per function.
        
        Args:
            language: Programming language
            
        Returns:
            Cost per function in USD
        """
        benchmark = self.get_current_benchmarks(language)
        return benchmark["cost_per_function_usd"]
