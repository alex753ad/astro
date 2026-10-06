"""backend/pilot/cron.py — E8 ежедневный тик пилота.

POST /api/v1/internal/pilot-tick   (header X-Internal-Secret)

Проходит по ВСЕМ пользователям с pilot_started_at (не только с push-подпиской —
поэтому отдельный эндпоинт, а не push-tick, который итерирует лишь подписчиков):
  1) Прощание (E8) — за ≤3 дня до конца. Письмо. Идемпотентно (kind=farewell).
  2) Спящий 5/10/14 (E10) — по числу дней без timeline_open, пока пилот активен.
     Один шаг за прогон. Дни 10/14 несут ссылку на exit-survey. (kind=dormant5/10/14)
  3) Даунгрейд (E8) — по истечении 30 дней tier→free. pilot_started_at сохраняем
     (нужен для read-only CRM E9 и end-of-month exit-survey E10).
  4) End-of-month exit-survey (E10) — после конца без продолжения. (kind=exit_eom)

Пушей пилот не шлёт — только письма (решение владельца 01.10.2026: в
приложении по умолчанию только прогноз дня, важные транзиты и планер, а
прощание и «спящий» пушем при лимите 2 в сутки вытесняли бы прогноз).
Не возвращать пуш сюда без пересмотра лимита — docs/notifications.md,
«Главное событие дня и лимит пушей».

Расписание: systemd-таймер astro-pilot-tick (раз в сутки) и, с 05.10.2026,
Celery Beat ежечасно (`tasks.pilot_tick`) — письма пилота уходят только в
окне 09–21 по местному времени (lifecycle_emails.email_window_open, решение
владельца 05.10.2026), а раз в сутки в 06:20 у Нью-Йорка окно не открыто
никогда. Идемпотентность позволяет запускать чаще без дублей.
"""
from __future__ import annotations

import asyncio
import logging

from backend import chart_points as _chart_points  # без времени рождения — без натальной Луны (шаг 3)
import os
from datetime import timedelta, date as date_type
from backend.time_utils import utcnow

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.authz import require_internal_secret
from backend.database import get_db
from backend.models import User, NatalChart, PushSentLog
from backend.email_service import TIER_NAMES
from backend.ephemeris.ru_names import PLANET_RU

logger = logging.getLogger("astro.pilot.cron")

# Секрет проверяется на уровне роутера — см. backend/authz.require_internal_secret.
router = APIRouter(
    prefix="/api/v1/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_secret)],
)

