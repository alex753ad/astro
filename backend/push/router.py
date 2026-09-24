"""Push API — подписки и настройки уведомлений.

Endpoints:
  GET   /api/v1/push/vapid-public-key   — публичный VAPID-ключ для фронта (без авторизации)
  POST  /api/v1/push/subscribe          — сохранить подписку устройства (auth)
  POST  /api/v1/push/unsubscribe        — удалить подписку по endpoint (auth)
  POST  /api/v1/push/device             — зарегистрировать токен FCM (auth)
  DELETE /api/v1/push/device            — забыть токен FCM (auth)
  GET   /api/v1/push/settings           — настройки уведомлений (auth)
  PATCH /api/v1/push/settings           — обновить настройки (auth)
  GET   /api/v1/push/upcoming           — будущие события с готовым текстом (auth)
  POST  /api/v1/push/test               — тестовый пуш себе (auth)

Подключается отдельной строкой в main.py.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, PushSubscription, DeviceToken, utcnow
from backend.time_utils import valid_timezone
from backend.auth.dependencies import get_current_user
from backend.push.sender import vapid_public_key, send_to_user
from backend.push.fcm import configured as fcm_configured
from backend.push.cron import (
    collect_upcoming,
    UPCOMING_DEFAULT_DAYS,
    UPCOMING_MAX_DAYS,
)

logger = logging.getLogger("astro.push.router")

router = APIRouter(prefix="/api/v1/push", tags=["push"])

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")  # HH:MM 24ч


# ── Schemas ──
class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class UnsubscribeRequest(BaseModel):
    endpoint: str


class DeviceTokenRequest(BaseModel):
    token: str
    platform: str = "android" 


class PushSettings(BaseModel):
    daily_forecast: bool
    daily_time: str
    quiet_from: str
    planner: bool
    key_transits: bool
    moon_phases: bool
    timezone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PushSettingsPatch(BaseModel):
    daily_forecast: Optional[bool] = None
    daily_time: Optional[str] = None
    quiet_from: Optional[str] = None
    planner: Optional[bool] = None
    key_transits: Optional[bool] = None
    moon_phases: Optional[bool] = None
    # Пояс устройства (IANA). Шлёт клиент сам, не человек.
    timezone: Optional[str] = None


def _settings_of(user: User) -> PushSettings:
    return PushSettings(
        daily_forecast=bool(getattr(user, "push_daily_forecast", True)),
        daily_time=str(getattr(user, "push_daily_time", "08:00") or "08:00"),
        quiet_from=str(getattr(user, "push_quiet_from", "22:00") or "22:00"),
        planner=bool(getattr(user, "push_planner", True)),
        key_transits=bool(getattr(user, "push_key_transits", True)),
        moon_phases=bool(getattr(user, "push_moon_phases", False)),
        timezone=getattr(user, "device_timezone", None),
    )


# ── Public: VAPID key ──
@router.get("/vapid-public-key", summary="Public VAPID key for the browser")
async def get_vapid_public_key():
    key = vapid_public_key()
    if not key:
        raise HTTPException(status_code=503, detail="Push not configured")
    return {"public_key": key}


# ── Subscribe / Unsubscribe ──
@router.post("/subscribe", summary="Save a push subscription for this device")
async def subscribe(
    payload: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint
    ).first()
    if existing:
        # Переназначаем подписку текущему пользователю и обновляем ключи
        existing.user_id = user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
    else:
        db.add(PushSubscription(
            user_id=user.id,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
        ))
    db.commit()
    return {"status": "ok"}


@router.post("/unsubscribe", summary="Delete a push subscription")
async def unsubscribe(
    payload: UnsubscribeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint,
        PushSubscription.user_id == user.id,
    ).delete()
    db.commit()
    return {"status": "ok"}


# ── Токен устройства (FCM) ──
@router.post("/device", summary="Register this device's FCM token")
async def register_device(
    payload: DeviceTokenRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Запомнить токен FCM этого устройства.

    ⚠️ Запись ПЕРЕЕЗЖАЕТ к текущему пользователю, а не добавляется второй, и
    это не оптимизация. Токен принадлежит установленному приложению, а не
    аккаунту: после выхода и входа под другим пользователем на том же телефоне
    прежний владелец продолжал бы получать уведомления по чужой карте. Тем же
    приёмом устроен `/subscribe` для браузера.

    Клиент присылает токен при каждом запуске, а не только при первом: FCM
    ротирует его сам (переустановка, очистка данных, миграция на новый
    телефон), и «зарегистрировались один раз» означало бы копить мёртвые
    записи. Поэтому у повторного вызова нет побочных эффектов, кроме
    `last_seen_at`.
    """
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="token must not be empty",
        )

    row = db.query(DeviceToken).filter(DeviceToken.token == token).first()
    if row:
        row.user_id = user.id
        row.platform = payload.platform or "android"
        row.last_seen_at = utcnow()
    else:
        db.add(DeviceToken(
            user_id=user.id,
            token=token,
            platform=payload.platform or "android",
        ))
    db.commit()

    # Клиенту важно знать, доедет ли что-нибудь по этому каналу: от этого
    # зависит, оставлять ли ему локальные уведомления запасным вариантом.
    # Отвечаем фактом настройки сервера, а не обещанием доставки.
    return {"status": "ok", "delivery": "fcm" if fcm_configured() else "unconfigured"}


