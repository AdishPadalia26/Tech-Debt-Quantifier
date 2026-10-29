"""Multi-provider LLM pool for fast, resilient debt-item estimation.

``LLMPool`` fans batches of debt items out across several OpenAI-compatible
providers (NVIDIA NIM, Groq, OpenRouter, ...) at once:

* One ``LLMEstimator`` per provider, N worker threads per provider.
* Items are pinned to a provider by a stable hash (reproducible results while
  every provider is healthy); an idle provider steals other providers' queued
  batches so speed wins over strict pinning.
* 429 -> provider cools down (``retry-after`` honoured, else exponential
  backoff 5 s .. 60 s) and the batch moves to another provider. Timeout ->
  batch is split in half and requeued. Other errors -> requeued to another
  provider. A provider failing repeatedly in a row is disabled for the scan.
* Items fall back to category defaults only when attempts are exhausted, every
  provider is disabled/cooling, or the pool time box expires.
* Successful estimates are cached in sqlite (``data/cache/llm_estimates.db``).

One pool instance == one scan: ``estimate_items`` resets cooldown/disabled
state at the start of every call.
"""

import concurrent.futures
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

import app_config as config
from tools.llm_estimator import LLMEstimator

logger = logging.getLogger(__name__)

PROMPT_VERSION = "batch-v1"
DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "cache" / "llm_estimates.db"
)
CONSECUTIVE_FAILURE_LIMIT = 5
BACKOFF_BASE_SECONDS = 5.0
BACKOFF_CAP_SECONDS = 60.0
RETRY_AFTER_CAP_SECONDS = 120.0
RATE_LIMIT_REQUEUE_FACTOR = 3  # rate-limit requeues allowed = factor * max_attempts
_IDLE_WAIT_SECONDS = 0.25

_SECRET_RE = re.compile(r"(?:nvapi-|gsk_|sk-or-v1-|sk-)[A-Za-z0-9_\-\.]{8,}")
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_RETRY_MSG_RE = re.compile(r"try again in\s+((?:\d+(?:\.\d+)?(?:ms|h|m|s)\s*)+)", re.I)
_RETRY_AFTER_MSG_RE = re.compile(r"retry[- ]after:?\s*(\d+(?:\.\d+)?)", re.I)
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


class _CallTimeout(TimeoutError):
    """Raised when a provider call exceeds its per-call time bound."""


def _scrub(text: str) -> str:
    """Redact API-key-looking tokens from text."""
    return _SECRET_RE.sub("[redacted]", text)


def _format_exc(exc: BaseException) -> str:
    """Return a scrubbed ``"<Type>: <first 200 chars>"`` description."""
    return _scrub(f"{type(exc).__name__}: {str(exc)[:200]}")


def parse_retry_after(exc: BaseException) -> float | None:
    """Extract a retry delay (seconds) from a rate-limit exception, if present.

    Looks at the response ``retry-after`` / ``retry-after-ms`` headers, a
    ``retry_after`` attribute, then at message text such as
    ``"Please try again in 1m3.5s"``.

    Args:
        exc: The exception raised by the provider SDK.

    Returns:
        Seconds to wait, or None when nothing parseable was found.
    """
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None:
        try:
            raw = headers.get("retry-after")
            if raw is not None:
                return max(0.0, float(raw))
            raw_ms = headers.get("retry-after-ms")
            if raw_ms is not None:
                return max(0.0, float(raw_ms) / 1000.0)
        except (TypeError, ValueError, AttributeError):
            pass
    direct = getattr(exc, "retry_after", None)
    if isinstance(direct, (int, float)):
        return max(0.0, float(direct))
    message = str(exc)
    match = _RETRY_MSG_RE.search(message)
    if match:
        total = sum(
            float(num) * _UNIT_SECONDS[unit]
            for num, unit in _DURATION_RE.findall(match.group(1))
        )
        return total
    match = _RETRY_AFTER_MSG_RE.search(message)
    if match:
        return float(match.group(1))
    return None


