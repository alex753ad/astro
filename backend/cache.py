"""In-memory cache with TTL.

Simple dict-based cache for variant A (single server).
Interface is designed for drop-in replacement with Redis later.
"""

from __future__ import annotations

import hashlib
import json
import time
import threading
from typing import Any, Optional


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL.

    Usage:
        cache = TTLCache()
        cache.set("key", value, ttl=3600)
        val = cache.get("key")  # None if expired
    """

    def __init__(self, max_size: int = 10_000):
        self._data: dict[str, tuple[Any, float]] = {}  # key → (value, expire_at)
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if expire_at > 0 and time.time() > expire_at:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        """Store a value. ttl=0 means no expiration."""
        expire_at = time.time() + ttl if ttl > 0 else 0
        with self._lock:
            if len(self._data) >= self._max_size:
                self._evict_expired()
            self._data[key] = (value, expire_at)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        now = time.time()
        expired = [k for k, (_, exp) in self._data.items() if exp > 0 and now > exp]
        for k in expired:
            del self._data[k]

    def __len__(self) -> int:
        return len(self._data)


# ── Global cache instances ──
interpretation_cache = TTLCache(max_size=5_000)
transit_cache = TTLCache(max_size=2_000)


def make_profile_hash(profile: dict) -> str:
    """Create a deterministic SHA-256 hash of a natal profile for cache key."""
    serialized = json.dumps(profile, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
