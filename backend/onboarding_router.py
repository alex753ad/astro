"""Onboarding email scheduler endpoint.
Call daily via Railway Cron: POST /api/v1/internal/onboarding-emails
Protected by X-Internal-Secret header.
"""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import timedelta
from backend.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.authz import require_internal_secret
from backend.database import get_db
from backend.models import User, NatalChart
from backend.email_service import send_retention_day2, send_retention_day7

logger = logging.getLogger("astro.onboarding")

# Секрет проверяется на уровне роутера: все маршруты здесь служебные (cron), и
# при добавлении нового он не окажется случайно открытым.
router = APIRouter(
    prefix="/api/v1/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_secret)],
)

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


def _latest_charts_by_user(db: Session, user_ids: list[str]) -> dict[str, NatalChart]:
    """Последняя карта каждого пользователя — одним запросом, а не в цикле.

    Раньше цикл по когорте дня 2/7 делал отдельный SELECT на каждого юзера
    (`db.query(NatalChart).filter(user_id == user.id)...first()`): на когорте в
    тысячу регистраций — тысяча запросов к БД на один прогон крона.
    """
    if not user_ids:
        return {}
    latest = (
        db.query(NatalChart.user_id, func.max(NatalChart.created_at).label("max_created"))
        .filter(NatalChart.user_id.in_(user_ids))
        .group_by(NatalChart.user_id)
        .subquery()
    )
    charts = (
        db.query(NatalChart)
        .join(
            latest,
            (NatalChart.user_id == latest.c.user_id)
            & (NatalChart.created_at == latest.c.max_created),
        )
        .all()
    )
    # При двух картах с одинаковым created_at (микросекундная коллизия) join
    # вернёт обе — берём любую детерминированно последней записью в словаре.
    return {c.user_id: c for c in charts}


@router.post("/onboarding-emails")
async def send_onboarding_emails(
    db: Session = Depends(get_db),
):
    now = utcnow()
    day2_start = now - timedelta(days=2, hours=1)
    day2_end   = now - timedelta(days=1, hours=23)
    day7_start = now - timedelta(days=7, hours=1)
    day7_end   = now - timedelta(days=6, hours=23)

    sent_day2 = sent_day7 = 0

    # ── Day 2: retention email with active transit ──
    day2_users = db.query(User).filter(User.created_at >= day2_start, User.created_at <= day2_end).all()
    day2_charts = _latest_charts_by_user(db, [u.id for u in day2_users])
    for user in day2_users:
        chart = day2_charts.get(user.id)
        if not chart:
            continue
        try:
            from datetime import date as date_type
            from backend.transit.engine import calculate_transits
            today = date_type.today()
            # Swiss Ephemeris — синхронный, блокирует event loop (см. CLAUDE.md).
            events = await asyncio.to_thread(
                calculate_transits, natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=7)
            )
            event = _pick_best_transit(events)
            if not event:
                continue
            await send_retention_day2(user.email, _build_transit_text(event))
            sent_day2 += 1
        except Exception as e:
            logger.warning("Day2 email failed for %s: %s", user.email, e)

    # ── Day 7: upgrade nudge for free users ──
    day7_users = db.query(User).filter(
        User.created_at >= day7_start, User.created_at <= day7_end, User.tier == "free"
    ).all()
    day7_charts = _latest_charts_by_user(db, [u.id for u in day7_users])
    for user in day7_users:
        chart = day7_charts.get(user.id)
        if not chart:
            continue
        try:
            from datetime import date as date_type
            from backend.transit.engine import calculate_transits
            today = date_type.today()
            # Swiss Ephemeris — синхронный, блокирует event loop (см. CLAUDE.md).
            events = await asyncio.to_thread(
                calculate_transits, natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=30)
            )
            await send_retention_day7(user.email, max(0, len(events) - 1))
            sent_day7 += 1
        except Exception as e:
            logger.warning("Day7 email failed for %s: %s", user.email, e)

    return {"sent_day2": sent_day2, "sent_day7": sent_day7}


async def run_weekly_digest(db: Session) -> dict:
    """Основная логика — переиспользуется HTTP-эндпоинтом ниже и внутренним
    планировщиком в main.py (см. lifespan). Отправляет дайджест пользователям,
    у которых сегодня настроен день получения (digest_day_of_week == today.weekday()).
    """
    from datetime import date as date_type
    from backend.models import User
    from backend.email_service import send_weekly_digest

    today_weekday = date_type.today().weekday()  # 0=пн, 6=вс

    pro_users = db.query(User).filter(
        User.tier.in_(["pro", "premium"]),
        User.digest_day_of_week == today_weekday,
    ).all()
    sent = 0
    for user in pro_users:
        try:
            ok = await send_weekly_digest(user, db)
            if ok:
                sent += 1
        except Exception as e:
            logger.warning("Weekly digest failed for %s: %s", user.email, e)

    return {"sent": sent, "weekday": today_weekday}


@router.post("/weekly-digest")
async def send_weekly_digests(
    db: Session = Depends(get_db),
):
    """Railway Cron: ежедневно 09:00 МСК."""
    return await run_weekly_digest(db)


@router.post("/lunar-returns")
async def trigger_lunar_returns(
    db: Session = Depends(get_db),
):
    """Railway Cron: ежедневно 09:00 МСК.
    Запускает Celery-задачу проверки лунных возвращений.
    """
    try:
        from backend.tasks import check_lunar_returns
        task = check_lunar_returns.delay()
        return {"status": "queued", "task_id": task.id}
    except Exception as e:
        logger.warning("lunar-returns trigger failed: %s", e)
        # Fallback: выполнить синхронно
        from backend.tasks import check_lunar_returns
        result = check_lunar_returns()
        return {"status": "done", **result}