PILOT_DAYS = int(os.getenv("PILOT_DAYS", "30"))
FAREWELL_LEAD_DAYS = 3
# Код на продолжение (пилот пользователя целится в Pro). Premium-код — astroprem90.
PROMO_CODE = os.getenv("CONTINUE_PRO_CODE", "astropro90")
PROMO_OFFER = os.getenv("CONTINUE_PRO_OFFER", f"{TIER_NAMES['pro']} — 690 ₽ в месяц на 3 месяца")
PROMO_DEADLINE = os.getenv("CONTINUE_DEADLINE")     # задаёт админ в панели (см. E8_wiring)

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
    from backend import day_event
    if day_event._sky_on(chart):
        return _sky_windows(chart, user)
    today = date_type.today()
    try:
        events = calculate_transits(
            natal_planets=_chart_points.planets(chart), from_date=today, to_date=today + timedelta(days=30),
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
        out.append(f"{pr} {rng} — влияет на твою карту, посмотри, что делать")
    return out


def _sky_windows(chart, user: User) -> list[str]:
    """`_upcoming_windows` под флагом sky_event (4.12): события ядра медленных
    планет с касанием в ближайшие 30 местных дней; срок — всего события в
    местных датах (без флага начало резалось окном и было «сегодня»).
    Проход без касания (станция) — не окно, как в ленте."""
    from backend.sky import sky_events
    from backend.time_utils import local_day, local_today, user_tz
    from backend.transit.engine import ALERT_PLANETS

    tz = user_tz(None, user, chart)
    today = local_today(tz)
    s, e = local_day(today, tz)[0], local_day(today + timedelta(days=30), tz)[1]
    try:
        events = [ev for ev in sky_events(chart, s, e)
                  if ev.transit in ALERT_PLANETS and any(s <= t.at_utc < e for t in ev.touches)]
    except Exception as ex:
        logger.warning("windows calc failed user=%s: %s", user.id, ex)
        return []
    events.sort(key=lambda ev: ev.start_utc)
    out: list[str] = []
    for ev in events[:3]:
        loc = ev.local(tz)
        start, end = _fmt_day(loc.start_day.isoformat()), _fmt_day(loc.end_day.isoformat())
        rng = f"{start}–{end}" if start != end else start
        out.append(f"{PLANET_RU.get(ev.transit, ev.transit)} {rng} — влияет на твою карту, посмотри, что делать")
    return out


async def _process(db: Session, user: User) -> dict:
    now = utcnow()
    start = user.pilot_started_at
    if not start:
        return {}
    end = start + timedelta(days=PILOT_DAYS)
    result = {}
    # Отписка от писем (068): письмо не шлём, но шаг считаем сделанным
    # (email_ok=True) — иначе он не отметится и пуш рядом с письмом
    # повторялся бы на каждом тике.
    from backend.lifecycle_emails import email_window_open
    from backend.profile.email_unsubscribe import unsubscribe_url
    unsub = unsubscribe_url(user)
    # Письма — только в окне 09–21 местного; вне окна шаг не отмечается и
    # уходит следующим прогоном в окне. Даунгрейд (шаг 3) от окна не зависит.
    window = email_window_open(user, None, now)

    # 1) Прощание за ≤3 дня
    if window and end - timedelta(days=FAREWELL_LEAD_DAYS) <= now < end:
        ref = f"farewell:{end.date().isoformat()}"
        if not _already(db, user.id, "farewell", ref):
            days_left = max(1, (end.date() - now.date()).days)
            # _upcoming_windows считает транзиты через Swiss Ephemeris —
            # синхронно, блокирует event loop api-процесса (см. CLAUDE.md).
            windows = await asyncio.to_thread(_upcoming_windows, db, user)

            # письмо. Раньше здесь стоял asyncio.get_event_loop().run_until_complete()
            # внутри уже запущенного event loop (pilot_tick — async) — гарантированный
            # RuntimeError на каждый вызов, письмо молча не уходило, а _mark ниже
            # писал "отправлено" и хоронил попытку навсегда.
            email_ok = unsub is None
            try:
                from backend.email_service import send_pilot_farewell
                checkout_url = None
                if PROMO_CODE:
                    from backend.config import get_settings
                    checkout_url = f"{get_settings().frontend_url}/profile?upgrade=pro"
                if unsub:
                    email_ok = await send_pilot_farewell(
                        user.email, windows,
                        promo_code=PROMO_CODE, offer_text=PROMO_OFFER,
                        checkout_url=checkout_url,
                        deadline=PROMO_DEADLINE, days_left=days_left,
                        unsubscribe_url=unsub,
                    )
            except Exception as e:
                logger.warning("farewell email failed user=%s: %s", user.id, e)

            # Отмечаем только при успешной отправке письма — иначе транзиентный
            # сбой (сеть, Resend недоступен) хоронит уведомление до конца пилота:
            # следующий тик видит тот же ref и молча пропускает шаг.
            if email_ok:
                _mark(db, user.id, "farewell", ref)
                result["farewell"] = True

    # 2) Спящий 5/10/14 — только пока пилот активен (юзер платно не пользуется)
    if window and now < end:
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

                email_ok = unsub is None
                try:
                    from backend.email_service import send_dormant
                    if unsub:
                        email_ok = await send_dormant(
                            user.email, step,
                            window=near,
                            missed_count=(len(windows) or None),
                            survey_url=survey_url,
                            unsubscribe_url=unsub,
                        )
                except Exception as e:
                    logger.warning("dormant%s email failed user=%s: %s", step, user.id, e)

                if email_ok:
                    _mark(db, user.id, f"dormant{step}", cohort)
                    result["dormant"] = step
                break  # один шаг за прогон (даже если письмо не ушло — не залипаем на нём весь тик)

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
    if window and now >= end and (user.tier or "free") == "free":
        ref = f"eom:{end.date().isoformat()}"
        if not _already(db, user.id, "exit_eom", ref):
            email_ok = unsub is None
            try:
                from backend.email_service import send_end_of_month_survey
                if unsub:
                    email_ok = await send_end_of_month_survey(
                        user.email, _survey_url(user, "end_of_month"),
                        unsubscribe_url=unsub,
                    )
            except Exception as e:
                logger.warning("eom survey email failed user=%s: %s", user.id, e)
            if email_ok:
                _mark(db, user.id, "exit_eom", ref)
                result["eom_survey"] = True

    return result


@router.post("/pilot-tick")
async def pilot_tick(
    db: Session = Depends(get_db),
):
    return await run_tick(db)


async def run_tick(db: Session) -> dict:
    """Один прогон пилота — ручка (systemd) и Celery Beat (`tasks.pilot_tick`)."""
    users = db.query(User).filter(User.pilot_started_at.isnot(None)).all()
    farewell = downgraded = dormant = eom = 0
    for user in users:
        try:
            r = await _process(db, user)
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
