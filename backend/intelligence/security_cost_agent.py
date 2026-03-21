"""Security Cost Agent - Dynamic breach cost and risk data.

Fetches current data breach costs and risk probabilities:
- IBM Cost of Data Breach Report
- Verizon DBIR (Data Breach Investigations Report)
- CWE-specific breach costs

Uses risk-weighted security cost calculation.
"""

import logging
import re
from datetime import datetime
from typing import Any

import httpx

from core.cache_manager import get_cache

logger = logging.getLogger(__name__)

IBM_BREACH_COST_FALLBACK = 4_880_000
IBM_BREACH_YEAR = 2024
DBIR_BASE_RATE = 0.046


class SecurityCostAgent:
    """Dynamic security cost calculation using breach data."""

    def __init__(self) -> None:
        self._cache = get_cache()
        self._search_count = 0
        self._max_searches = 10

    def fetch_latest_breach_costs(self) -> dict[str, Any]:
        """Fetch latest breach cost data from IBM report.
        
        Returns:
            Dict with breach cost data
        """
        cache_key = self._cache.make_key("breach_costs")

        if self._cache.is_fresh(cache_key, "breach_costs"):
            cached = self._cache.get(cache_key, "breach_costs")
            if cached:
                return cached

        breach_cost = IBM_BREACH_COST_FALLBACK
        breach_year = IBM_BREACH_YEAR
        source = "IBM Cost of Data Breach Report 2024 (fallback)"
        live = False
        url = "https://www.ibm.com/reports/data-breach"

        if self._search_count < self._max_searches:
            try:
                from duckduckgo_search import DDGS

                query = "IBM cost data breach report 2025 average total cost"
                
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))

                self._search_count += 1

                figures = []
                sources = []

                for r in results:
                    snippet = r.get("body", "")
                    sources.append(r.get("href", ""))

                    matches = re.findall(r"\$?([\d,\.]+)\s*(?:million|m)", snippet, re.IGNORECASE)
                    for match in matches:
                        try:
                            value = float(match.replace(",", ""))
                            if 1 <= value <= 20:
                                figures.append(value * 1_000_000)
                        except ValueError:
                            continue

                if figures:
                    breach_cost = max(figures)
                    breach_year = 2025
                    source = "IBM Cost of Data Breach Report 2025 via web search"
                    live = True

            except Exception as e:
                logger.warning(f"Breach cost search failed: {e}")

        result = {
            "average_breach_cost": breach_cost,
            "year": breach_year,
            "source": source,
            "url": url,
            "live": live,
            "fetched_at": datetime.now().isoformat(),
        }

        self._cache.set(cache_key, "breach_costs", result)
        return result

    def fetch_dbir_probability(self) -> dict[str, Any]:
        """Fetch breach probability from Verizon DBIR.
        
        Returns:
            Dict with DBIR data
        """
        cache_key = self._cache.make_key("dbir_probability")

        if self._cache.is_fresh(cache_key, "breach_costs"):
            cached = self._cache.get(cache_key, "breach_costs")
            if cached and "dbir" in cached:
                return cached["dbir"]

        base_rate = DBIR_BASE_RATE
        source = "Verizon DBIR 2024 (fallback)"
        live = False

        if self._search_count < self._max_searches:
            try:
                from duckduckgo_search import DDGS

                query = "Verizon DBIR 2025 breach probability percentage statistics"

                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))

                self._search_count += 1

                pct_figures = []
                sources = []

                for r in results:
                    snippet = r.get("body", "")
                    sources.append(r.get("href", ""))

                    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", snippet)
                    for match in matches:
                        try:
                            value = float(match)
                            if 0.1 <= value <= 50:
                                pct_figures.append(value / 100)
                        except ValueError:
                            continue

                if pct_figures:
                    base_rate = max(pct_figures)
                    source = "Verizon DBIR 2025 via web search"
                    live = True

            except Exception as e:
                logger.warning(f"DBIR search failed: {e}")

        result = {
            "base_breach_probability": base_rate,
            "source": source,
            "live": live,
        }

        return result

    def _get_cwe_breach_cost(self, cwe_id: str) -> float:
        """Get breach cost specific to a CWE type.
        
        Different vulnerability types have different average breach costs.
        Based on IBM research by attack type.
        
        Args:
            cwe_id: CWE identifier
            
        Returns:
            Breach cost for this vulnerability type
        """
        breach_data = self.fetch_latest_breach_costs()
        base_cost = breach_data["average_breach_cost"]

        cwe_multipliers = {
            "CWE-79": 0.5,    # XSS - lower impact
            "CWE-89": 1.5,    # SQL Injection - high impact
            "CWE-22": 1.2,    # Path Traversal
            "CWE-78": 1.3,    # OS Command Injection
            "CWE-352": 1.1,   # CSRF
            "CWE-287": 1.4,   # Improper Authentication
            "CWE-434": 1.0,    # Unrestricted Upload
            "CWE-78": 1.3,    # OS Command Injection
            "CWE-502": 0.9,   # Deserialization
            "CWE-915": 0.9,   # Improperly Controlled Modification
        }

        multiplier = cwe_multipliers.get(cwe_id, 1.0)
        return base_cost * multiplier

    def get_risk_weighted_cost(
        self,
        cwe_id: str,
        cvss_score: float,
        fix_hours: float,
        hourly_rate: float,
    ) -> dict[str, Any]:
        """Calculate risk-weighted security cost.
        
        Uses a simplified calculation that doesn't include massive breach costs
        by default. Only adds expected breach value for HIGH severity issues.
        
        Args:
            cwe_id: CWE identifier for the vulnerability
            cvss_score: CVSS severity score (0-10)
            fix_hours: Hours to fix the vulnerability
            hourly_rate: Developer hourly rate
            
        Returns:
            Complete security cost breakdown
        """
        breach_data = self.fetch_latest_breach_costs()
        dbir_data = self.fetch_dbir_probability()

        fix_cost = fix_hours * hourly_rate

        if cvss_score >= 9.0:
            breach_cost = self._get_cwe_breach_cost(cwe_id)
            breach_prob = dbir_data["base_breach_probability"] * 0.5
            expected_breach_value = breach_prob * breach_cost * 0.01
            total_security_cost = fix_cost + expected_breach_value
        else:
            expected_breach_value = 0
            total_security_cost = fix_cost

        return {
            "fix_cost": round(fix_cost, 2),
            "expected_breach_value": round(expected_breach_value, 2),
            "breach_probability_pct": round(breach_prob * 100, 2) if cvss_score >= 9.0 else 0,
            "breach_cost_used": round(breach_cost, 2) if cvss_score >= 9.0 else 0,
            "total_security_cost": round(total_security_cost, 2),
            "cvss_score": cvss_score,
            "cwe_id": cwe_id,
            "fix_hours": fix_hours,
            "hourly_rate": hourly_rate,
            "sources": [
                f"IBM: ${breach_data['average_breach_cost']:,.0f} ({breach_data['year']})",
                f"DBIR: {dbir_data['base_breach_probability']*100:.1f}% base rate",
            ],
            "data_fresh": breach_data.get("live", False) and dbir_data.get("live", False),
        }

    def get_simple_cost(
        self,
        severity: str,
        fix_hours: float,
        hourly_rate: float,
    ) -> float:
        """Simple security cost without risk weighting.
        
        Args:
            severity: Issue severity (HIGH/MEDIUM/LOW)
            fix_hours: Hours to fix
            hourly_rate: Developer rate
            
        Returns:
            Total fix cost
        """
        return fix_hours * hourly_rate
