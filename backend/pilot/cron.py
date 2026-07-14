"""backend/pilot/cron.py — E8 ежедневный тик пилота.

POST /api/v1/internal/pilot-tick   (header X-Internal-Secret)

Проходит по ВСЕМ пользователям с pilot_started_at (не только с push-подпиской —
поэтому отдельный эндпоинт, а не push-tick, который итерирует лишь подписчиков):
  1) Прощание (E8) — за ≤3 дня до конца. Письмо+пуш. Идемпотентно (kind=farewell).
  2) Спящий 5/10/14 (E10) — по числу дней без timeline_open, пока пилот активен.
     Один шаг за прогон. Дни 10/14 несут ссылку на exit-survey. (kind=dormant5/10/14)
  3) Даунгрейд (E8) — по истечении 30 дней tier→free. pilot_started_at сохраняем
     (нужен для read-only CRM E9 и end-of-month exit-survey E10).
  4) End-of-month exit-survey (E10) — после конца без продолжения. (kind=exit_eom)

Расписание Railway Cron: раз в день (напр. 09:10). Идемпотентность позволяет
запускать чаще без дублей.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, date as date_type

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, NatalChart, PushSentLog
from backend.push.sender import send_to_user

logger = logging.getLogger("astro.pilot.cron")

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])

PILOT_DAYS = int(os.getenv("PILOT_DAYS", "30"))
FAREWELL_LEAD_DAYS = 3
# Код на продолжение (пилот пользователя целится в Pro). Premium-код — astroprem90.
PROMO_CODE = os.getenv("CONTINUE_PRO_CODE", "astropro90")
PROMO_OFFER = os.getenv("CONTINUE_PRO_OFFER", "Pro — 690 ₽ в месяц на 3 месяца")
PROMO_DEADLINE = os.getenv("CONTINUE_DEADLINE")     # задаёт админ в панели (см. E8_wiring)

PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн",
    "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон",
}
_MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _fmt_day(iso: str) -> str:
    """'2026-07-24' → '24 июля'."""
    try:
        d = date_type.fromisoformat(iso[:10])
        return f"{d.day} {_MONTHS[d.month]}"
    except Exception:
        return iso


def _already(db, uid, kind, ref) -> bool:
    return db.query(PushSentLog).filter(
        PushSentLog.user_id == uid, PushSentLog.kind == kind,
        PushSentLog.ref_key == ref,
    ).first() is not None


def _mark(db, uid, kind, ref) -> None:
    from sqlalchemy.exc import IntegrityError
    db.add(PushSentLog(user_id=uid, kind=kind, ref_key=ref[:128]))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _last_open_date(db: Session, user: User):
    """Дата последнего timeline_open; если не было — дата старта пилота."""
    from backend.models import Event
    row = (
        db.query(Event.ts)
        .filter(Event.user_id == user.id, Event.name == "timeline_open")
        .order_by(Event.ts.desc())
        .first()
    )
    if row and row[0]:
        return row[0].date()
    return user.pilot_started_at.date() if user.pilot_started_at else None


def _survey_url(user: User, moment: str) -> str:
    from backend.config import get_settings
    base = get_settings().frontend_url.rstrip("/")
    return f"{base}/exit-survey?m={moment}&u={user.id}"


def _upcoming_windows(db: Session, user: User) -> list[str]:
    """1–3 ближайших значимых окна пользователя (для персонального прощания)."""
    from backend.tasks import _get_primary_chart
    from backend.transit.engine import calculate_transits, ALERT_PLANETS

    chart = _get_primary_chart(db, user)
    if not chart or not chart.planets:
        return []
    today = date_type.today()
    try:
        events = calculate_transits(
            natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=30),
        )
    except Exception as e:
        logger.warning("windows calc failed user=%s: %s", user.id, e)
        return []

    # значимые: медленные/алерт-планеты, ближайшие по дате
    sig = [e for e in events if getattr(e, "transit_planet", "") in ALERT_PLANETS]
    sig.sort(key=lambda e: str(getattr(e, "start_date", "") or ""))
    out: list[str] = []
    for e in sig[:3]:
        pr = PLANET_RU.get(e.transit_planet, e.transit_planet)
        start = _fmt_day(str(getattr(e, "start_date", "") or ""))
        end = _fmt_day(str(getattr(e, "end_date", "") or ""))
        rng = f"{start}–{end}" if start and end and start != end else (start or end)
        out.append(f"{pr} {rng} — активное окно по вашей карте")
    return out


def _process(db: Session, user: User) -> dict:
    now = datetime.utcnow()
    start = user.pilot_started_at
    if not start:
        return {}
    end = start + timedelta(days=PILOT_DAYS)
    result = {}

    # 1) Прощание за ≤3 дня
    if end - timedelta(days=FAREWELL_LEAD_DAYS) <= now < end:
        ref = f"farewell:{end.date().isoformat()}"
        if not _already(db, user.id, "farewell", ref):
            days_left = max(1, (end.date() - now.date()).days)
            windows = _upcoming_windows(db, user)

            # письмо
            try:
                import asyncio
                from backend.email_service import send_pilot_farewell
                checkout_url = None
                if PROMO_CODE:
                    from backend.config import get_settings
                    checkout_url = f"{get_settings().frontend_url}/profile?upgrade=pro"
                asyncio.get_event_loop().run_until_complete(
                    send_pilot_farewell(
                        user.email, windows,
                        promo_code=PROMO_CODE, offer_text=PROMO_OFFER,
                        checkout_url=checkout_url,
                        deadline=PROMO_DEADLINE, days_left=days_left,
                    )
                )
            except Exception as e:
                logger.warning("farewell email failed user=%s: %s", user.id, e)

            # пуш (если есть подписка)
            try:
                near = windows[0] if windows else "важное окно вашей карты"
                send_to_user(db, user.id, {
                    "title": "✦ Ваш месяц заканчивается",
                    "body": f"Через {days_left} дн. {near} закроется для вас. Это окно стоит того, чтобы его не потерять.",
                    "url": "/profile",
                })
            except Exception as e:
                logger.warning("farewell push failed user=%s: %s", user.id, e)

            _mark(db, user.id, "farewell", ref)
            result["farewell"] = True

    # 2) Спящий 5/10/14 — только пока пилот активен (юзер платно не пользуется)
    if now < end:
        last = _last_open_date(db, user)
        if last is not None:
            inactive = (now.date() - last).days
            cohort = start.date().isoformat()
            for step in (5, 10, 14):
                if inactive < step:
                    break
                if _already(db, user.id, f"dormant{step}", cohort):
                    continue
                # шлём один (самый низкий неотправленный) шаг за прогон
                windows = _upcoming_windows(db, user)
                near = windows[0] if windows else None
                survey_url = _survey_url(user, "dormant") if step in (10, 14) else None

                try:
                    import asyncio
                    from backend.email_service import send_dormant
                    asyncio.get_event_loop().run_until_complete(
                        send_dormant(
                            user.email, step,
                            window=near,
                            missed_count=(len(windows) or None),
                            survey_url=survey_url,
                        )
                    )
                except Exception as e:
                    logger.warning("dormant%s email failed user=%s: %s", step, user.id, e)

                try:
                    body = {
                        5:  f"Вы не заходили 5 дней. {near or 'В карте идёт активное окно'} — не пропустите.",
                        10: "10 дней без Timeline. Если что-то не так — расскажите, это 30 секунд.",
                        14: "Последнее напоминание. Ваша карта будет ждать, если захотите вернуться.",
                    }[step]
                    send_to_user(db, user.id, {
                        "title": "✦ Astrea", "body": body, "url": "/planner",
                    })
                except Exception as e:
                    logger.warning("dormant%s push failed user=%s: %s", step, user.id, e)

                _mark(db, user.id, f"dormant{step}", cohort)
                result["dormant"] = step
                break  # один шаг за прогон

    # 3) Даунгрейд после конца
    if now >= end and user.tier != "free":
        user.tier = "free"
        db.add(user)
        db.commit()
        try:
            from backend.metrics import log_event
            log_event(db, user.id, "pilot_downgraded", {"ended": end.date().isoformat()})
        except Exception:
            pass
        result["downgraded"] = True

    # 4) End-of-month exit-survey — момент 3: месяц кончился, продолжения нет
    if now >= end and (user.tier or "free") == "free":
        ref = f"eom:{end.date().isoformat()}"
        if not _already(db, user.id, "exit_eom", ref):
            try:
                import asyncio
                from backend.email_service import send_end_of_month_survey
                asyncio.get_event_loop().run_until_complete(
                    send_end_of_month_survey(user.email, _survey_url(user, "end_of_month"))
                )
            except Exception as e:
                logger.warning("eom survey email failed user=%s: %s", user.id, e)
            _mark(db, user.id, "exit_eom", ref)
            result["eom_survey"] = True

    return result


@router.post("/pilot-tick")
async def pilot_tick(
    x_internal_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    secret = os.getenv("INTERNAL_SECRET", "")
    if secret and x_internal_secret != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    users = db.query(User).filter(User.pilot_started_at.isnot(None)).all()
    farewell = downgraded = dormant = eom = 0
    for user in users:
        try:
            r = _process(db, user)
            farewell += 1 if r.get("farewell") else 0
            downgraded += 1 if r.get("downgraded") else 0
            dormant += 1 if r.get("dormant") else 0
            eom += 1 if r.get("eom_survey") else 0
        except Exception as e:
            logger.warning("pilot-tick user=%s failed: %s", user.id, e)
            db.rollback()

    return {
        "users": len(users), "farewell_sent": farewell, "downgraded": downgraded,
        "dormant_sent": dormant, "eom_survey_sent": eom,
    }