@router.delete("/device", summary="Forget this device's FCM token")
async def forget_device(
    payload: DeviceTokenRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Убрать токен. Зовётся при выходе из аккаунта и при выключении тумблера."""
    db.query(DeviceToken).filter(
        DeviceToken.token == payload.token,
        DeviceToken.user_id == user.id,
    ).delete()
    db.commit()
    return {"status": "ok"}


# ── Settings ──
@router.get("/settings", response_model=PushSettings, summary="Get notification settings")
async def get_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _settings_of(user)


@router.patch("/settings", response_model=PushSettings, summary="Update notification settings")
async def update_settings(
    payload: PushSettingsPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.daily_forecast is not None:
        user.push_daily_forecast = payload.daily_forecast
    if payload.daily_time is not None:
        if not _TIME_RE.match(payload.daily_time):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="daily_time must be HH:MM (24h)")
        user.push_daily_time = payload.daily_time
    if payload.quiet_from is not None:
        if not _TIME_RE.match(payload.quiet_from):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="quiet_from must be HH:MM (24h)")
        user.push_quiet_from = payload.quiet_from
    # Пара границ проверяется целиком и ПОСЛЕ присваивания обеих: прислать
    # можно любую одну, и осмысленность у них только совместная. Иначе
    # человек, двигающий только нижнюю границу, молча получил бы пустое окно.
    if payload.daily_time is not None or payload.quiet_from is not None:
        if str(user.push_quiet_from) <= str(user.push_daily_time):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="quiet_from must be later than daily_time",
            )
    if payload.planner is not None:
        user.push_planner = payload.planner
    if payload.key_transits is not None:
        user.push_key_transits = payload.key_transits
    if payload.moon_phases is not None:
        user.push_moon_phases = payload.moon_phases
    if payload.timezone is not None:
        tz = valid_timezone(payload.timezone)
        if tz is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="timezone must be an IANA name")
        user.device_timezone = tz

    db.commit()
    db.refresh(user)
    return _settings_of(user)


# ── Будущие события для локальных уведомлений ──
@router.get("/upcoming", summary="Upcoming notification events for on-device scheduling")
async def upcoming(
    days: int = UPCOMING_DEFAULT_DAYS,
    tz: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """События ближайших дней с готовым заголовком и телом уведомления.

    Мобильное приложение планирует локальные уведомления НА УСТРОЙСТВЕ и
    заранее — до него планировщик веб-пушей не достаёт. Логика отбора и
    формулировки при этом остаются в одном экземпляре: ручка вызывает тот же
    `_collect_candidates`, что и планировщик (см. докстринг
    `collect_upcoming` — там же про `key` и про то, что сюда СОЗНАТЕЛЬНО не
    перенесено).

    ⚠️ `asyncio.to_thread` здесь обязателен, а не для красоты. Внутри —
    синхронный Swiss Ephemeris (транзиты, проходы по домам) на КАЖДЫЙ день
    окна, а `api` это один процесс с одним event loop на все запросы разом
    (CLAUDE.md, раздел про pyswisseph). Прямой вызов заблокировал бы чат,
    чужие интерпретации и health-check на всё время расчёта.
    """
    if days < 1 or days > UPCOMING_MAX_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"days must be between 1 and {UPCOMING_MAX_DAYS}",
        )
    return await asyncio.to_thread(collect_upcoming, db, user, days, valid_timezone(tz))


# ── Test push ──
@router.post("/test", summary="Send a test push to the current user")
async def send_test(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delivered = send_to_user(db, user.id, {
        "title": "✦ Aristea",
        "body": "Тестовое уведомление — всё работает!",
        "url": "/",
    })
    if delivered == 0:
        raise HTTPException(status_code=404, detail="No active subscriptions")
    return {"delivered": delivered}
