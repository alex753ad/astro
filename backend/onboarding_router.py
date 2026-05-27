"""Onboarding email scheduler endpoint.
Call daily via Railway Cron: POST /api/v1/internal/onboarding-emails
Protected by X-Internal-Secret header.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, NatalChart
from backend.email_service import send_retention_day2, send_retention_day7

logger = logging.getLogger("astro.onboarding")

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])

PLANET_LABELS_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий",
    "Venus": "Венера", "Mars": "Марс", "Jupiter": "Юпитер",
    "Saturn": "Сатурн", "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон",
}
ASPECT_LABELS_RU = {
    "conjunction": "соединение", "sextile": "секстиль",
    "square": "квадрат", "trine": "трин", "opposition": "оппозиция",
}
POSITIVE_ASPECTS = {"trine", "sextile", "conjunction"}
POSITIVE_PLANETS = {"Venus", "Jupiter", "Sun"}

TRANSIT_TEMPLATES = {
    ("Venus",   "trine"):       "Венера образует гармоничный трин — прекрасное время для отношений, творчества и приятных встреч.",
    ("Venus",   "sextile"):     "Венера в секстиле открывает возможности для новых знакомств и укрепления связей.",
    ("Venus",   "conjunction"): "Венера в соединении усиливает вашу привлекательность и желание гармонии.",
    ("Jupiter", "trine"):       "Юпитер в трине приносит удачу и расширение возможностей — действуйте смело.",
    ("Jupiter", "sextile"):     "Юпитер в секстиле открывает двери там, где раньше были препятствия.",
    ("Jupiter", "conjunction"): "Юпитер в соединении — один из лучших транзитов года. Энергия роста на максимуме.",
    ("Sun",     "trine"):       "Солнечный трин наполняет энергией и уверенностью в собственных силах.",
    ("Mars",    "trine"):       "Марс в трине даёт прилив сил и решимости — отличный момент для активных действий.",
}


def _pick_best_transit(events: list):
    for e in events:
        tp = getattr(e, "transit_planet", None)
        at = getattr(e, "aspect_type", None)
        if tp in POSITIVE_PLANETS and at in POSITIVE_ASPECTS:
            return e
    for e in events:
        if getattr(e, "aspect_type", None) in {"trine", "sextile"}:
            return e
    return events[0] if events else None


def _build_transit_text(event) -> str:
    tp = getattr(event, "transit_planet", "")
    np = getattr(event, "natal_planet", "")
    at = getattr(event, "aspect_type", "")
    template = TRANSIT_TEMPLATES.get((tp, at), "")
    planet_ru = PLANET_LABELS_RU.get(tp, tp)
    natal_ru  = PLANET_LABELS_RU.get(np, np)
    aspect_ru = ASPECT_LABELS_RU.get(at, at)
    base = f"Сегодня <strong>{planet_ru}</strong> образует {aspect_ru} с вашим натальным <strong>{natal_ru}</strong>."
    return f"{base}<br><br>{template}" if template else base


@router.post("/onboarding-emails")
async def send_onboarding_emails(
    x_internal_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    secret = os.getenv("INTERNAL_SECRET", "")
    if secret and x_internal_secret != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    now = datetime.utcnow()
    day2_start = now - timedelta(days=2, hours=1)
    day2_end   = now - timedelta(days=1, hours=23)
    day7_start = now - timedelta(days=7, hours=1)
    day7_end   = now - timedelta(days=6, hours=23)

    sent_day2 = sent_day7 = 0

    # ── Day 2: retention email with active transit ──
    for user in db.query(User).filter(User.created_at >= day2_start, User.created_at <= day2_end).all():
        chart = db.query(NatalChart).filter(NatalChart.user_id == user.id).order_by(NatalChart.created_at.desc()).first()
        if not chart:
            continue
        try:
            from datetime import date as date_type
            from backend.transit.engine import calculate_transits
            today = date_type.today()
            events = calculate_transits(natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=7))
            event = _pick_best_transit(events)
            if not event:
                continue
            await send_retention_day2(user.email, _build_transit_text(event))
            sent_day2 += 1
        except Exception as e:
            logger.warning("Day2 email failed for %s: %s", user.email, e)

    # ── Day 7: upgrade nudge for free users ──
    for user in db.query(User).filter(User.created_at >= day7_start, User.created_at <= day7_end, User.tier == "free").all():
        chart = db.query(NatalChart).filter(NatalChart.user_id == user.id).order_by(NatalChart.created_at.desc()).first()
        if not chart:
            continue
        try:
            from datetime import date as date_type
            from backend.transit.engine import calculate_transits
            today = date_type.today()
            events = calculate_transits(natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=30))
            await send_retention_day7(user.email, max(0, len(events) - 1))
            sent_day7 += 1
        except Exception as e:
            logger.warning("Day7 email failed for %s: %s", user.email, e)

    return {"sent_day2": sent_day2, "sent_day7": sent_day7}
