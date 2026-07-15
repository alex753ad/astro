"""JWT revocation store (denylist by jti).

Отзыв токенов реализован через денилист их идентификаторов (jti) в Redis с TTL,
равным оставшемуся сроку жизни токена — после истечения exp запись всё равно
не нужна. Используется при logout, ротации refresh (reuse-detection) и может
вызываться при смене пароля / деактивации аккаунта.

Проверка `is_denied` fail-open: если Redis недоступен, доступ не блокируется, но
инцидент логируется (доступность важнее строгости в рантайме). Запись `deny`
пробрасывает исключение — logout должен гарантированно отозвать токен.
"""
from __future__ import annotations

import logging

from backend.redis_client import get_redis

logger = logging.getLogger("astro.auth.tokens")

_PREFIX = "jwt:denied:"


async def deny(jti: str, ttl_seconds: int) -> None:
    """Поместить jti в денилист на оставшийся срок жизни токена."""
    if not jti:
        return
    ttl = max(int(ttl_seconds), 1)
    await get_redis().setex(f"{_PREFIX}{jti}", ttl, "1")


async def is_denied(jti: str) -> bool:
    """True, если токен отозван. Fail-open при недоступности Redis."""
    if not jti:
        return False
    try:
        return bool(await get_redis().exists(f"{_PREFIX}{jti}"))
    except Exception as exc:  # noqa: BLE001
        logger.error("JWT denylist check failed (fail-open): %s", exc)
        return False
