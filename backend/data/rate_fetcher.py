"""Rate fetcher for engineer hourly rates.

Fetches real rates from BLS public API with caching.
Falls back to BLS OES May 2023 published values if API unavailable.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from constants import CACHE_STALE_HOURS, HOURLY_RATES

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "rates_cache.json"

BLS_FALLBACK_RATES = {
    "junior": 55.10,
    "mid": 84.55,
    "senior": 128.37,
}

BLS_SERIES_IDS = [
    "OEUN0000000152064000008",
    "OEUS0000000152064000008",
    "CES0500000003",
]


class RateFetcher:
    """Fetches engineer hourly rates from BLS API with caching.
    
    Uses BLS OES May 2023 published data as fallback when API is unavailable.
    Caches results for 24 hours to avoid excessive API calls.
    """

    def __init__(self) -> None:
        self._rates_cache: dict | None = None

    def _is_cache_fresh(self, cached_data: dict) -> bool:
        """Check if cached data is less than CACHE_STALE_HOURS old."""
        if "fetched_at" not in cached_data:
            return False
        fetched_at = datetime.fromisoformat(cached_data["fetched_at"])
        age_hours = (datetime.now() - fetched_at).total_seconds() / 3600
        return age_hours < CACHE_STALE_HOURS

    def _load_cache(self) -> dict | None:
        """Load rates from cache file if it exists."""
        if not CACHE_FILE.exists():
            return None
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load rates cache: {e}")
            return None

    def _save_cache(self, data: dict) -> None:
        """Save rates to cache file."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.warning(f"Failed to save rates cache: {e}")

    def _fetch_from_bls(self, series_id: str) -> float | None:
        """Fetch rate from BLS API for given series ID."""
        url = f"https://api.bls.gov/publicAPI/v1/timeseries/data/{series_id}"
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(url)
                if response.status_code != 200:
                    logger.warning(f"BLS API returned status {response.status_code}")
                    return None
                data = response.json()
                if data.get("status") != "REQUEST_SUCCEEDED":
                    logger.warning(f"BLS API error: {data.get('message')}")
                    return None
                series_data = data.get("Results", {}).get("series", [])
                if not series_data:
                    return None
                observations = series_data[0].get("data", [])
                if not observations:
                    return None
                latest = observations[0].get("value")
                if latest:
                    return float(latest)
                return None
        except httpx.TimeoutException:
            logger.warning(f"BLS API timeout for series {series_id}")
            return None
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
            logger.warning(f"BLS API error for series {series_id}: {e}")
            return None

    def fetch_bls_rates(self) -> dict:
        """Fetch engineer hourly rates from BLS API.
        
        Tries multiple BLS series IDs until one works.
        Falls back to cached or hardcoded values on failure.
        
        Returns:
            Dictionary with junior/mid/senior rates and metadata
        """
        cached = self._load_cache()
        if cached and self._is_cache_fresh(cached):
            logger.info("Using cached BLS rates (fresh)")
            return cached

        for series_id in BLS_SERIES_IDS:
            rate = self._fetch_from_bls(series_id)
            if rate and rate > 0:
                hourly_wage = float(rate)
                result = {
                    "junior": round(hourly_wage * 0.7, 2),
                    "mid": round(hourly_wage, 2),
                    "senior": round(hourly_wage * 1.5, 2),
                    "source": f"BLS API (series: {series_id})",
                    "fetched_at": datetime.now().isoformat(),
                    "used_fallback": False,
                }
                logger.info("Using live BLS API rates")
                self._save_cache(result)
                self._rates_cache = result
                return result

        logger.warning("BLS API unavailable, using fallback rates")
        result = {
            "junior": BLS_FALLBACK_RATES["junior"],
            "mid": BLS_FALLBACK_RATES["mid"],
            "senior": BLS_FALLBACK_RATES["senior"],
            "source": "BLS OES May 2023 published (fallback)",
            "fetched_at": datetime.now().isoformat(),
            "used_fallback": True,
        }
        self._save_cache(result)
        self._rates_cache = result
        return result

    def get_rate(self, role: str) -> float:
        """Get hourly rate for a given role.
        
        Args:
            role: One of 'junior', 'mid', or 'senior'
            
        Returns:
            Hourly rate in USD
        """
        rates = self.fetch_bls_rates()
        if role not in rates:
            logger.warning(f"Unknown role '{role}', using 'mid' rate")
            role = "mid"
        return rates[role]

    def get_all_rates(self) -> dict:
        """Get all hourly rates.
        
        Returns:
            Dictionary with all rates and metadata
        """
        return self.fetch_bls_rates()
