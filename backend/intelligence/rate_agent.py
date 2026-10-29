"""Rate Intelligence Agent - live, cited hourly engineer rates.

``blend_rates`` queries four sources in parallel under a hard time box:
- BLS API, OES 15-1252 Software Developers (weighted .40, loaded rate)
- Levels.fyi (.30, total compensation)
- Stack Overflow Developer Survey (.20, from a disk-cached zip only)
- DuckDuckGo snippets (.10)

Each source that fails falls back (per source) to the cited table in
``data.reference_tables`` and is excluded from the weighted blend. If no
source is live the table rate is returned with ``live: False``. Successes
are cached 24h, failures 1h. ENGINEER_HOURLY_RATE is used only when no live source succeeds.
"""

import csv
import io
import logging
import os
import re
import statistics
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from data.reference_tables import (
    HOURLY_RATE_TABLE,
    HOURS_PER_YEAR,
    LEVEL_RATIOS,
    REFERENCE_TABLES_VERSION,
    cached_call,
    live_cache,
    run_parallel,
)

logger = logging.getLogger(__name__)

FALLBACK_RATES = {level: e["value"] for level, e in HOURLY_RATE_TABLE.items()}

WEIGHTS = {
    "bls": 0.40,
    "levels": 0.30,
    "so": 0.20,
    "ddg": 0.10,
}

RATE_TIME_BOX_SECONDS = 8.0
REQUEST_TIMEOUT_SECONDS = 5.0

SO_ZIP_URL = (
    "https://survey.stackoverflow.co/datasets/"
    "stack-overflow-developer-survey-2024.zip"
)
SO_ZIP_PATH = Path(__file__).parent.parent / "data" / "cache" / "so_survey_2024.zip"
SO_MAX_ROWS = 60_000
# Download the survey zip to disk in the background when it is missing.
SO_BACKGROUND_DOWNLOAD = True
_so_download_lock = threading.Lock()
_so_download_started = False

LEVELS_URL = "https://www.levels.fyi/js/salaryData.json"

SOURCE_LABELS = {
    "bls": "BLS OES 15-1252",
    "levels": "Levels.fyi",
    "so": "Stack Overflow Survey 2024",
    "ddg": "DuckDuckGo",
}


def _levels_from_mid(mid_hourly: float) -> dict[str, float]:
    """Scale a mid-level hourly figure to junior/mid/senior via LEVEL_RATIOS."""
    return {k: round(mid_hourly * r, 2) for k, r in LEVEL_RATIOS.items()}


def _table_fallback(key: str, reason: str = "lookup failed") -> dict[str, Any]:
    """Cited table rates for a failed source (live=False)."""
    mid = HOURLY_RATE_TABLE["mid"]
    return {
        **FALLBACK_RATES,
        "source": f"{mid['source']} (table fallback: {SOURCE_LABELS[key]} {reason})",
        "citation": mid["citation"],
        "fetched_at": datetime.now().isoformat(),
        "live": False,
    }


