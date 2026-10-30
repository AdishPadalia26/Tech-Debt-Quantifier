"""Security Cost Agent - live breach cost, cited fallbacks.

The IBM Cost of a Data Breach average is looked up via web search snippets
under a hard time box, fetched once per agent (scan) and cached 24h on
success / 1h on failure. Search backends are tried in order until one yields
a strict match; anything that does not match falls back to the cited table.

The base breach probability always comes from the cited DBIR-derived table:
Verizon's DBIR does not publish a "probability of breach" percentage, so
there is nothing to look up live.
"""

import logging
import re
import statistics
from datetime import datetime
from typing import Any

from data.reference_tables import (
    BREACH_COST_TABLE,
    CWE_BREACH_MULTIPLIERS,
    DBIR_TABLE,
    REFERENCE_TABLES_VERSION,
    cached_call,
    run_parallel,
)

logger = logging.getLogger(__name__)

IBM_BREACH_COST_FALLBACK = BREACH_COST_TABLE["value"]
IBM_BREACH_YEAR = BREACH_COST_TABLE["year"]
DBIR_BASE_RATE = DBIR_TABLE["value"]

# CVSS score at or above which expected breach value is added.
BREACH_CVSS_THRESHOLD = 7.0

SECURITY_TIME_BOX_SECONDS = 10.0

# Tried in order. "auto" mixes backends at random and several (google, mojeek,
# yahoo, brave) return nothing for these queries, which made lookups flaky.
SEARCH_BACKENDS = ("duckduckgo", "bing", "yandex")

# Sane range for an average total breach cost, in USD.
MIN_BREACH_COST = 2_000_000
MAX_BREACH_COST = 15_000_000

_BREACH_COST_RE = re.compile(
    r"(?:cost of a data breach|data breach cost|average (?:total )?cost)"
    r"[^.$]{0,100}(?:\$|USD)\s*(\d+(?:\.\d+)?)\s*(?:million|M)\b",
    re.IGNORECASE,
)


def parse_breach_cost(text: str) -> float | None:
    """Strictly extract an average breach cost (USD) from snippet text."""
    values = [
        float(m) * 1_000_000
        for m in _BREACH_COST_RE.findall(text)
        if MIN_BREACH_COST <= float(m) * 1_000_000 <= MAX_BREACH_COST
    ]
    return statistics.median(values) if values else None


def _search_snippets(query: str, backend: str) -> tuple[str, list[str]]:
    """Run a web search on one backend; return (snippet text, result URLs)."""
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5, backend=backend))
    text = " ".join(r.get("body", "") for r in results)
    return text, [r.get("href", "") for r in results if r.get("href")]


