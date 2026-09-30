"""Активные дни — запись для удержания D1/D7/D30 (таблица user_activity_days).

Зовётся из get_current_user на каждый авторизованный запрос; в базу идёт
одна строка на человека, день и платформу. Повтор в тот же день отсекает
Redis (SET NX), а если Redis недоступен — ON CONFLICT DO NOTHING в базе.

Любой сбой проглатывается: метрика не должна ронять запрос.

Правило «человек вернулся» (решение владельца 30.09.2026) — в
metrics.compute_retention_weekly.
"""
from __future__ import annotations

import logging
from datetime import date, timezone
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy.orm import Session

from backend import redis_client
from backend.time_utils import utcnow

logger = logging.getLogger("astro.activity")

MSK = ZoneInfo("Europe/Moscow")

# Запросы, которые приложение шлёт само, без того чтобы человек его открыл:
# регистрация токена FCM и план локальных уведомлений. Засчитай их — и
# «вернулся» получит тот, кто приложение не открывал.
BACKGROUND_PATHS = frozenset({"/api/v1/push/device", "/api/v1/push/upcoming"})

# ⚠️ Приложение узнаётся по Origin, а не по X-Client-Platform: заголовок
# ставят только запросы авторизации (api/authTransport.js), а Origin
# webview Capacitor шлёт на каждый запрос — для браузера это чужой сайт.
# Сайт с aristeatime.ru на GET Origin не шлёт вовсе, на POST — свой.
APP_ORIGINS = frozenset({"https://localhost", "capacitor://localhost"})

_DEDUP_TTL = 2 * 86400


def msk_today() -> date:
    return utcnow().replace(tzinfo=timezone.utc).astimezone(MSK).date()


def platform_of(request: Request) -> str:
    if (request.headers.get("x-client-platform") == "mobile"
            or request.headers.get("origin") in APP_ORIGINS):
        return "app"
    return "web"


async def mark_active(request: Request, db: Session, user) -> None:
    if request.url.path in BACKGROUND_PATHS:
        return
    day = msk_today()
    platform = platform_of(request)
    key = f"active:{user.id}:{day.isoformat()}:{platform}"
    redis = None
    try:
        redis = redis_client.get_redis()
        if not await redis.set(key, 1, ex=_DEDUP_TTL, nx=True):
            return
    except Exception as e:  # noqa: BLE001 — без Redis пишем в базу, дубль погасит конфликт
        logger.warning("mark_active: redis недоступен user=%s: %s", user.id, e)
        redis = None
    try:
        _insert(db, user, day, platform)
    except Exception as e:  # noqa: BLE001
        logger.warning("mark_active failed user=%s: %s", user.id, e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        # Отметку снимаем, иначе день не запишется до завтра.
        if redis is not None:
            try:
                await redis.delete(key)
            except Exception:  # noqa: BLE001
                pass


def _insert(db: Session, user, day: date, platform: str) -> None:
    # Ленивый импорт: backend.flags импортирует auth.dependencies, откуда
    # зовут этот модуль.
    from backend.flags import enabled_flags
    from backend.models import UserActivityDay

    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:  # тесты на SQLite
        from sqlalchemy.dialects.sqlite import insert
    db.execute(
        insert(UserActivityDay.__table__)
        .values(user_id=user.id, day=day, platform=platform,
                flags=enabled_flags(db, user))
        .on_conflict_do_nothing()
    )
    db.commit()
