"""Push API — подписки и настройки уведомлений.

Endpoints:
  GET   /api/v1/push/vapid-public-key   — публичный VAPID-ключ для фронта (без авторизации)
  POST  /api/v1/push/subscribe          — сохранить подписку устройства (auth)
  POST  /api/v1/push/unsubscribe        — удалить подписку по endpoint (auth)
  GET   /api/v1/push/settings           — настройки уведомлений (auth)
  PATCH /api/v1/push/settings           — обновить настройки (auth)
  POST  /api/v1/push/test               — тестовый пуш себе (auth)

Подключается отдельной строкой в main.py.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, PushSubscription
from backend.auth.dependencies import get_current_user
from backend.push.sender import vapid_public_key, send_to_user

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


class PushSettings(BaseModel):
    daily_forecast: bool
    daily_time: str
    planner: bool
    key_transits: bool

    class Config:
        from_attributes = True


class PushSettingsPatch(BaseModel):
    daily_forecast: Optional[bool] = None
    daily_time: Optional[str] = None
    planner: Optional[bool] = None
    key_transits: Optional[bool] = None


def _settings_of(user: User) -> PushSettings:
    return PushSettings(
        daily_forecast=bool(getattr(user, "push_daily_forecast", True)),
        daily_time=str(getattr(user, "push_daily_time", "08:00") or "08:00"),
        planner=bool(getattr(user, "push_planner", True)),
        key_transits=bool(getattr(user, "push_key_transits", True)),
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
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="daily_time must be HH:MM (24h)")
        user.push_daily_time = payload.daily_time
    if payload.planner is not None:
        user.push_planner = payload.planner
    if payload.key_transits is not None:
        user.push_key_transits = payload.key_transits

    db.commit()
    db.refresh(user)
    return _settings_of(user)


# ── Test push ──
@router.post("/test", summary="Send a test push to the current user")
async def send_test(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delivered = send_to_user(db, user.id, {
        "title": "✦ Astrea",
        "body": "Тестовое уведомление — всё работает!",
        "url": "/",
    })
    if delivered == 0:
        raise HTTPException(status_code=404, detail="No active subscriptions")
    return {"delivered": delivered}