class SecurityCostAgent:
    """Security cost calculation using live breach data with cited fallbacks."""

    def __init__(self) -> None:
        self._reference: dict[str, dict[str, Any]] | None = None

    def _live_breach(self) -> dict[str, Any] | None:
        """Look up the IBM average breach cost; None if no backend matches."""
        query = "IBM Cost of a Data Breach Report global average total cost"
        for backend in SEARCH_BACKENDS:
            try:
                text, urls = _search_snippets(query, backend)
            except Exception as exc:  # no results / blocked: try the next one
                logger.debug("Breach search on %s failed: %s", backend, exc)
                continue
            cost = parse_breach_cost(text)
            if cost is None:
                continue
            return {
                "average_breach_cost": cost,
                "year": datetime.now().year,
                "source": f"IBM Cost of a Data Breach Report (web search, {backend})",
                "citation": (
                    f"Search snippets matched ${cost/1e6:.2f}M: {', '.join(urls[:3])}"
                ),
                "url": "https://www.ibm.com/reports/data-breach",
                "live": True,
                "fetched_at": datetime.now().isoformat(),
            }
        return None

    def _load_reference(self) -> dict[str, dict[str, Any]]:
        """Fetch breach data once per agent, time-boxed; DBIR from the table."""
        if self._reference is not None:
            return self._reference
        raw = run_parallel(
            {"breach": lambda: cached_call("ibm_breach", self._live_breach)},
            SECURITY_TIME_BOX_SECONDS,
        )
        now = datetime.now().isoformat()
        breach = raw.get("breach") or {
            "average_breach_cost": BREACH_COST_TABLE["value"],
            "year": BREACH_COST_TABLE["year"],
            "source": BREACH_COST_TABLE["source"],
            "citation": BREACH_COST_TABLE["citation"],
            "url": "https://www.ibm.com/reports/data-breach",
            "live": False,
            "fetched_at": now,
        }
        dbir = {
            "base_breach_probability": DBIR_TABLE["value"],
            "source": DBIR_TABLE["source"],
            "citation": DBIR_TABLE["citation"],
            "live": False,
            "fetched_at": now,
        }
        if not breach["live"]:
            logger.warning("No live breach cost found; using cited reference table")
        self._reference = {"breach": breach, "dbir": dbir}
        return self._reference

    def fetch_latest_breach_costs(self) -> dict[str, Any]:
        """Return average breach cost (live if found, else IBM 2024 table)."""
        return self._load_reference()["breach"]

    def fetch_dbir_probability(self) -> dict[str, Any]:
        """Return base breach probability (cited table; not published live)."""
        return self._load_reference()["dbir"]

    def _get_cwe_breach_cost(self, cwe_id: str | None) -> float:
        """Get breach cost specific to a CWE type.

        Args:
            cwe_id: CWE identifier (None/unknown uses multiplier 1.0)

        Returns:
            Breach cost for this vulnerability type
        """
        base_cost = self.fetch_latest_breach_costs()["average_breach_cost"]
        multiplier = CWE_BREACH_MULTIPLIERS.get(cwe_id or "", 1.0)
        return base_cost * multiplier

    def get_risk_weighted_cost(
        self,
        cwe_id: str | None,
        cvss_score: float,
        fix_hours: float,
        hourly_rate: float,
    ) -> dict[str, Any]:
        """Calculate risk-weighted security cost.

        Expected breach value is added for cvss_score >= 7.0, with probability
        scaled by the real CVSS score (cvss/10) and the CWE multiplier.

        Args:
            cwe_id: CWE identifier (optional; None uses multiplier 1.0)
            cvss_score: CVSS severity score (0-10)
            fix_hours: Hours to fix the vulnerability
            hourly_rate: Developer hourly rate

        Returns:
            Complete security cost breakdown
        """
        breach_data = self.fetch_latest_breach_costs()
        dbir_data = self.fetch_dbir_probability()

        fix_cost = fix_hours * hourly_rate
        breach_prob = 0.0
        breach_cost = 0.0
        expected_breach_value = 0.0

        if cvss_score >= BREACH_CVSS_THRESHOLD:
            breach_cost = self._get_cwe_breach_cost(cwe_id)
            breach_prob = dbir_data["base_breach_probability"] * (cvss_score / 10.0)
            expected_breach_value = breach_prob * breach_cost * 0.01
        total_security_cost = fix_cost + expected_breach_value

        return {
            "fix_cost": round(fix_cost, 2),
            "expected_breach_value": round(expected_breach_value, 2),
            "breach_probability_pct": round(breach_prob * 100, 2),
            "breach_cost_used": round(breach_cost, 2),
            "total_security_cost": round(total_security_cost, 2),
            "cvss_score": cvss_score,
            "cwe_id": cwe_id,
            "fix_hours": fix_hours,
            "hourly_rate": hourly_rate,
            "sources": [
                f"IBM: ${breach_data['average_breach_cost']:,.0f} ({breach_data['year']})",
                f"DBIR: {dbir_data['base_breach_probability']*100:.1f}% base rate",
            ],
            "data_fresh": bool(breach_data["live"] and dbir_data["live"]),
            "citations": [breach_data["citation"], dbir_data["citation"]],
            "reference_version": REFERENCE_TABLES_VERSION,
            "live": bool(breach_data["live"] or dbir_data["live"]),
            "live_sources": int(breach_data["live"]) + int(dbir_data["live"]),
            "sources_used": int(breach_data["live"]) + int(dbir_data["live"]),
            "source_details": {
                "breach_cost": {
                    "value": breach_data["average_breach_cost"],
                    "live": breach_data["live"],
                    "source": breach_data["source"],
                    "citation": breach_data["citation"],
                    "fetched_at": breach_data["fetched_at"],
                },
                "breach_probability": {
                    "value": dbir_data["base_breach_probability"],
                    "live": dbir_data["live"],
                    "source": dbir_data["source"],
                    "citation": dbir_data["citation"],
                    "fetched_at": dbir_data["fetched_at"],
                },
            },
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
