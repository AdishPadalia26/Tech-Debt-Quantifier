"""Cache manager for Tech Debt Quantifier.

Provides centralized caching for all components with configurable TTLs.
Uses diskcache for persistent, thread-safe caching.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from diskcache import Cache

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DURATIONS = {
    "hourly_rates": timedelta(days=7),
    "sonar_rules": timedelta(days=7),
    "bls_data": timedelta(days=7),
    "stackoverflow": timedelta(days=30),
    "levels_fyi": timedelta(days=3),
    "breach_costs": timedelta(days=30),
    "cisq_benchmarks": timedelta(days=30),
    "osv_vulns": timedelta(hours=24),
    "github_insights": timedelta(hours=24),
    "ddg_searches": timedelta(days=7),
    "repo_profile": timedelta(hours=24),
}


class CacheManager:
    """Centralized cache manager for all components.
    
    Uses diskcache for persistent, thread-safe caching with TTL support.
    Each cache entry stores: {data, fetched_at, expires_at}
    """

    def __init__(self, cache_name: str = "tech_debt_cache") -> None:
        self._cache = Cache(str(CACHE_DIR / cache_name))

    def make_key(self, *args: Any) -> str:
        """Hash arbitrary args into a cache key.
        
        Args:
            *args: Any hashable arguments to create key from
            
        Returns:
            MD5 hex digest of arguments
        """
        key_string = json.dumps(args, sort_keys=True, default=str)
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(self, key: str, category: str) -> dict | None:
        """Return cached value if not expired, else None.
        
        Args:
            key: Cache key
            category: Cache category (determines TTL)
            
        Returns:
            Cached data dict or None if expired/missing
        """
        full_key = f"{category}:{key}"
        
        try:
            cached = self._cache.get(full_key)
            if cached is None:
                return None
                
            cached_data = json.loads(cached) if isinstance(cached, str) else cached
            
            expires_at = datetime.fromisoformat(cached_data.get("expires_at", "2000-01-01"))
            if datetime.now() > expires_at:
                logger.debug(f"Cache expired for {full_key}")
                del self._cache[full_key]
                return None
                
            return cached_data.get("data")
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Cache read error for {full_key}: {e}")
            return None

    def set(self, key: str, category: str, data: dict) -> None:
        """Store value with expiry timestamp.
        
        Args:
            key: Cache key
            category: Cache category (determines TTL)
            data: Data to cache
        """
        full_key = f"{category}:{key}"
        duration = CACHE_DURATIONS.get(category, timedelta(days=1))
        expires_at = datetime.now() + duration
        
        cache_entry = {
            "data": data,
            "fetched_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "category": category,
        }
        
        try:
            self._cache.set(full_key, json.dumps(cache_entry, default=str))
            logger.debug(f"Cached {full_key} until {expires_at.isoformat()}")
        except Exception as e:
            logger.warning(f"Cache write error for {full_key}: {e}")

    def is_fresh(self, key: str, category: str) -> bool:
        """Check if cache entry exists and is not expired.
        
        Args:
            key: Cache key
            category: Cache category
            
        Returns:
            True if fresh, False otherwise
        """
        return self.get(key, category) is not None

    def invalidate(self, key: str, category: str) -> None:
        """Remove a specific cache entry.
        
        Args:
            key: Cache key
            category: Cache category
        """
        full_key = f"{category}:{key}"
        try:
            del self._cache[full_key]
        except KeyError:
            pass

    def clear_category(self, category: str) -> int:
        """Clear all entries in a category.
        
        Args:
            category: Cache category to clear
            
        Returns:
            Number of entries cleared
        """
        prefix = f"{category}:"
        keys_to_delete = [k for k in self._cache.iterkeys() if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)

    def clear_all(self) -> int:
        """Clear entire cache.
        
        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        return count

    def stats(self) -> dict:
        """Get cache statistics.
        
        Returns:
            Dict with cache size and category breakdown
        """
        categories: dict[str, int] = {}
        for key in self._cache.iterkeys():
            category = key.split(":")[0] if ":" in key else "unknown"
            categories[category] = categories.get(category, 0) + 1
        
        return {
            "total_entries": len(self._cache),
            "by_category": categories,
            "cache_dir": str(CACHE_DIR),
        }


_global_cache: CacheManager | None = None


def get_cache() -> CacheManager:
    """Get the global cache instance.
    
    Returns:
        Global CacheManager singleton
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager()
    return _global_cache
