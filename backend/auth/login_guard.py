"""Счётчик неудачных входов по аккаунту.

Лимит по IP не защищает от перебора пароля к одному аккаунту с ботнета: каждый
адрес расходует свою квоту. Поэтому считаем неудачи ещё и по email — после
LOGIN_MAX_FAILURES попыток аккаунт временно блокируется независимо от того, с
каких адресов шли запросы.

Счётчик fail-open: при недоступности Redis вход не блокируется (иначе сбой
Redis означал бы отказ в обслуживании для всех), но инцидент логируется.
"""
from __future__ import annotations

import hashlib
import logging

from backend.config import get_settings
from backend.redis_client import get_redis

logger = logging.getLogger("astro.auth.login")

_PREFIX = "login:fail:"


def _key(email: str) -> str:
    # Email не кладём в Redis в открытом виде — ключи попадают в дампы и логи.
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]
    return f"{_PREFIX}{digest}"


async def is_locked(email: str) -> bool:
    """True, если по этому аккаунту исчерпан лимит неудачных попыток."""
    settings = get_settings()
    try:
        raw = await get_redis().get(_key(email))
    except Exception as exc:  # noqa: BLE001
        logger.error("login lockout check failed (fail-open): %s", exc)
        return False
    return int(raw or 0) >= settings.login_max_failures


async def record_failure(email: str) -> None:
    """Учесть неудачную попытку входа."""
    settings = get_settings()
    key = _key(email)
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            # TTL ставится только на первую неудачу — окно скользит от неё,
            # иначе непрерывный перебор продлевал бы блокировку бесконечно.
            await redis.expire(key, settings.login_lockout_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.error("login failure counter failed: %s", exc)


async def reset(email: str) -> None:
    """Сбросить счётчик после успешного входа."""
    try:
        await get_redis().delete(_key(email))
    except Exception as exc:  # noqa: BLE001
        logger.error("login counter reset failed: %s", exc)
