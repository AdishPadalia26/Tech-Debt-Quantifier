"""Redis-backed job state store with in-memory fallback.

Tries Redis first; falls back to a process-local dict when Redis is
unavailable (e.g. local dev without a running Redis instance).

Redis availability is cached after the first probe so that connection
attempts don't block async endpoint handlers on every call.
"""

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_JOB_TTL = 3600  # 1 hour

# In-memory fallback used when Redis is unreachable
_mem: dict[str, dict[str, Any]] = {}

# Cache Redis reachability.  Probes always run in a background thread so
# the main asyncio event loop is never blocked by a TCP connect attempt.
_redis_available: bool = False
_redis_last_check: float = 0.0
_REDIS_RETRY_S = 60  # re-probe every 60 seconds
_redis_probe_lock = threading.Lock()
_redis_probing = False


def _do_probe() -> None:
    """Run once in a daemon thread; updates the shared availability flag."""
    global _redis_available, _redis_last_check, _redis_probing
    try:
        from redis import Redis
        r = Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
            socket_connect_timeout=0.3,
            socket_timeout=0.5,
        )
        r.ping()
        _redis_available = True
        logger.info("Redis connection OK")
    except Exception:
        _redis_available = False
        logger.debug("Redis unavailable — using in-memory fallback")
    finally:
        _redis_last_check = time.monotonic()
        with _redis_probe_lock:
            _redis_probing = False


def _check_redis_available() -> bool:
    """Return cached Redis availability; schedule a background re-probe if stale."""
    global _redis_probing
    now = time.monotonic()
    if now - _redis_last_check < _REDIS_RETRY_S:
        return _redis_available
    with _redis_probe_lock:
        if _redis_probing:
            return _redis_available
        if now - _redis_last_check < _REDIS_RETRY_S:
            return _redis_available
        _redis_probing = True
    t = threading.Thread(target=_do_probe, daemon=True, name="redis-probe")
    t.start()
    return _redis_available  # return stale value while probe runs


def _redis():
    from redis import Redis
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        decode_responses=True,
        socket_connect_timeout=0.3,
        socket_timeout=0.5,
    )


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def set_job(job_id: str, data: dict[str, Any]) -> None:
    if not _check_redis_available():
        _mem[job_id] = data
        return
    try:
        _redis().set(_job_key(job_id), json.dumps(data, default=str), ex=_JOB_TTL)
        _mem.pop(job_id, None)
    except Exception:
        _mem[job_id] = data


def get_job(job_id: str) -> dict[str, Any] | None:
    if not _check_redis_available():
        return _mem.get(job_id)
    try:
        raw = _redis().get(_job_key(job_id))
        return json.loads(raw) if raw else _mem.get(job_id)
    except Exception:
        return _mem.get(job_id)


def update_job(job_id: str, **fields: Any) -> None:
    data = get_job(job_id) or {}
    data.update(fields)
    set_job(job_id, data)


def job_exists(job_id: str) -> bool:
    if not _check_redis_available():
        return job_id in _mem
    try:
        return bool(_redis().exists(_job_key(job_id))) or job_id in _mem
    except Exception:
        return job_id in _mem


def list_jobs() -> list[dict[str, Any]]:
    """Return all active jobs from Redis (or in-memory fallback)."""
    if not _check_redis_available():
        return list(_mem.values())
    try:
        r = _redis()
        keys = r.keys("job:*")
        result = []
        for key in keys:
            raw = r.get(key)
            if raw:
                try:
                    result.append(json.loads(raw))
                except Exception:
                    pass
        return result or list(_mem.values())
    except Exception:
        return list(_mem.values())
