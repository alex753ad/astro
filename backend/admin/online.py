"""Online-user counter — Redis-backed, best-effort.

Пишется на каждый успешный get_current_user() (backend/auth/dependencies.py):
SETEX online:{user_id} ONLINE_TTL_SECONDS 1 — TTL сам вычищает протухшее,
отдельная задача очистки не нужна. Подсчёт — SCAN по маске online:*, а не
KEYS: не блокирует Redis целиком на большом keyspace.

Обе операции fail-open: недоступность Redis не должна ронять логин/API
(запись) или страницу статистики (подсчёт) — только лог/None.
"""
from __future__ import annotations

import logging

from backend.redis_client import get_redis

logger = logging.getLogger("astro.online")

ONLINE_TTL_SECONDS = 300


async def mark_online(user_id: str) -> None:
    try:
        await get_redis().set(f"online:{user_id}", 1, ex=ONLINE_TTL_SECONDS)
    except Exception as e:
        logger.warning("mark_online failed user=%s: %s", user_id, e)


async def count_online() -> int | None:
    try:
        redis = get_redis()
        count = 0
        async for _ in redis.scan_iter(match="online:*", count=500):
            count += 1
        return count
    except Exception as e:
        logger.warning("count_online failed: %s", e)
        return None
