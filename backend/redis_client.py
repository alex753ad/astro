"""Shared async Redis client.

Единая точка доступа к Redis для не-OTP задач: денилист JWT, идемпотентность
платежей, TTL публичных токенов шаринга. Все обёртки безопасны к сбою Redis:
операции чтения (проверки) fail-open и логируют ошибку, чтобы недоступность
Redis не «ложила» весь сервис. Операции записи, критичные для безопасности
(денилист при logout, фиксация обработанного платежа), пробрасывают исключение
вызывающему коду, который сам решает, как реагировать.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from backend.config import get_settings

logger = logging.getLogger("astro.redis")

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _client
