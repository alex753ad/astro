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
        self._local: dict[str, Any] = {}  # in-memory fallback when Redis is down

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
            raw = self._local.get(self._key(key))
            return raw
        try:
            raw = self._redis.get(self._key(key))
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            logger.warning("Cache GET error: %s", e)
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._redis is None:
            self._local[self._key(key)] = value
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
            self._local.pop(self._key(key), None)
            return
        try:
            self._redis.delete(self._key(key))
        except Exception as e:
            logger.warning("Cache DELETE error: %s", e)

    def clear(self) -> None:
        """Clear all keys for this prefix (used in tests)."""
        self._local.clear()
        if self._redis is None:
            return
        try:
            keys = self._redis.keys(f"{self._prefix}:*")
            if keys:
                self._redis.delete(*keys)
        except Exception as e:
            logger.warning("Cache CLEAR error: %s", e)


# ── Singleton instances (импортируются из main.py) ──
interpretation_cache = RedisCache("interp", TTL_INTERPRETATION)
transit_cache        = RedisCache("transit", TTL_TRANSIT)


def make_profile_hash(profile: dict) -> str:
    """Стабильный хеш натального профиля для ключа кеша интерпретации."""
    serialized = json.dumps(profile, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════
# AI BUDGET TRACKING (Redis)
# ═══════════════════════════════════════════════════════════

class BudgetTracker:
    """Суточный бюджет AI в Redis. Fallback — in-memory."""

    def __init__(self):
        self._redis = interpretation_cache._redis  # переиспользуем соединение
        self._local: dict[str, float] = {}         # fallback если Redis недоступен

    def _today_key(self) -> str:
        import time
        return f"ai_budget:{time.strftime('%Y-%m-%d')}"

    def get_spent(self) -> float:
        if self._redis:
            try:
                val = self._redis.get(self._today_key())
                return float(val) if val else 0.0
            except Exception:
                pass
        import time
        return self._local.get(time.strftime("%Y-%m-%d"), 0.0)

    def add_spend(self, amount_usd: float) -> float:
        """Прибавить расход. Возвращает новый итог."""
        import time
        today = time.strftime("%Y-%m-%d")
        if self._redis:
            try:
                pipe = self._redis.pipeline()
                key = self._today_key()
                pipe.incrbyfloat(key, amount_usd)
                pipe.expire(key, 86400)      # TTL 1 день — сброс в следующие сутки
                results = pipe.execute()
                return float(results[0])
            except Exception as e:
                logger.warning("Budget Redis error: %s", e)
        # fallback
        self._local[today] = self._local.get(today, 0.0) + amount_usd
        return self._local[today]

    def is_within_budget(self, limit_usd: float, engine_name: str) -> bool:
        if engine_name == "template":
            return True
        return self.get_spent() < limit_usd


budget_tracker = BudgetTracker()


# ═══════════════════════════════════════════════════════════
# IP MONITORING (защита от складчин для Premium)
# ═══════════════════════════════════════════════════════════

class IpMonitor:
    """Отслеживает уникальные IP пользователя за последние 30 минут.

    Если 3+ разных IP → сброс сессии (возвращает True).
    Хранится в Redis как sorted set: ip → timestamp.
    """

    WINDOW_SEC = 30 * 60   # 30 минут
    MAX_IPS    = 3

    def __init__(self):
        self._redis = interpretation_cache._redis

    def _key(self, user_id: str) -> str:
        return f"ip_monitor:{user_id}"

    def record_and_check(self, user_id: str, ip: str) -> bool:
        """Записывает IP. Возвращает True если превышен лимит уникальных IP."""
        if not self._redis:
            return False  # без Redis мониторинг отключён

        import time
        now = time.time()
        cutoff = now - self.WINDOW_SEC
        key = self._key(user_id)

        try:
            pipe = self._redis.pipeline()
            # Добавляем текущий IP со score=timestamp
            pipe.zadd(key, {ip: now})
            # Удаляем записи старше 30 минут
            pipe.zremrangebyscore(key, 0, cutoff)
            # Считаем уникальные IP в окне
            pipe.zcard(key)
            pipe.expire(key, self.WINDOW_SEC * 2)
            results = pipe.execute()
            unique_count = results[2]
            if unique_count > self.MAX_IPS:
                logger.warning(
                    "IP monitor: user=%s has %d unique IPs in 30min — session reset",
                    user_id, unique_count,
                )
                return True
        except Exception as e:
            logger.warning("IP monitor Redis error: %s", e)

        return False


ip_monitor = IpMonitor()


# ═══════════════════════════════════════════════════════════
# SECTION CACHE (кеш секций интерпретаций, задача 6.1)
# ═══════════════════════════════════════════════════════════

TTL_SECTION = 30 * 24 * 3600  # 30 дней


def get_section_cache_key(chart_id: str, planet: str, sign: str, house: str, prompt_version: str) -> str:
    return f"interp:{chart_id}:{planet}:{sign}:{house}:{prompt_version}"


def get_cached_section(key: str) -> str | None:
    if interpretation_cache._redis is None:
        return None
    try:
        return interpretation_cache._redis.get(key)
    except Exception as e:
        logger.warning("Section cache GET error: %s", e)
        return None


def set_cached_section(key: str, text: str, ttl: int = TTL_SECTION) -> None:
    if interpretation_cache._redis is None:
        return
    try:
        interpretation_cache._redis.setex(key, ttl, text)
    except Exception as e:
        logger.warning("Section cache SET error: %s", e)
