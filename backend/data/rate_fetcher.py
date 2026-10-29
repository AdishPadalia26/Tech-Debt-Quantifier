"""Rate fetcher for engineer hourly rates.

Default path queries the BLS public API for the OES 15-1252 (Software
Developers) national median annual wage, converts to an hourly wage (/2080),
applies level ratios and the ECEC loaded-cost factor. Results (and failures)
are cached; on failure the cited reference table is returned with live=False.
"""

import logging
from datetime import datetime
from typing import Any

import httpx

from data.reference_tables import (
    HOURLY_RATE_TABLE,
    HOURS_PER_YEAR,
    LEVEL_RATIOS,
    LOADED_COST_FACTOR,
    REFERENCE_TABLES_VERSION,
    cached_call,
)

logger = logging.getLogger(__name__)

BLS_TIMEOUT_SECONDS = 5.0

BLS_FALLBACK_RATES = {level: e["value"] for level, e in HOURLY_RATE_TABLE.items()}

# OES 15-1252 Software Developers, national (area 0000000, all industries),
# datatype 13 = annual median wage. verify series id against BLS.
# https://www.bls.gov/oes/current/oes151252.htm
BLS_SERIES_IDS = [
    "OEUN000000000000015125213",
]


class RateFetcher:
    """Fetches engineer hourly rates from the BLS API with caching."""

    def __init__(self) -> None:
        self._rates_cache: dict | None = None

    def _fetch_from_bls(self, series_id: str) -> float | None:
        """Fetch latest value from BLS API for the given series ID."""
        url = f"https://api.bls.gov/publicAPI/v1/timeseries/data/{series_id}"
        try:
            with httpx.Client(timeout=BLS_TIMEOUT_SECONDS) as client:
                response = client.get(url)
                if response.status_code != 200:
                    logger.warning("BLS API returned status %s", response.status_code)
                    return None
                data = response.json()
            if data.get("status") != "REQUEST_SUCCEEDED":
                logger.warning("BLS API error: %s", data.get("message"))
                return None
            series = data.get("Results", {}).get("series", [])
            observations = series[0].get("data", []) if series else []
            latest = observations[0].get("value") if observations else None
            return float(latest) if latest else None
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            logger.warning("BLS API error for series %s: %s", series_id, exc)
            return None

    def _live_bls(self) -> dict[str, Any] | None:
        """Query BLS; return a live rate dict or None on failure."""
        for series_id in BLS_SERIES_IDS:
            annual = self._fetch_from_bls(series_id)
            if annual and annual > 0:
                base_mid = annual / HOURS_PER_YEAR
                result: dict[str, Any] = {
                    level: round(base_mid * ratio * LOADED_COST_FACTOR, 2)
                    for level, ratio in LEVEL_RATIOS.items()
                }
                result.update({
                    "source": "BLS OES 15-1252 Software Developers (live API)",
                    "citation": (
                        f"BLS API series {series_id}: national median annual "
                        f"wage ${annual:,.0f} / {HOURS_PER_YEAR} h x level "
                        f"ratio x {LOADED_COST_FACTOR} loaded (BLS ECEC). "
                        "https://www.bls.gov/oes/current/oes151252.htm"
                    ),
                    "median_annual": annual,
                    "fetched_at": datetime.now().isoformat(),
                    "used_fallback": False,
                    "live": True,
                    "reference_version": REFERENCE_TABLES_VERSION,
                })
                return result
        return None

    def _table_rates(self) -> dict[str, Any]:
        """Return the cited reference-table rates (live=False)."""
        mid = HOURLY_RATE_TABLE["mid"]
        return {
            **BLS_FALLBACK_RATES,
            "source": mid["source"] + " (table fallback)",
            "citation": mid["citation"],
            "year": "2023",
            "fetched_at": datetime.now().isoformat(),
            "used_fallback": True,
            "live": False,
            "reference_version": REFERENCE_TABLES_VERSION,
        }

    def fetch_bls_rates(self) -> dict:
        """Fetch loaded hourly rates from BLS (cached), else the table.

        Returns:
            Dictionary with junior/mid/senior rates, source, citation, live
        """
        live = cached_call("bls_oes_15_1252", self._live_bls)
        if live:
            self._rates_cache = live
            return live
        logger.warning("BLS API unavailable, using reference table rates")
        result = self._table_rates()
        self._rates_cache = result
        return result

    def fetch_live_bls_rates(self) -> dict:
        """Alias of fetch_bls_rates (kept for compatibility)."""
        return self.fetch_bls_rates()

    def get_rate(self, role: str) -> float:
        """Get hourly rate for a given role.

        Args:
            role: One of 'junior', 'mid', or 'senior'

        Returns:
            Hourly rate in USD
        """
        rates = self.fetch_bls_rates()
        if role not in LEVEL_RATIOS:
            logger.warning("Unknown role '%s', using 'mid' rate", role)
            role = "mid"
        return rates[role]

    def get_all_rates(self) -> dict:
        """Get all hourly rates.

        Returns:
            Dictionary with all rates and metadata
        """
        return self.fetch_bls_rates()
