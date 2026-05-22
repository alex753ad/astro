"""backend/cache.py — Redis-backed cache.

Заменяет in-memory TTLCache. При недоступности Redis падает в no-op кеш
(логирует предупреждение, приложение продолжает работу без кеширования).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger("astro.cache")

# ── TTL constants ──
TTL_INTERPRETATION = 30 * 24 * 3600   # 30 дней
TTL_TRANSIT        =  7 * 24 * 3600   #  7 дней


class RedisCache:
    """Тонкая обёртка над redis-py с JSON-сериализацией и fallback."""

    def __init__(self, prefix: str, default_ttl: int):
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._redis = self._connect()

    def _connect(self):
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis
            client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
            client.ping()
            logger.info("Redis connected: %s (prefix=%s)", url, self._prefix)
            return client
        except Exception as e:
            logger.warning("Redis unavailable (%s) — cache disabled for %s", e, self._prefix)
            return None

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def get(self, key: str) -> Any | None:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(self._key(key))
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            logger.warning("Cache GET error: %s", e)
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(
                self._key(key),
                ttl or self._default_ttl,
                json.dumps(value, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning("Cache SET error: %s", e)

    def delete(self, key: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(self._key(key))
        except Exception as e:
            logger.warning("Cache DELETE error: %s", e)


# ── Singleton instances (импортируются из main.py) ──
interpretation_cache = RedisCache("interp", TTL_INTERPRETATION)
transit_cache        = RedisCache("transit", TTL_TRANSIT)


def make_profile_hash(profile: dict) -> str:
    """Стабильный хеш натального профиля для ключа кеша интерпретации."""
    serialized = json.dumps(profile, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]
