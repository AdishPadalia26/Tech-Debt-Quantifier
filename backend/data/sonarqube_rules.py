"""SonarQube rules fetcher for remediation time estimates.

Fetches rule metadata from SonarCloud public API with caching.
Uses fallback values based on SonarQube's public rule database when API is unavailable.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from constants import (
    CACHE_STALE_HOURS,
    COMPLEXITY_TO_SONAR_SEVERITY,
    SONAR_CACHE_STALE_DAYS,
    SONAR_SEVERITY_MINUTES,
)

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "sonar_rules_cache.json"

SONARCLOUD_API_TOKEN = "2091f4b0274f100838cd9379ed0f63d963be0c62"

SONARCLOUD_ORG = "sonarsource"

SONARCLOUD_API_URLS = [
    "https://sonarcloud.io/api/rules/search?languages=py&ps=500&types=CODE_SMELL,BUG,VULNERABILITY&f=defaultRemFn,severity&organization=" + SONARCLOUD_ORG,
]


class SonarQubeRules:
    """Fetches SonarQube rule metadata with caching.
    
    Provides remediation time estimates based on SonarCloud rule data.
    Caches results for 7 days to avoid excessive API calls.
    """

    def __init__(self) -> None:
        self._rules_cache: dict | None = None

    def _is_cache_fresh(self, cached_data: dict) -> bool:
        """Check if cached data is less than SONAR_CACHE_STALE_DAYS old."""
        if "fetched_at" not in cached_data:
            return False
        fetched_at = datetime.fromisoformat(cached_data["fetched_at"])
        age_days = (datetime.now() - fetched_at).total_seconds() / 86400
        return age_days < SONAR_CACHE_STALE_DAYS

    def _load_cache(self) -> dict | None:
        """Load rules from cache file if it exists."""
        if not CACHE_FILE.exists():
            return None
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load sonar rules cache: {e}")
            return None

    def _save_cache(self, data: dict) -> None:
        """Save rules to cache file."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.warning(f"Failed to save sonar rules cache: {e}")

    def _parse_effort(self, effort_str: str | None) -> int:
        """Parse SonarQube effort string to minutes.
        
        Args:
            effort_str: Effort string like '10min', '2h', '1d'
            
        Returns:
            Minutes as integer
        """
        if not effort_str:
            return SONAR_SEVERITY_MINUTES["MAJOR"]

        effort_str = effort_str.strip().lower()

        min_match = re.search(r"(\d+)\s*min", effort_str)
        if min_match:
            return int(min_match.group(1))

        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*h", effort_str)
        if hour_match:
            return int(float(hour_match.group(1)) * 60)

        day_match = re.search(r"(\d+(?:\.\d+)?)\s*d", effort_str)
        if day_match:
            return int(float(day_match.group(1)) * 480)

        return SONAR_SEVERITY_MINUTES["MAJOR"]

    def fetch_rules(self) -> dict:
        """Fetch SonarQube rules from SonarCloud API.
        
        Tries multiple API URLs until one works.
        
        Returns:
            Dictionary mapping rule keys to rule metadata
        """
        cached = self._load_cache()
        if cached and self._is_cache_fresh(cached):
            logger.info("Using cached SonarQube rules (fresh)")
            return cached

        rules = {}
        successful_url = None
        successful_url_idx = 0
        
        for url_idx, api_url in enumerate(SONARCLOUD_API_URLS):
            try:
                with httpx.Client(timeout=10) as client:
                    logger.info(f"[SONAR API] Trying URL {url_idx + 1}/{len(SONARCLOUD_API_URLS)}")
                    response = client.get(
                        api_url,
                        auth=(SONARCLOUD_API_TOKEN, "")
                    )
                    
                    if response.status_code != 200:
                        logger.warning(
                            f"[SONAR API] URL {url_idx + 1} returned HTTP {response.status_code}"
                        )
                        continue  # Try next URL

                    data = response.json()
                    if "rules" not in data:
                        logger.warning(f"[SONAR API] URL {url_idx + 1} returned invalid response")
                        continue  # Try next URL

                    for rule in data.get("rules", []):
                        key = rule.get("key", "")
                        effort = rule.get("defaultRemFnBaseEffort") or rule.get("defaultRemFn")
                        severity = rule.get("severity", "MAJOR")
                        rule_type = rule.get("type", "CODE_SMELL")

                        rules[key] = {
                            "minutes": self._parse_effort(effort),
                            "severity": severity,
                            "type": rule_type,
                        }

                    successful_url = api_url
                    successful_url_idx = url_idx + 1
                    break  # Success!

            except httpx.TimeoutException:
                logger.warning(f"[SONAR API] URL {url_idx + 1} timeout")
                continue
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                logger.warning(f"[SONAR API] URL {url_idx + 1} error: {e}")
                continue

        if successful_url:
            result = {
                "rules": rules,
                "source": "SonarCloud API",
                "api_url_index": successful_url_idx,
                "fetched_at": datetime.now().isoformat(),
                "used_fallback": False,
                "count": len(rules),
            }
            logger.info(f"[SONAR API] Success! Loaded {len(rules)} rules from URL {successful_url_idx}")
            self._save_cache(result)
            self._rules_cache = result
            return result
        
        logger.warning("[SONAR API] All URLs failed, using fallback values")
        return self._get_fallback_rules()

    def _get_fallback_rules(self) -> dict:
        """Return fallback rules based on severity averages."""
        return {
            "rules": {},
            "source": "Fallback (severity averages)",
            "fetched_at": datetime.now().isoformat(),
            "used_fallback": True,
            "count": 0,
        }

    def get_minutes_for_complexity(
        self, complexity_severity: str
    ) -> float:
        """Get average remediation minutes for a complexity severity level.
        
        Args:
            complexity_severity: One of 'low', 'medium', 'high', 'critical'
            
        Returns:
            Average remediation minutes
        """
        sonar_severity = COMPLEXITY_TO_SONAR_SEVERITY.get(
            complexity_severity, "MAJOR"
        )

        rules_data = self.fetch_rules()
        rules = rules_data.get("rules", {})

        code_smell_rules = [
            r for r in rules.values() if r.get("type") == "CODE_SMELL"
        ]

        severity_rules = [
            r["minutes"]
            for r in code_smell_rules
            if r.get("severity") == sonar_severity
        ]

        if severity_rules:
            return float(sum(severity_rules) / len(severity_rules))

        return float(SONAR_SEVERITY_MINUTES.get(sonar_severity, 30))

    def get_rule_minutes(self, rule_key: str) -> float:
        """Get remediation minutes for a specific rule.
        
        Args:
            rule_key: SonarQube rule identifier
            
        Returns:
            Remediation minutes
        """
        rules_data = self.fetch_rules()
        rules = rules_data.get("rules", {})

        if rule_key in rules:
            return float(rules[rule_key]["minutes"])

        return float(SONAR_SEVERITY_MINUTES["MAJOR"])