def classify_error(exc: BaseException) -> tuple[str, float | None]:
    """Classify a provider exception.

    Returns:
        ``("rate_limit", retry_after_or_None)``, ``("timeout", None)`` or
        ``("error", None)``.
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if (
        status == 429
        or "ratelimit" in name
        or "rate limit" in message
        or "rate-limit" in message
        or "rate_limit" in message
        or re.search(r"\b429\b", message[:300])
    ):
        return "rate_limit", parse_retry_after(exc)
    if isinstance(exc, (TimeoutError, concurrent.futures.TimeoutError)) or (
        "timeout" in name or "timed out" in message
    ):
        return "timeout", None
    return "error", None


def _call_bounded(fn: Callable[[], Any], timeout: float) -> Any:
    """Run ``fn`` in a daemon thread and wait at most ``timeout`` seconds.

    A hung call can never block the caller or interpreter shutdown: on timeout
    the thread is abandoned (the SDK's own HTTP timeout reaps the socket).

    Raises:
        _CallTimeout: ``fn`` did not finish in time.
        Exception: Whatever ``fn`` raised.
    """
    box: dict[str, Any] = {}
    done = threading.Event()

    def runner() -> None:
        try:
            box["result"] = fn()
        except Exception as exc:  # noqa: BLE001 - re-raised in caller thread
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=runner, daemon=True, name="llm-pool-call").start()
    if not done.wait(timeout):
        raise _CallTimeout(f"no response within {timeout:.1f}s")
    if "error" in box:
        raise box["error"]
    return box["result"]


class LLMEstimateCache:
    """Thread-safe sqlite cache of LLM estimates (``estimates`` table)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS estimates ("
                "key TEXT PRIMARY KEY, provider TEXT, model TEXT, "
                "value TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            conn.commit()
            self._conn = conn
        except sqlite3.Error:
            logger.warning("LLM estimate cache unavailable at %s", self.path,
                           exc_info=True)

    def get(self, key: str) -> dict[str, Any] | None:
        """Return ``{provider, model, estimate}`` for a key, or None."""
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT provider, model, value FROM estimates WHERE key = ?",
                    (key,),
                ).fetchone()
            if row is None:
                return None
            return {
                "provider": row[0], "model": row[1], "estimate": json.loads(row[2]),
            }
        except (sqlite3.Error, ValueError):
            logger.warning("LLM estimate cache read failed", exc_info=True)
            return None

    def put(
        self, key: str, provider: str, model: str, estimate: dict[str, Any]
    ) -> None:
        """Store an estimate; failures are logged and swallowed."""
        if self._conn is None:
            return
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO estimates "
                    "(key, provider, model, value, created_at) VALUES (?,?,?,?,?)",
                    (key, provider, model, json.dumps(estimate), time.time()),
                )
                self._conn.commit()
        except sqlite3.Error:
            logger.warning("LLM estimate cache write failed", exc_info=True)

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


