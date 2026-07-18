"""Одноразовые тикеты для SSE-подключений.

EventSource не умеет слать заголовок Authorization, поэтому раньше access-токен
передавался в query (`?token=`). Это утечка: URL попадает в логи прокси, в
Referer и в историю браузера, а живёт access-токен минуты.

Вместо него — короткоживущий одноразовый тикет: клиент меняет свой access-токен
на тикет обычным POST (с заголовком), затем открывает EventSource с `?ticket=`.
Сервер гасит тикет при обмене, поэтому повторное использование невозможно.

Обе операции fail-closed: если Redis недоступен, тикет не выдаётся и не
принимается — деградация до отсутствия SSE, а не до анонимного доступа.
"""
from __future__ import annotations

import logging
import secrets

from backend.config import get_settings
from backend.redis_client import get_redis

logger = logging.getLogger("astro.auth.sse")

_PREFIX = "sse:ticket:"


async def issue(user_id: str) -> str:
    """Выдать одноразовый тикет для пользователя."""
    ticket = secrets.token_urlsafe(32)
    ttl = max(int(get_settings().sse_ticket_ttl_seconds), 1)
    await get_redis().setex(f"{_PREFIX}{ticket}", ttl, user_id)
    return ticket


async def redeem(ticket: str) -> str | None:
    """Обменять тикет на user_id, погасив его. None — если тикет невалиден.

    Гашение и чтение — одной атомарной операцией (GETDEL), иначе два
    параллельных подключения успели бы использовать один тикет.
    """
    if not ticket:
        return None
    try:
        return await get_redis().getdel(f"{_PREFIX}{ticket}")
    except Exception as exc:  # noqa: BLE001
        logger.error("SSE ticket redeem failed (fail-closed): %s", exc)
        return None