class RateIntelligenceAgent:
    """Live rate intelligence with per-source cited fallbacks."""

    # ------------------------------------------------------------------ BLS
    def fetch_bls_rate(self) -> dict[str, Any]:
        """Fetch BLS OES 15-1252 loaded rates (cached; table on failure)."""
        from data.rate_fetcher import RateFetcher

        data = RateFetcher().fetch_bls_rates()
        return {
            "junior": data.get("junior", FALLBACK_RATES["junior"]),
            "mid": data.get("mid", FALLBACK_RATES["mid"]),
            "senior": data.get("senior", FALLBACK_RATES["senior"]),
            "source": data.get("source", "BLS OES"),
            "citation": data.get("citation", ""),
            "live": bool(data.get("live", False)),
            "fetched_at": data.get("fetched_at"),
        }

    # ------------------------------------------------------------- Levels
    def _live_levels(self, technology: str) -> dict[str, Any] | None:
        """Download Levels.fyi data and compute median rates, or None."""
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = client.get(LEVELS_URL)
                response.raise_for_status()
                salaries = response.json()
        except Exception:
            live_cache.set_failure("levels_http_fail")
            raise
        tech = technology.lower()
        comps = [
            float(s["totalyearlycompensation"])
            for s in salaries
            if float(s.get("totalyearlycompensation", 0) or 0) > 0
            and (
                tech in str(s.get("title", "")).lower()
                or tech in str(s.get("companyName", "")).lower()
            )
        ]
        if not comps:
            return None
        median_annual = statistics.median(comps)
        return {
            **_levels_from_mid(median_annual / HOURS_PER_YEAR),
            "median_annual": median_annual,
            "sample_size": len(comps),
            "technology": technology,
            "source": "Levels.fyi",
            "citation": (
                f"Levels.fyi salaryData.json: median total comp "
                f"${median_annual:,.0f} for '{technology}' (n={len(comps)}) "
                f"/ {HOURS_PER_YEAR} h"
            ),
            "fetched_at": datetime.now().isoformat(),
            "live": True,
        }

    def fetch_levels_fyi(self, technology: str = "Python") -> dict[str, Any]:
        """Fetch Levels.fyi rates for a technology (cached; table on failure)."""
        # A dead endpoint is cached once, not once per technology.
        hit, _ = live_cache.get("levels_http_fail")
        if hit:
            return _table_fallback("levels")
        key = f"levels:{technology.lower()}"
        result = cached_call(key, lambda: self._live_levels(technology))
        return result or _table_fallback("levels")

    # ------------------------------------------------------ Stack Overflow
    @staticmethod
    def _parse_years(raw: str) -> float | None:
        """Parse the survey's YearsCodePro value."""
        raw = (raw or "").strip()
        if not raw or raw == "NA":
            return None
        if raw.startswith("Less than"):
            return 0.5
        if raw.startswith("More than"):
            return 51.0
        try:
            return float(raw)
        except ValueError:
            return None

    def _parse_so_zip(self, path: Path) -> dict[str, Any] | None:
        """Parse the survey zip: median US comp per experience band."""
        with zipfile.ZipFile(path) as zf:
            name = next(
                n for n in zf.namelist()
                if "survey_results" in n and n.endswith(".csv")
            )
            with zf.open(name) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
                bands: dict[str, list[float]] = {k: [] for k in LEVEL_RATIOS}
                total = 0
                for i, row in enumerate(reader):
                    if i >= SO_MAX_ROWS:
                        break
                    if row.get("Country") != "United States of America":
                        continue
                    try:
                        comp = float(row.get("ConvertedCompYearly") or 0)
                    except ValueError:
                        continue
                    years = self._parse_years(row.get("YearsCodePro", ""))
                    if years is None or not 0 < comp < 1_000_000:
                        continue
                    band = "junior" if years < 3 else "mid" if years < 8 else "senior"
                    bands[band].append(comp)
                    total += 1
        if total < 50 or not all(bands.values()):
            return None
        rates = {k: round(statistics.median(v) / HOURS_PER_YEAR, 2) for k, v in bands.items()}
        return {
            **rates,
            "sample_size": total,
            "source": "Stack Overflow Developer Survey 2024",
            "citation": (
                f"Stack Overflow Developer Survey 2024, US respondents "
                f"(n={total}, first {SO_MAX_ROWS} rows), median "
                "ConvertedCompYearly / 2080 h by YearsCodePro band. "
                "https://survey.stackoverflow.co/"
            ),
            "fetched_at": datetime.now().isoformat(),
            "live": True,
        }

    def _download_so_zip(self) -> None:
        """Background: download the survey zip to disk once."""
        try:
            SO_ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = SO_ZIP_PATH.with_suffix(".part")
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                response = client.get(SO_ZIP_URL)
                response.raise_for_status()
                tmp.write_bytes(response.content)
            tmp.replace(SO_ZIP_PATH)
            live_cache.delete("so_survey")
            logger.info("Stack Overflow survey zip cached to %s", SO_ZIP_PATH)
        except Exception as exc:
            logger.warning("SO survey background download failed: %s", exc)

    def _live_so(self) -> dict[str, Any] | None:
        """Use the on-disk survey zip, or start a background download."""
        global _so_download_started
        if SO_ZIP_PATH.exists():
            return self._parse_so_zip(SO_ZIP_PATH)
        if SO_BACKGROUND_DOWNLOAD:
            with _so_download_lock:
                if not _so_download_started:
                    _so_download_started = True
                    threading.Thread(target=self._download_so_zip, daemon=True).start()
        logger.info("SO survey zip not cached yet; skipping this scan")
        return None

    def fetch_stackoverflow_rates(self) -> dict[str, Any]:
        """Stack Overflow survey rates from the disk-cached zip (else table)."""
        result = cached_call("so_survey", self._live_so)
        return result or _table_fallback("so")

    # ---------------------------------------------------------------- DDG
    _DDG_PATTERNS = (
        (re.compile(r"\$(\d+(?:\.\d+)?)\s*(?:per hour|/\s*hr|/\s*hour|hourly)", re.I), "hour"),
        (re.compile(r"\$(\d{2,3}(?:,\d{3})+)\s*(?:per year|annual|a year|/\s*yr)", re.I), "year"),
        (re.compile(r"\$(\d{2,3})\s*[kK]\s*(?:per year|annual|a year|/\s*yr)", re.I), "yearK"),
    )

    def _live_ddg(self, technology: str) -> dict[str, Any] | None:
        """Search DuckDuckGo snippets for hourly/annual pay figures."""
        query = f"{technology} engineer average hourly rate salary"
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
        except Exception:
            live_cache.set_failure("ddg_fail")
            raise
        figures: list[float] = []
        urls: list[str] = []
        for r in results:
            snippet = r.get("body", "")
            urls.append(r.get("href", ""))
            for pattern, kind in self._DDG_PATTERNS:
                for m in pattern.findall(snippet):
                    value = float(m.replace(",", ""))
                    if kind == "year":
                        value /= HOURS_PER_YEAR
                    elif kind == "yearK":
                        value = value * 1000 / HOURS_PER_YEAR
                    if 20 <= value <= 300:
                        figures.append(value)
        if not figures:
            return None
        median_rate = statistics.median(figures)
        return {
            **_levels_from_mid(median_rate),
            "rate": median_rate,
            "figures_found": len(figures),
            "sources": urls[:3],
            "technology": technology,
            "source": "DuckDuckGo Search",
            "citation": (
                f"Median of {len(figures)} pay figures in web search snippets "
                f"for '{query}': {', '.join(u for u in urls[:3] if u)}"
            ),
            "fetched_at": datetime.now().isoformat(),
            "live": True,
        }

    def search_ddg_salary(self, technology: str) -> dict[str, Any]:
        """Web-search salary figures for a technology (cached; table on failure)."""
        hit, _ = live_cache.get("ddg_fail")
        if hit:
            return {**_table_fallback("ddg"), "rate": FALLBACK_RATES["mid"]}
        result = cached_call(
            f"ddg:{technology.lower()}", lambda: self._live_ddg(technology)
        )
        return result or {**_table_fallback("ddg"), "rate": FALLBACK_RATES["mid"]}

    # -------------------------------------------------------------- blend
    @staticmethod
    def _engineer_rate_fallback() -> float | None:
        """Read ENGINEER_HOURLY_RATE (fallback when all live sources fail); float if > 0."""
        raw = os.getenv("ENGINEER_HOURLY_RATE", "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            logger.warning("Ignoring invalid ENGINEER_HOURLY_RATE=%r", raw)
            return None
        return value if value > 0 else None

    def blend_rates(self, technology: str = "Python", role: str = "mid") -> dict[str, Any]:
        """Blend live rates from all sources under a hard time box.

        Failed or timed-out sources use the cited table value, are marked
        live=False and get zero effective weight. The blend is a weighted
        average over live sources only; with none live the table rate is used.

        Args:
            technology: Technology to search for
            role: Experience level (junior/mid/senior)

        Returns:
            Rate result with per-source {value, live, source, citation,
            fetched_at}, sources_used, live_sources, reference_version
        """
        if role not in LEVEL_RATIOS:
            logger.warning("Unknown role %r, using mid", role)
            role = "mid"
        entry = HOURLY_RATE_TABLE[role]

        raw = run_parallel(
            {
                "bls": self.fetch_bls_rate,
                "levels": lambda: self.fetch_levels_fyi(technology),
                "so": self.fetch_stackoverflow_rates,
                "ddg": lambda: self.search_ddg_salary(technology),
            },
            RATE_TIME_BOX_SECONDS,
        )

        breakdown: dict[str, dict[str, Any]] = {}
        live_weight = 0.0
        for key, weight in WEIGHTS.items():
            data = raw.get(key)
            if not data:
                data = _table_fallback(key, "timed out")
            live = bool(data.get("live", False))
            value = float(data.get(role, FALLBACK_RATES[role]))
            breakdown[key] = {
                "rate": round(value, 2),
                "value": round(value, 2),
                "weight": weight,
                "effective_weight": 0.0,
                "live": live,
                "source": data.get("source", SOURCE_LABELS[key]),
                "citation": data.get("citation", ""),
                "fetched_at": data.get("fetched_at"),
            }
            if live:
                live_weight += weight

        live_sources = sum(1 for b in breakdown.values() if b["live"])
        if live_weight > 0:
            blended = 0.0
            for b in breakdown.values():
                if b["live"]:
                    b["effective_weight"] = round(b["weight"] / live_weight, 4)
                    blended += b["value"] * b["effective_weight"]
            live_names = ", ".join(
                SOURCE_LABELS[k] for k, b in breakdown.items() if b["live"]
            )
            source = f"Live blend: {live_names}"
            citation = "; ".join(
                f"{SOURCE_LABELS[k]}: {b['citation']}"
                for k, b in breakdown.items() if b["live"]
            )
        elif (env_rate := self._engineer_rate_fallback()) is not None:
            ratio = entry["value"] / HOURLY_RATE_TABLE["mid"]["value"]
            blended = env_rate * ratio
            logger.warning(
                "No live rate sources succeeded; using ENGINEER_HOURLY_RATE fallback"
            )
            source = "env_fallback"
            citation = (
                f"ENGINEER_HOURLY_RATE=${env_rate:.2f}/h (mid) from .env, used "
                f"because no live source succeeded; level ratio {ratio:.2f} applied"
            )
        else:
            logger.warning(
                "No live rate sources succeeded; using cited reference table"
            )
            blended = float(entry["value"])
            source = entry["source"] + " (table fallback)"
            citation = entry["citation"]

        confidence = "high" if live_sources >= 3 else "medium" if live_sources >= 2 else "low"
        return self._result(
            technology, role, round(blended, 2), confidence, source, citation,
            breakdown, live_sources=live_sources, sources_used=live_sources,
            live=live_sources > 0,
        )

    @staticmethod
    def _result(
        technology: str,
        role: str,
        rate: float,
        confidence: str,
        source: str,
        citation: str,
        breakdown: dict[str, dict[str, Any]],
        *,
        live_sources: int,
        sources_used: int,
        live: bool,
    ) -> dict[str, Any]:
        """Assemble the blend_rates result dict."""
        return {
            "technology": technology,
            "role": role,
            "blended_rate": rate,
            "confidence": confidence,
            "sources_used": sources_used,
            "live_sources": live_sources,
            "breakdown": breakdown,
            "citations": [
                f"{k}: {b['rate']:.2f}/hr ({'live' if b['live'] else 'table'})"
                for k, b in breakdown.items()
            ],
            "cached_until": "24h success / 1h failure",
            "source": source,
            "citation": citation,
            "live": live,
            "reference_version": REFERENCE_TABLES_VERSION,
        }

    def get_rate(self, technology: str = "Python", role: str = "mid") -> float:
        """Simple wrapper returning just the blended rate."""
        return self.blend_rates(technology, role)["blended_rate"]

    def get_all_rates(self, technology: str = "Python") -> dict[str, Any]:
        """Get blended rates for all experience levels."""
        return {
            "junior": self.get_rate(technology, "junior"),
            "mid": self.get_rate(technology, "mid"),
            "senior": self.get_rate(technology, "senior"),
        }


def get_rate(technology: str = "Python", role: str = "mid") -> float:
    """Convenience function for getting a single rate."""
    return RateIntelligenceAgent().get_rate(technology, role)
