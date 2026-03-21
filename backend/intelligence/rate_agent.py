"""Rate Intelligence Agent - Dynamic market rate fetching.

Finds current market rates for any technology using multiple sources:
- BLS API (government data)
- Levels.fyi (real offer letters)
- Stack Overflow Survey (community data)
- DuckDuckGo (supplementary search)

All results cached 7 days using CacheManager.
"""

import json
import logging
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any

import httpx

from core.cache_manager import get_cache

logger = logging.getLogger(__name__)

HOURS_PER_YEAR = 2080

FALLBACK_RATES = {
    "junior": 55.10,
    "mid": 84.55,
    "senior": 128.37,
}

ROLE_TO_YEARS = {
    "junior": (0, 2),
    "mid": (3, 7),
    "senior": (8, 99),
}

WEIGHTS = {
    "bls": 0.40,
    "levels": 0.30,
    "so": 0.20,
    "ddg": 0.10,
}


class RateIntelligenceAgent:
    """Dynamic rate intelligence using multiple sources.
    
    Tries sources in order of reliability:
    1. BLS API (government)
    2. Levels.fyi (real offers)
    3. Stack Overflow Survey
    4. DuckDuckGo search
    """

    def __init__(self) -> None:
        self._cache = get_cache()
        self._ddg_search_count = 0
        self._max_ddg_searches = 10

    def fetch_bls_rate(self) -> dict[str, Any]:
        """Fetch rates from BLS API.
        
        Returns:
            Dict with rate and source info
        """
        cache_key = self._cache.make_key("bls_rates")
        
        if self._cache.is_fresh(cache_key, "bls_data"):
            cached = self._cache.get(cache_key, "bls_data")
            if cached:
                return cached

        try:
            from data.rate_fetcher import RateFetcher
            fetcher = RateFetcher()
            data = fetcher.fetch_bls_rates()
            
            result = {
                "junior": data.get("junior", FALLBACK_RATES["junior"]),
                "mid": data.get("mid", FALLBACK_RATES["mid"]),
                "senior": data.get("senior", FALLBACK_RATES["senior"]),
                "source": f"BLS OES {data.get('year', '2024')}",
                "live": True,
                "fetched_at": data.get("fetched_at"),
            }
            
            self._cache.set(cache_key, "bls_data", result)
            return result
            
        except Exception as e:
            logger.warning(f"BLS fetch failed: {e}")
            return self._bls_fallback()

    def _bls_fallback(self) -> dict[str, Any]:
        """Return BLS fallback rates with citation."""
        return {
            "junior": FALLBACK_RATES["junior"],
            "mid": FALLBACK_RATES["mid"],
            "senior": FALLBACK_RATES["senior"],
            "source": "BLS OES May 2023 (fallback)",
            "live": False,
        }

    def fetch_levels_fyi(self, technology: str = "Python") -> dict[str, Any]:
        """Fetch rates from Levels.fyi salary data.
        
        Args:
            technology: Technology keyword to filter by
            
        Returns:
            Dict with rates by experience level
        """
        cache_key = self._cache.make_key("levels_fyi", technology)
        
        if self._cache.is_fresh(cache_key, "levels_fyi"):
            cached = self._cache.get(cache_key, "levels_fyi")
            if cached:
                return cached

        try:
            url = "https://www.levels.fyi/js/salaryData.json"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                salaries = response.json()

            filtered = [
                s for s in salaries
                if technology.lower() in str(s.get("title", "")).lower()
                or technology.lower() in str(s.get("companyName", "")).lower()
            ]

            if not filtered:
                return self._levels_fallback(technology)

            filtered = [s for s in filtered if s.get("totalyearlycompensation", 0) > 0]
            
            total = sum(s["totalyearlycompensation"] for s in filtered)
            median_annual = sorted(s["totalyearlycompensation"] for s in filtered)[
                len(filtered) // 2
            ]
            median_hourly = median_annual / HOURS_PER_YEAR

            result = {
                "junior": median_hourly * 0.8,
                "mid": median_hourly,
                "senior": median_hourly * 1.3,
                "median_annual": median_annual,
                "median_hourly": median_hourly,
                "sample_size": len(filtered),
                "technology": technology,
                "source": "Levels.fyi",
                "live": True,
            }

            self._cache.set(cache_key, "levels_fyi", result)
            return result

        except Exception as e:
            logger.warning(f"Levels.fyi fetch failed: {e}")
            return self._levels_fallback(technology)

    def _levels_fallback(self, technology: str) -> dict[str, Any]:
        """Return Levels.fyi fallback rates."""
        bls = self._bls_fallback()
        return {
            "junior": bls["junior"] * 1.05,
            "mid": bls["mid"] * 1.05,
            "senior": bls["senior"] * 1.05,
            "technology": technology,
            "source": "Levels.fyi (fallback)",
            "live": False,
        }

    def fetch_stackoverflow_rates(self) -> dict[str, Any]:
        """Fetch rates from Stack Overflow Developer Survey.
        
        Downloads and parses the annual survey data.
        Cached 30 days since survey is annual.
        
        Returns:
            Dict with rates by experience level
        """
        cache_key = self._cache.make_key("stackoverflow_rates")
        
        if self._cache.is_fresh(cache_key, "stackoverflow"):
            cached = self._cache.get(cache_key, "stackoverflow")
            if cached:
                return cached

        try:
            url = "https://survey.stackoverflow.co/datasets/stack-overflow-developer-survey-2024.zip"
            
            with httpx.Client(timeout=60) as client:
                response = client.get(url)
                response.raise_for_status()
                
                with zipfile.ZipFile(BytesIO(response.content)) as zf:
                    csv_name = [n for n in zf.namelist() if "survey_results" in n and n.endswith(".csv")][0]
                    with zf.open(csv_name) as f:
                        content = f.read().decode("utf-8", errors="ignore")
            
            lines = content.split("\n")
            headers = lines[0].lower().split(",")
            
            comp_idx = next((i for i, h in enumerate(headers) if "convertedcomp" in h), None)
            country_idx = next((i for i, h in enumerate(headers) if "country" in h), None)
            years_idx = next((i for i, h in enumerate(headers) if "yearscodepro" in h), None)
            
            if comp_idx is None or country_idx is None:
                return self._stackoverflow_fallback()

            us_data = []
            for line in lines[1:10000]:
                parts = line.split(",")
                if len(parts) > max(comp_idx, country_idx, years_idx or 0):
                    country = parts[country_idx].strip('"')
                    if country == "United States of America":
                        try:
                            comp = float(parts[comp_idx])
                            years_str = parts[years_idx].strip('"') if years_idx else "0"
                            years = float(years_str) if years_str else 0
                            if 0 < comp < 1000000:
                                us_data.append({"comp": comp, "years": years})
                        except (ValueError, IndexError):
                            continue

            if len(us_data) < 50:
                return self._stackoverflow_fallback()

            by_level = {"junior": [], "mid": [], "senior": []}
            for d in us_data:
                for role, (min_y, max_y) in ROLE_TO_YEARS.items():
                    if min_y <= d["years"] <= max_y:
                        by_level[role].append(d["comp"] / HOURS_PER_YEAR)

            result = {
                role: sum(vals) / len(vals) if vals else FALLBACK_RATES[role]
                for role, vals in by_level.items()
            }
            result.update({
                "sample_size": len(us_data),
                "source": "SO Survey 2024",
                "live": True,
            })

            self._cache.set(cache_key, "stackoverflow", result)
            return result

        except Exception as e:
            logger.warning(f"Stack Overflow fetch failed: {e}")
            return self._stackoverflow_fallback()

    def _stackoverflow_fallback(self) -> dict[str, Any]:
        """Return Stack Overflow fallback rates."""
        return {
            **FALLBACK_RATES,
            "source": "SO Survey 2024 (fallback)",
            "live": False,
        }

    def search_ddg_salary(self, technology: str) -> dict[str, Any]:
        """Search DuckDuckGo for salary information.
        
        Uses free DuckDuckGo search (no API key needed).
        Limited to 10 searches per full analysis.
        
        Args:
            technology: Technology to search for
            
        Returns:
            Dict with rate and search metadata
        """
        if self._ddg_search_count >= self._max_ddg_searches:
            logger.info("DDG search limit reached")
            return self._ddg_fallback(technology)

        cache_key = self._cache.make_key("ddg_salary", technology)
        
        if self._cache.is_fresh(cache_key, "ddg_searches"):
            cached = self._cache.get(cache_key, "ddg_searches")
            if cached:
                return cached

        try:
            from duckduckgo_search import DDGS
            
            query = f"{technology} engineer average hourly rate salary 2025"
            
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            
            self._ddg_search_count += 1
            
            figures = []
            sources = []
            
            for r in results:
                snippet = r.get("body", "")
                sources.append(r.get("href", ""))
                
                patterns = [
                    r"\$(\d+(?:\.\d+)?)\s*(?:per hour|/hr|hourly)",
                    r"\$(\d+(?:,\d+)?(?:\.\d+)?)[kK]\s*(?:per year|annual|/yr)",
                    r"\$(\d+(?:,\d+)+)\s*(?:per year|annual)",
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, snippet, re.IGNORECASE)
                    for match in matches:
                        try:
                            value = float(match.replace(",", ""))
                            if "k" in pattern.lower() and value < 1000:
                                value *= 1000
                            if "hourly" in pattern.lower() or "/hr" in pattern.lower():
                                hourly = value
                            else:
                                hourly = value / HOURS_PER_YEAR
                            
                            if 20 <= hourly <= 300:
                                figures.append(hourly)
                        except ValueError:
                            continue

            if figures:
                median_rate = sorted(figures)[len(figures) // 2]
            else:
                median_rate = self._ddg_fallback(technology)["rate"]

            result = {
                "rate": median_rate,
                "figures_found": len(figures),
                "sources": sources[:3],
                "query_used": query,
                "technology": technology,
                "source": "DuckDuckGo Search",
                "live": True,
            }

            self._cache.set(cache_key, "ddg_searches", result)
            return result

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            return self._ddg_fallback(technology)

    def _ddg_fallback(self, technology: str) -> dict[str, Any]:
        """Return DuckDuckGo fallback rate."""
        return {
            "rate": FALLBACK_RATES["mid"],
            "figures_found": 0,
            "sources": [],
            "query_used": None,
            "technology": technology,
            "source": "DuckDuckGo (fallback)",
            "live": False,
        }

    def blend_rates(self, technology: str = "Python", role: str = "mid") -> dict[str, Any]:
        """Blend rates from all sources with weights.
        
        Args:
            technology: Technology to search for
            role: Experience level (junior/mid/senior)
            
        Returns:
            Full blended rate result with confidence
        """
        sources = {}
        total_weight = 0.0
        live_count = 0

        bls = self.fetch_bls_rate()
        sources["bls"] = {
            "rate": bls.get(role, FALLBACK_RATES[role]),
            "weight": WEIGHTS["bls"],
            "live": bls.get("live", False),
        }
        if bls.get("live"):
            live_count += 1
            total_weight += WEIGHTS["bls"]

        levels = self.fetch_levels_fyi(technology)
        sources["levels"] = {
            "rate": levels.get(role, FALLBACK_RATES[role]),
            "weight": WEIGHTS["levels"],
            "live": levels.get("live", False),
        }
        if levels.get("live"):
            live_count += 1
            total_weight += WEIGHTS["levels"]

        so = self.fetch_stackoverflow_rates()
        sources["so"] = {
            "rate": so.get(role, FALLBACK_RATES[role]),
            "weight": WEIGHTS["so"],
            "live": so.get("live", False),
        }
        if so.get("live"):
            live_count += 1
            total_weight += WEIGHTS["so"]

        ddg = self.search_ddg_salary(technology)
        ddg_rate = ddg.get("rate", FALLBACK_RATES[role])
        if role == "junior":
            ddg_rate *= 0.8
        elif role == "senior":
            ddg_rate *= 1.3
        sources["ddg"] = {
            "rate": ddg_rate,
            "weight": WEIGHTS["ddg"],
            "live": ddg.get("live", False),
        }
        if ddg.get("live"):
            live_count += 1
            total_weight += WEIGHTS["ddg"]

        if total_weight == 0:
            total_weight = 1.0

        blended = sum(
            s["rate"] * (s["weight"] / total_weight)
            for s in sources.values()
        )

        if live_count >= 3:
            confidence = "high"
        elif live_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        citations = [
            f"BLS OES: {sources['bls']['rate']:.2f}/hr",
            f"Levels.fyi: {sources['levels']['rate']:.2f}/hr",
            f"SO Survey: {sources['so']['rate']:.2f}/hr",
            f"DDG: {sources['ddg']['rate']:.2f}/hr",
        ]

        return {
            "technology": technology,
            "role": role,
            "blended_rate": round(blended, 2),
            "confidence": confidence,
            "sources_used": live_count,
            "breakdown": {
                k: {**v, "rate": round(v["rate"], 2)}
                for k, v in sources.items()
            },
            "citations": citations,
            "cached_until": "7 days",
        }

    def get_rate(self, technology: str = "Python", role: str = "mid") -> float:
        """Simple wrapper returning just the blended rate.
        
        Args:
            technology: Technology keyword
            role: Experience level
            
        Returns:
            Blended hourly rate
        """
        result = self.blend_rates(technology, role)
        return result["blended_rate"]

    def get_all_rates(self, technology: str = "Python") -> dict[str, Any]:
        """Get all rates for all experience levels.
        
        Args:
            technology: Technology keyword
            
        Returns:
            Dict with rates for all roles
        """
        return {
            "junior": self.get_rate(technology, "junior"),
            "mid": self.get_rate(technology, "mid"),
            "senior": self.get_rate(technology, "senior"),
        }


def get_rate(technology: str = "Python", role: str = "mid") -> float:
    """Convenience function for getting a single rate."""
    return RateIntelligenceAgent().get_rate(technology, role)
