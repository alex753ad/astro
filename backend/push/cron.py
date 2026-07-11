"""Push scheduler — internal cron endpoint.

Вызывается Railway Cron каждые ~15 минут:
  POST /api/v1/internal/push-tick   (header X-Internal-Secret)

Для каждого пользователя с активной подпиской, по его ГЛАВНОЙ карте
(primary_chart_id), в его локальное время (tz главной карты):
  1) Ежедневный прогноз — в выбранное пользователем время (push_daily_time).
  2) Планер — когда сегодня начинается новый период планеты (заход в дом).
  3) Важные транзиты — когда сегодня начинается значимый транзит.

Все три отправляются в утреннее «окно» пользователя (>= push_daily_time),
дедуплицируются через push_sent_log (одно событие — один пуш).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, date as date_type, timedelta

import pytz
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, NatalChart, PushSubscription, PushSentLog
from backend.push.sender import send_to_user

logger = logging.getLogger("astro.push.cron")

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])

DEFAULT_TZ = "Europe/Moscow"

PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн",
    "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон",
    "North Node": "Сев. узел", "Ascendant": "Асцендент", "Midheaven": "MC",
}
ASPECT_RU = {
    "conjunction": "соединение", "sextile": "секстиль",
    "square": "квадрат", "trine": "трин", "opposition": "оппозиция",
}
FAST_PLANETS = ("Sun", "Mercury", "Venus", "Mars")


# ── Дедупликация ──
def _already_sent(db: Session, user_id: str, kind: str, ref_key: str) -> bool:
    return db.query(PushSentLog).filter(
        PushSentLog.user_id == user_id,
        PushSentLog.kind == kind,
        PushSentLog.ref_key == ref_key,
    ).first() is not None


def _mark_sent(db: Session, user_id: str, kind: str, ref_key: str) -> None:
    db.add(PushSentLog(user_id=user_id, kind=kind, ref_key=ref_key[:128]))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # уже отмечено параллельным тиком


# ── Тексты ──
def _daily_body(chart: NatalChart, today: date_type) -> str:
    """Короткий тизер прогноза на день из активных транзитов (без AI)."""
    try:
        from backend.transit.engine import calculate_transits
        events = calculate_transits(
            natal_planets=chart.planets, from_date=today, to_date=today
        )
        best = None
        for e in events:
            if e.aspect_type in ("trine", "sextile", "conjunction"):
                best = e
                break
        best = best or (events[0] if events else None)
        if best:
            p = PLANET_RU.get(best.transit_planet, best.transit_planet)
            n = PLANET_RU.get(best.natal_planet, best.natal_planet)
            a = ASPECT_RU.get(best.aspect_type, best.aspect_type)
            return f"Сегодня {p} {a} к вашему {n}. Загляните в прогноз на день."
    except Exception as e:
        logger.warning("daily body build failed: %s", e)
    return "Ваш персональный прогноз на сегодня готов."


# ── Основная логика по одному пользователю ──
def _process_user(db: Session, user: User) -> int:
    chart = None
    if user.primary_chart_id:
        chart = db.query(NatalChart).filter(NatalChart.id == user.primary_chart_id).first()
    if not chart:
        return 0  # без главной карты уведомлять не по чему

    tzname = getattr(chart, "timezone", None) or DEFAULT_TZ
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone(DEFAULT_TZ)

    now_local = datetime.now(pytz.utc).astimezone(tz)
    today = now_local.date()

    target = str(getattr(user, "push_daily_time", "08:00") or "08:00")
    try:
        th, tm = (int(x) for x in target.split(":"))
    except Exception:
        th, tm = 8, 0
    # Утреннее окно: работаем только когда локальное время уже наступило.
    if (now_local.hour, now_local.minute) < (th, tm):
        return 0

    sent = 0

    # 1) Ежедневный прогноз
    if getattr(user, "push_daily_forecast", True):
        ref = today.isoformat()
        if not _already_sent(db, user.id, "daily", ref):
            n = send_to_user(db, user.id, {
                "title": "✦ Прогноз на сегодня",
                "body": _daily_body(chart, today),
                "url": "/home",
            })
            if n:
                _mark_sent(db, user.id, "daily", ref)
                sent += n

    # 2) Планер — старт нового периода планеты (заход в дом сегодня)
    if getattr(user, "push_planner", True):
        try:
            from backend.transit.house_passages import calculate_house_passages, _extract_cusps
            cusps = _extract_cusps({"houses": chart.houses})
            if not all(c == 0.0 for c in cusps):
                win_start = datetime(today.year, today.month, today.day) - timedelta(days=1)
                win_end = datetime(today.year, today.month, today.day) + timedelta(days=1, hours=23)
                for planet in FAST_PLANETS:
                    passages = calculate_house_passages(planet, cusps, win_start, win_end)
                    for p in passages:
                        start = p["start_dt"].date()
                        if start != today:
                            continue
                        ref = f"{planet}:{p['house']}:{start.isoformat()}"
                        if _already_sent(db, user.id, "planner", ref):
                            continue
                        pr = PLANET_RU.get(planet, planet)
                        n = send_to_user(db, user.id, {
                            "title": "✦ Планер",
                            "body": f"{pr}: начался новый период (дом {p['house']}).",
                            "url": f"/planner/{chart.id}",
                        })
                        if n:
                            _mark_sent(db, user.id, "planner", ref)
                            sent += n
        except Exception as e:
            logger.warning("planner push failed user=%s: %s", user.id, e)

    # 3) Важные транзиты — старт значимого транзита сегодня
    if getattr(user, "push_key_transits", True):
        try:
            from backend.transit.engine import calculate_transits, ALERT_PLANETS
            events = calculate_transits(
                natal_planets=chart.planets, from_date=today, to_date=today
            )
            for e in events:
                if e.transit_planet not in ALERT_PLANETS:
                    continue
                if e.start_date != today.isoformat():
                    continue
                ref = f"{e.transit_planet}:{e.natal_planet}:{e.aspect_type}:{e.start_date}"
                if _already_sent(db, user.id, "transit", ref):
                    continue
                pr = PLANET_RU.get(e.transit_planet, e.transit_planet)
                nr = PLANET_RU.get(e.natal_planet, e.natal_planet)
                ar = ASPECT_RU.get(e.aspect_type, e.aspect_type)
                n = send_to_user(db, user.id, {
                    "title": "✦ Важный транзит",
                    "body": f"{pr} {ar} к вашему {nr} — начинается значимый транзит.",
                    "url": f"/planner/{chart.id}",
                })
                if n:
                    _mark_sent(db, user.id, "transit", ref)
                    sent += n
        except Exception as e:
            logger.warning("transit push failed user=%s: %s", user.id, e)

    return sent


@router.post("/push-tick")
async def push_tick(
    x_internal_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    secret = os.getenv("INTERNAL_SECRET", "")
    if secret and x_internal_secret != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Только пользователи с хотя бы одной подпиской
    user_ids = [row[0] for row in db.query(PushSubscription.user_id).distinct().all()]
    if not user_ids:
        return {"users": 0, "delivered": 0}

    total = 0
    processed = 0
    for user in db.query(User).filter(User.id.in_(user_ids)).all():
        try:
            total += _process_user(db, user)
            processed += 1
        except Exception as e:
            logger.warning("push-tick user=%s failed: %s", user.id, e)
            db.rollback()

    return {"users": processed, "delivered": total}
