"""Cited reference tables (fallbacks) plus shared live-lookup helpers.

Live lookups (BLS, Levels.fyi, Stack Overflow, web search, benchmark pages)
are the default; these tables are the per-source fallback when a lookup
fails. Every number lives here with a value, source, citation, and ``as_of``
date. Update this file (and bump REFERENCE_TABLES_VERSION) when new official
releases are published.

Also provides ``live_cache`` (24h success / 1h failure TTL), ``cached_call``
and ``run_parallel`` (hard wall-clock deadline) used by the live agents.

This module has no project imports so it can be imported from anywhere
(including ``constants``) without circular-import problems.
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Final

logger = logging.getLogger(__name__)

REFERENCE_TABLES_VERSION: Final[str] = "2026.10"

HOURS_PER_YEAR: Final[int] = 2080

# --- Wages -----------------------------------------------------------------

# BLS OES 15-1252 Software Developers, national median annual wage (May 2023).
# verify against latest BLS OES release
# https://www.bls.gov/oes/current/oes151252.htm
BLS_SOFTWARE_DEV_MEDIAN_ANNUAL_USD: Final[float] = 132_270.0

# Base hourly wage = annual / 2080 (full-time hours).
BASE_HOURLY_RATE_USD: Final[float] = round(
    BLS_SOFTWARE_DEV_MEDIAN_ANNUAL_USD / HOURS_PER_YEAR, 2
)

# Loaded (fully burdened) factor: BLS Employer Costs for Employee Compensation,
# total compensation / wages and salaries, private industry (~1.42).
# verify against latest BLS ECEC release
# https://www.bls.gov/news.release/ecec.toc.htm
LOADED_COST_FACTOR: Final[float] = 1.42

# Experience-level ratios relative to the mid (median) developer.
# ASSUMPTION: these are modelling assumptions, not BLS-published figures.
LEVEL_RATIOS: Final[dict[str, float]] = {
    "junior": 0.7,
    "mid": 1.0,
    "senior": 1.4,
}

_WAGE_SOURCE = "BLS OES 15-1252 Software Developers, national median (May 2023)"
_WAGE_CITATION = (
    "U.S. Bureau of Labor Statistics, Occupational Employment and Wage "
    "Statistics, SOC 15-1252 median annual wage $132,270 / 2080 h; loaded "
    "x1.42 per BLS ECEC private-industry compensation/wages ratio; level "
    "ratios 0.7/1.0/1.4 are assumptions. "
    "https://www.bls.gov/oes/current/oes151252.htm"
)


def _build_rates() -> dict[str, dict[str, Any]]:
    """Build the per-level rate table from the base wage inputs."""
    table: dict[str, dict[str, Any]] = {}
    for level, ratio in LEVEL_RATIOS.items():
        base = round(BASE_HOURLY_RATE_USD * ratio, 2)
        table[level] = {
            "value": round(base * LOADED_COST_FACTOR, 2),
            "base_hourly": base,
            "loaded_factor": LOADED_COST_FACTOR,
            "source": _WAGE_SOURCE,
            "citation": _WAGE_CITATION,
            "as_of": "2023-05",
        }
    return table


HOURLY_RATE_TABLE: Final[dict[str, dict[str, Any]]] = _build_rates()

# --- Code-quality benchmark -------------------------------------------------

# ONE value for cost-per-function. Rough industry reference only: it is NOT
# a CISQ-verified figure (CISQ publishes aggregate cost-of-poor-quality
# estimates, not a per-function dollar amount).
COST_PER_FUNCTION_USD: Final[float] = 310.0

BENCHMARK_TABLE: Final[dict[str, dict[str, Any]]] = {
    "cost_per_function_usd": {
        "value": COST_PER_FUNCTION_USD,
        "source": "Rough industry reference (not CISQ-verified)",
        "citation": (
            "Order-of-magnitude estimate of remediation cost per function "
            "derived from CISQ Cost of Poor Software Quality framing "
            "(https://www.it-cisq.org/); CISQ does not publish this exact "
            "per-function figure. Treat as approximate."
        ),
        "as_of": "2022",
    },
    "avg_debt_days": {
        "value": 15.0,
        "source": "Rough SonarQube-style project average (assumption)",
        "citation": "Planning assumption; not a published SonarSource statistic.",
        "as_of": "2026-10",
    },
    "avg_debt_ratio_pct": {
        "value": 10.0,
        "source": "Rough SonarQube-style debt ratio (assumption)",
        "citation": "Planning assumption; not a published SonarSource statistic.",
        "as_of": "2026-10",
    },
}

# --- Security ---------------------------------------------------------------

BREACH_COST_TABLE: Final[dict[str, Any]] = {
    "value": 4_880_000,
    "year": 2024,
    "source": "IBM Cost of a Data Breach Report 2024",
    "citation": (
        "IBM Security / Ponemon Institute, Cost of a Data Breach Report 2024: "
        "global average total cost of a data breach $4.88M. "
        "https://www.ibm.com/reports/data-breach"
    ),
    "as_of": "2024",
}

DBIR_TABLE: Final[dict[str, Any]] = {
    "value": 0.046,
    "source": "Verizon DBIR 2024 (base breach probability, approximate)",
    "citation": (
        "Verizon Data Breach Investigations Report 2024 "
        "(https://www.verizon.com/business/resources/reports/dbir/); the "
        "4.6% annual base rate is an approximation used for risk weighting, "
        "not a figure quoted verbatim by the report."
    ),
    "as_of": "2024",
}

# Multipliers vs. average breach cost (modelling assumptions informed by
# IBM breach-by-attack-vector cost differences).
CWE_BREACH_MULTIPLIERS: Final[dict[str, float]] = {
    "CWE-79": 0.5,
    "CWE-89": 1.5,
    "CWE-22": 1.2,
    "CWE-78": 1.3,
    "CWE-352": 1.1,
    "CWE-287": 1.4,
    "CWE-434": 1.0,
    "CWE-502": 0.9,
    "CWE-915": 0.9,
}


# --- Live-lookup helpers ----------------------------------------------------

SUCCESS_TTL_SECONDS: Final[float] = 24 * 3600
FAILURE_TTL_SECONDS: Final[float] = 3600


class LiveCache:
    """Thread-safe in-process TTL cache storing successes and failures.

    A cached failure is stored as ``None`` with the shorter failure TTL so
    repeat scans do not re-hit a dead endpoint.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value); value is None for a cached failure."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False, None
            expires, value = entry
            if time.monotonic() > expires:
                del self._data[key]
                return False, None
            return True, value

    def set_success(self, key: str, value: Any) -> None:
        """Cache a successful result for SUCCESS_TTL_SECONDS."""
        with self._lock:
            self._data[key] = (time.monotonic() + SUCCESS_TTL_SECONDS, value)

    def set_failure(self, key: str) -> None:
        """Cache a failure marker for FAILURE_TTL_SECONDS."""
        with self._lock:
            self._data[key] = (time.monotonic() + FAILURE_TTL_SECONDS, None)

    def delete(self, key: str) -> None:
        """Remove one entry."""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Drop all entries."""
        with self._lock:
            self._data.clear()


live_cache: Final[LiveCache] = LiveCache()


def cached_call(key: str, producer: Callable[[], Any]) -> Any:
    """Return cached result for key or run producer (None/exception = failure)."""
    hit, value = live_cache.get(key)
    if hit:
        return value
    try:
        value = producer()
    except Exception as exc:  # network/parse errors are expected here
        logger.warning("Live lookup %s failed: %s", key, exc)
        value = None
    if value:
        live_cache.set_success(key, value)
    else:
        live_cache.set_failure(key)
    return value


def run_parallel(
    tasks: dict[str, Callable[[], Any]], timeout: float
) -> dict[str, Any]:
    """Run tasks in parallel with a hard total deadline.

    Returns a result per task; tasks that raise or miss the deadline map to
    None. Stragglers are not waited for.
    """
    if not tasks:
        return {}
    ex = ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="live")
    futs = {k: ex.submit(fn) for k, fn in tasks.items()}
    done, _ = wait(list(futs.values()), timeout=timeout)
    ex.shutdown(wait=False, cancel_futures=True)
    out: dict[str, Any] = {}
    for key, fut in futs.items():
        if fut in done:
            try:
                out[key] = fut.result()
            except Exception as exc:
                logger.warning("Task %s failed: %s", key, exc)
                out[key] = None
        else:
            logger.warning("Task %s exceeded %.1fs time box", key, timeout)
            out[key] = None
    return out