def cache_key(model: str, item: dict[str, Any]) -> str:
    """sha256 over model, prompt version and the item's identifying fields."""
    parts = [
        model, PROMPT_VERSION,
        str(item.get("category", "")), str(item.get("severity", "")),
        str(item.get("file_path", "")), str(item.get("function_name", "")),
        str(item.get("code_snippet", "")),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def stable_hash(item: dict[str, Any]) -> int:
    """Process-independent hash of file + function + category (for pinning)."""
    raw = "\x1f".join([
        str(item.get("file_path", "")), str(item.get("function_name", "")),
        str(item.get("category", "")),
    ])
    return int(hashlib.sha1(raw.encode("utf-8")).hexdigest(), 16)


class _Batch:
    """A unit of work: input indices plus retry bookkeeping."""

    __slots__ = ("indices", "attempts", "failed_on", "rl_requeues", "last_error")

    def __init__(self, indices: list[int], attempts: int = 0) -> None:
        self.indices = indices
        self.attempts = attempts
        self.failed_on: set[str] = set()
        self.rl_requeues = 0
        self.last_error: str | None = None


class LLMPool:
    """Estimate debt items across several LLM providers concurrently.

    Args:
        providers: Provider names in pool order (default: keyed providers from
            ``llm_factory.available_pool_providers()``).
        estimators: Optional ``{provider: estimator}`` (anything exposing
            ``estimate_debt_items_batch_strict``); built from
            ``llm_factory.get_llm_for`` when omitted.
        models: Optional ``{provider: model_id}`` (primary model per provider).
        model_candidates: Optional ``{provider: [model ids]}`` listing every
            model a provider may actually serve (OpenRouter fallback routing);
            used for cache lookups. Defaults to the primary model only.
        concurrency: Optional ``{provider: worker_threads}``.
        batch_size: Items per LLM call.
        batch_timeout: Per-call time bound in seconds.
        time_box: Whole-pool time bound in seconds.
        max_attempts: Max attempts per batch.
        backoff_base: First rate-limit cooldown (seconds) without retry-after.
        backoff_cap: Cap on the exponential rate-limit cooldown.
        failure_limit: Consecutive failures that disable a provider.
        use_cache: Enable the sqlite estimate cache.
        cache_path: Cache file (default ``data/cache/llm_estimates.db``).
    """

    def __init__(
        self,
        providers: list[str] | None = None,
        *,
        estimators: dict[str, Any] | None = None,
        models: dict[str, str] | None = None,
        model_candidates: dict[str, list[str]] | None = None,
        concurrency: dict[str, int] | None = None,
        batch_size: int | None = None,
        batch_timeout: float | None = None,
        time_box: float | None = None,
        max_attempts: int | None = None,
        backoff_base: float = BACKOFF_BASE_SECONDS,
        backoff_cap: float = BACKOFF_CAP_SECONDS,
        failure_limit: int = CONSECUTIVE_FAILURE_LIMIT,
        use_cache: bool = True,
        cache_path: Path | str | None = None,
    ) -> None:
        if providers is None:
            if estimators is not None:
                providers = list(estimators)
            else:
                from agents.llm_factory import available_pool_providers

                providers = available_pool_providers()
        self.estimators: dict[str, Any] = dict(estimators or {})
        self.models: dict[str, str] = dict(models or {})
        self.model_candidates: dict[str, list[str]] = {}
        built: list[str] = []
        for name in providers:
            if name not in self.estimators:
                try:
                    from agents.llm_factory import get_llm_for

                    self.estimators[name] = LLMEstimator(llm=get_llm_for(name, "json"))
                except Exception as exc:  # noqa: BLE001 - skip unusable provider
                    logger.warning(
                        "LLM pool: provider %s unavailable (%s)", name,
                        _format_exc(exc),
                    )
                    continue
            if name not in self.models:
                try:
                    from agents.llm_factory import get_model_id_for

                    self.models[name] = get_model_id_for(name)
                except Exception:  # noqa: BLE001 - model id is informational
                    self.models[name] = name
            if model_candidates and name in model_candidates:
                candidates = list(model_candidates[name])
            else:
                try:
                    from agents.llm_factory import get_model_candidates_for

                    candidates = get_model_candidates_for(name)
                    if self.models[name] not in candidates:
                        candidates.insert(0, self.models[name])
                except Exception:  # noqa: BLE001 - candidates are best-effort
                    candidates = [self.models[name]]
            self.model_candidates[name] = candidates
            built.append(name)
        self.providers: list[str] = built
        self.concurrency: dict[str, int] = {
            p: max(1, int((concurrency or {}).get(p, config.LLM_CONCURRENCY.get(p, 2))))
            for p in self.providers
        }
        self.batch_size = max(1, batch_size or config.LLM_BATCH_SIZE)
        self.batch_timeout = (
            config.LLM_BATCH_TIMEOUT_SECONDS if batch_timeout is None else batch_timeout
        )
        self.time_box = (
            config.LLM_POOL_TIME_BOX_SECONDS if time_box is None else time_box
        )
        self.max_attempts = max(1, max_attempts or config.LLM_MAX_ATTEMPTS)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.failure_limit = max(1, failure_limit)

        self.cache: LLMEstimateCache | None = None
        if use_cache and os.getenv("LLM_CACHE_ENABLED", "true").lower() in (
            "true", "1", "yes",
        ):
            self.cache = LLMEstimateCache(
                cache_path or os.getenv("LLM_CACHE_PATH") or DEFAULT_CACHE_PATH
            )

        self.last_stats: dict[str, Any] = {}
        self._cond = threading.Condition()
        self._reset_locked([])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def preferred_provider(self, item: dict[str, Any]) -> str:
        """Return the provider an item is pinned to (stable across runs)."""
        return self.providers[stable_hash(item) % len(self.providers)]

    def estimate_items(
        self, inputs: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Estimate every item, returning results in input order plus stats.

        Args:
            inputs: Item dicts (file_path, category, severity, description,
                code_snippet, function_name, language).

        Returns:
            ``(results, stats)``. Each result is a normalized estimate with
            ``estimation_source`` ("llm" | "fallback"), ``estimation_provider``
            and ``estimation_model`` (None for fallbacks) and ``cached: True``
            on cache hits. ``stats`` is ``{per_provider: {name: {batches_ok,
            items_ok, rate_limited, timeouts, errors, disabled, ...}},
            cache_hits, elapsed_s, total, llm, fallback, time_box_expired}``.
        """
        started = time.monotonic()
        n = len(inputs)
        with self._cond:
            self._reset_locked(inputs)
        if n == 0:
            return [], self._snapshot(started, False)
        if not self.providers:
            error = "NoProviders: no LLM pool provider is configured"
            with self._cond:
                for i in range(n):
                    self._resolve_locked(i, self._fallback_for(inputs[i], error))
            return list(self._results), self._snapshot(started, False)  # type: ignore[arg-type]

        deadline = started + self.time_box
        prefs = [self.preferred_provider(item) for item in inputs]
        pending: list[int] = []
        cache_hits = 0
        for i, item in enumerate(inputs):
            hit = self._cache_lookup(item, prefs[i])
            if hit is not None:
                cache_hits += 1
                with self._cond:
                    self._resolve_locked(i, hit)
            else:
                pending.append(i)

        with self._cond:
            self._cache_hits = cache_hits
            self._deadline = deadline
            for provider in self.providers:
                mine = [i for i in pending if prefs[i] == provider]
                for k in range(0, len(mine), self.batch_size):
                    self._queues[provider].append(
                        _Batch(mine[k:k + self.batch_size])
                    )
            total_batches = sum(len(q) for q in self._queues.values())
        logger.info(
            "[LLM POOL] %d items (%d cache hits) in %d batches across %s",
            n, cache_hits, total_batches, ",".join(self.providers),
        )

        if pending:
            for provider in self.providers:
                for k in range(self.concurrency[provider]):
                    threading.Thread(
                        target=self._worker, args=(provider,), daemon=True,
                        name=f"llm-pool-{provider}-{k}",
                    ).start()

        time_box_expired = False
        with self._cond:
            while self._unresolved > 0:
                now = time.monotonic()
                if now >= deadline:
                    time_box_expired = True
                    break
                if self._stalled_locked(now):
                    break
                self._cond.wait(min(_IDLE_WAIT_SECONDS, deadline - now))
            self._stop = True
            if self._unresolved > 0:
                reason = self._unresolved_reason_locked(time_box_expired)
                logger.warning(
                    "[LLM POOL] %d items unresolved -> fallback (%s)",
                    self._unresolved, reason,
                )
                for i in range(n):
                    if self._results[i] is None:
                        self._resolve_locked(i, self._fallback_for(inputs[i], reason))
            self._cond.notify_all()

        stats = self._snapshot(started, time_box_expired)
        logger.info(
            "[LLM POOL] done in %.1fs: %d llm, %d fallback, %d cache hits, %s",
            stats["elapsed_s"], stats["llm"], stats["fallback"], cache_hits,
            {p: s["items_ok"] for p, s in stats["per_provider"].items()},
        )
        self.last_stats = stats
        return list(self._results), stats  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # State helpers (callers hold self._cond unless noted)
    # ------------------------------------------------------------------

    def _reset_locked(self, inputs: list[dict[str, Any]]) -> None:
        """Reset all per-scan state."""
        self._inputs = inputs
        self._results: list[dict[str, Any] | None] = [None] * len(inputs)
        self._unresolved = len(inputs)
        self._queues: dict[str, list[_Batch]] = {p: [] for p in self.providers}
        self._disabled: dict[str, bool] = {p: False for p in self.providers}
        self._cooldown_until: dict[str, float] = {p: 0.0 for p in self.providers}
        self._consec_fail: dict[str, int] = {p: 0 for p in self.providers}
        self._rl_streak: dict[str, int] = {p: 0 for p in self.providers}
        self._last_error: dict[str, str | None] = {p: None for p in self.providers}
        self._stats: dict[str, dict[str, Any]] = {
            p: {
                "batches_ok": 0, "items_ok": 0, "rate_limited": 0,
                "timeouts": 0, "errors": 0, "disabled": False,
                "model": self.models.get(p),
            }
            for p in self.providers
        }
        self._inflight = 0
        self._cache_hits = 0
        self._stop = False
        self._deadline = float("inf")

    def _snapshot(self, started: float, time_box_expired: bool) -> dict[str, Any]:
        """Build the stats dict (takes the lock itself)."""
        with self._cond:
            results = [r for r in self._results if r is not None]
            llm = sum(1 for r in results if r.get("estimation_source") == "llm")
            per_provider = {}
            for p in self.providers:
                entry = dict(self._stats[p])
                entry["last_error"] = self._last_error[p]
                per_provider[p] = entry
            return {
                "per_provider": per_provider,
                "cache_hits": self._cache_hits,
                "elapsed_s": round(time.monotonic() - started, 2),
                "total": len(results),
                "llm": llm,
                "fallback": len(results) - llm,
                "time_box_expired": time_box_expired,
            }

    def _resolve_locked(self, index: int, estimate: dict[str, Any]) -> None:
        """Record the final estimate for one item (first writer wins)."""
        if self._results[index] is None:
            self._results[index] = estimate
            self._unresolved -= 1
            self._cond.notify_all()

    def _fallback_for(self, item: dict[str, Any], error: str) -> dict[str, Any]:
        """Category-default estimate tagged with the failure reason."""
        est = LLMEstimator._fallback_estimates(
            item.get("category", "code_quality"),
            item.get("severity", "medium"),
            error=_scrub(error),
        )
        est["estimation_provider"] = None
        est["estimation_model"] = None
        return est

    def _stalled_locked(self, now: float) -> bool:
        """True when no provider can make progress before the deadline."""
        active = [p for p in self.providers if not self._disabled[p]]
        if not active:
            return True
        if all(self._cooldown_until[p] > self._deadline for p in active):
            return True
        queued = any(self._queues[p] for p in self.providers)
        return not queued and self._inflight == 0

    def _unresolved_reason_locked(self, time_box_expired: bool) -> str:
        """Human-readable reason unresolved items fall back."""
        errors = "; ".join(
            f"{p}: {e}" for p, e in self._last_error.items() if e
        )
        if time_box_expired:
            reason = f"TimeBoxExpired: LLM pool exceeded {self.time_box:.0f}s"
        elif all(self._disabled.values()):
            reason = "AllProvidersDisabled: every LLM provider failed repeatedly"
        else:
            reason = "AllProvidersUnavailable: providers rate-limited past time box"
        return f"{reason} ({errors})" if errors else reason

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _cache_lookup(
        self, item: dict[str, Any], preferred: str
    ) -> dict[str, Any] | None:
        """Look up an item under the preferred provider's models, then the rest."""
        if self.cache is None:
            return None
        order = [preferred] + [p for p in self.providers if p != preferred]
        for provider in order:
            for model in self.model_candidates[provider]:
                hit = self.cache.get(cache_key(model, item))
                if hit is not None and isinstance(hit.get("estimate"), dict):
                    est = dict(hit["estimate"])
                    est["estimation_source"] = "llm"
                    est["estimation_provider"] = hit.get("provider") or provider
                    est["estimation_model"] = hit.get("model") or model
                    est["cached"] = True
                    return est
        return None

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    def _eligible_locked(self, batch: _Batch, provider: str) -> bool:
        """A provider skips a batch it failed on while a fresh provider exists."""
        if provider not in batch.failed_on:
            return True
        return not any(
            q not in batch.failed_on and not self._disabled[q] for q in self.providers
        )

    def _take_locked(self, provider: str) -> _Batch | None:
        """Pop the next batch: own queue first, then steal from the others."""
        order = [provider] + [p for p in self.providers if p != provider]
        for owner in order:
            queue = self._queues[owner]
            for idx, batch in enumerate(queue):
                if self._eligible_locked(batch, provider):
                    return queue.pop(idx)
        return None

    def _worker(self, provider: str) -> None:
        """Worker thread body for one provider."""
        while True:
            with self._cond:
                batch: _Batch | None = None
                while True:
                    if self._stop or self._disabled[provider]:
                        return
                    now = time.monotonic()
                    if now >= self._deadline:
                        return
                    cooling = self._cooldown_until[provider] - now
                    if cooling > 0:
                        self._cond.wait(min(cooling, _IDLE_WAIT_SECONDS))
                        continue
                    batch = self._take_locked(provider)
                    if batch is not None:
                        self._inflight += 1
                        break
                    self._cond.wait(_IDLE_WAIT_SECONDS)
            try:
                self._process(provider, batch)
            except Exception:  # noqa: BLE001 - a worker must never die silently
                logger.exception("LLM pool worker error (%s)", provider)
                with self._cond:
                    self._handle_failure_locked(
                        provider, batch, "error", "InternalError: worker crashed",
                        None,
                    )
            finally:
                with self._cond:
                    self._inflight -= 1
                    self._cond.notify_all()

    def _process(self, provider: str, batch: _Batch) -> None:
        """Run one batch against one provider and record the outcome."""
        items = [self._inputs[i] for i in batch.indices]
        with self._cond:
            remaining = self._deadline - time.monotonic()
        timeout = min(self.batch_timeout, remaining)
        if timeout <= 0:
            return
        estimator = self.estimators[provider]
        started = time.monotonic()
        try:
            outs = _call_bounded(
                lambda: estimator.estimate_debt_items_batch_strict(items), timeout
            )
        except _CallTimeout as exc:
            with self._cond:
                if not self._stop:
                    self._handle_failure_locked(
                        provider, batch, "timeout",
                        f"TimeoutError: {exc}", None,
                    )
            return
        except Exception as exc:  # noqa: BLE001 - classify any SDK error
            kind, retry_after = classify_error(exc)
            with self._cond:
                if not self._stop:
                    self._handle_failure_locked(
                        provider, batch, kind, _format_exc(exc), retry_after,
                    )
            return

        outs = list(outs or [])
        outs.extend([None] * (len(batch.indices) - len(outs)))
        model = self.models[provider]
        stamped: list[tuple[int, dict[str, Any]]] = []
        missing: list[int] = []
        for k, idx in enumerate(batch.indices):
            est = outs[k]
            if est is None:
                missing.append(idx)
                continue
            est = dict(est)
            # A routing provider may report the model that really answered.
            actual_model = str(est.get("estimation_model") or model)
            est["estimation_source"] = "llm"
            est["estimation_provider"] = provider
            est["estimation_model"] = actual_model
            stamped.append((idx, est))
            if self.cache is not None:
                self.cache.put(
                    cache_key(actual_model, self._inputs[idx]),
                    provider, actual_model, est,
                )

        with self._cond:
            if self._stop:
                return
            if not stamped:
                self._handle_failure_locked(
                    provider, batch, "error",
                    "MissingEstimate: provider returned no valid estimate", None,
                )
                return
            st = self._stats[provider]
            st["batches_ok"] += 1
            st["items_ok"] += len(stamped)
            self._consec_fail[provider] = 0
            self._rl_streak[provider] = 0
            for idx, est in stamped:
                self._resolve_locked(idx, est)
            if missing:
                retry = _Batch(missing, attempts=batch.attempts + 1)
                retry.failed_on = set(batch.failed_on) | {provider}
                retry.rl_requeues = batch.rl_requeues
                self._requeue_locked(
                    retry, provider,
                    f"MissingEstimate: {len(missing)} item(s) omitted by LLM",
                )
        logger.debug(
            "[LLM POOL] %s batch of %d ok in %.1fs", provider, len(batch.indices),
            time.monotonic() - started,
        )

    # ------------------------------------------------------------------
    # Failure handling (lock held)
    # ------------------------------------------------------------------

    def _handle_failure_locked(
        self,
        provider: str,
        batch: _Batch,
        kind: str,
        error: str,
        retry_after: float | None,
    ) -> None:
        """Apply rate-limit / timeout / error policy and requeue the batch."""
        now = time.monotonic()
        st = self._stats[provider]
        self._last_error[provider] = error
        batch.last_error = error

        if kind == "rate_limit":
            st["rate_limited"] += 1
            if now >= self._cooldown_until[provider]:
                self._rl_streak[provider] += 1
                if retry_after is not None:
                    delay = min(retry_after + 0.25, RETRY_AFTER_CAP_SECONDS)
                else:
                    delay = min(
                        self.backoff_cap,
                        self.backoff_base * (2 ** (self._rl_streak[provider] - 1)),
                    )
                self._cooldown_until[provider] = now + delay
                logger.warning(
                    "[LLM POOL] %s rate-limited; cooling down %.1fs (%s)",
                    provider, delay, error,
                )
            batch.rl_requeues += 1
            if batch.rl_requeues > RATE_LIMIT_REQUEUE_FACTOR * self.max_attempts:
                self._fail_batch_locked(
                    batch, f"RateLimited: gave up after {batch.rl_requeues} "
                    f"rate-limit requeues ({error})",
                )
            else:
                self._requeue_locked(batch, provider, error)
            return

        st["timeouts" if kind == "timeout" else "errors"] += 1
        self._consec_fail[provider] += 1
        logger.warning(
            "[LLM POOL] %s %s on batch of %d (attempt %d): %s",
            provider, kind, len(batch.indices), batch.attempts + 1, error,
        )
        if self._consec_fail[provider] >= self.failure_limit and not self._disabled[
            provider
        ]:
            self._disabled[provider] = True
            st["disabled"] = True
            logger.error(
                "[LLM POOL] %s disabled for the rest of the scan after %d "
                "consecutive failures (last: %s)",
                provider, self._consec_fail[provider], error,
            )

        if kind == "timeout" and len(batch.indices) > 1:
            half = len(batch.indices) // 2
            parts = [batch.indices[:half], batch.indices[half:]]
        else:
            parts = [batch.indices]
        for part in parts:
            sub = _Batch(part, attempts=batch.attempts + 1)
            sub.failed_on = set(batch.failed_on)
            sub.rl_requeues = batch.rl_requeues
            self._requeue_locked(sub, provider, error)

    def _requeue_locked(self, batch: _Batch, failed_provider: str, error: str) -> None:
        """Queue a batch for a provider that has not failed it, or give up."""
        batch.failed_on.add(failed_provider)
        batch.last_error = error
        if batch.attempts >= self.max_attempts:
            self._fail_batch_locked(
                batch, f"{error} (gave up after {batch.attempts} attempts)"
            )
            return
        active = [p for p in self.providers if not self._disabled[p]]
        if not active:
            self._fail_batch_locked(
                batch, f"AllProvidersDisabled: {error}"
            )
            return
        target = next((p for p in active if p not in batch.failed_on), active[0])
        self._queues[target].append(batch)
        self._cond.notify_all()

    def _fail_batch_locked(self, batch: _Batch, error: str) -> None:
        """Resolve every unresolved item in a batch with a fallback estimate."""
        for idx in batch.indices:
            if self._results[idx] is None:
                self._resolve_locked(idx, self._fallback_for(self._inputs[idx], error))
