"""backend/metrics.py — E11 трекинг пилота.

Лёгкий журнал событий (таблица `events`) + расчёт метрик из стратегии §12:
  Группа 1 — привычка: D1/D3/D7/D14/D30 retention по пилот-когорте.
  Группа 2 — воронка: register → chart → first_interpretation → second_visit.
  Группа 3 — астролог: ≥5 клиентов, консультация через бриф, заход по алерту.
  Группа 4 — остаться самим: активация промокода (+ exit-причины из E10).

log_event() устойчив: любые ошибки логирования НЕ ломают основной запрос.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("astro.metrics")


# ── Канон имён событий (чтобы не расходились строки по кодовой базе) ──
class EventName:
    # Группа 1 — привычка
    TIMELINE_OPEN = "timeline_open"            # открыт планер/Timeline (основа retention)
    # Группа 2 — воронка
    REGISTER = "register"                      # регистрация
    CHART_CREATED = "chart_created"            # построена первая карта
    FIRST_INTERPRETATION = "first_interpretation"  # достигнут первый AI-разбор
    SECOND_VISIT = "second_visit"              # второй заход (другой день)
    # Группа 3 — астролог
    CRM_CLIENT_ADDED = "crm_client_added"
    CRM_CONSULTATION_BRIEF = "crm_consultation_via_brief"
    CRM_ALERT_OPENED = "crm_alert_opened"
    # Группа 4 — остаться самим
    PROMO_ACTIVATED = "promo_activated"


def maybe_mark_second_visit(db: Session, user_id: Optional[str]) -> bool:
    """Строгий «второй заход»: возврат в Timeline в ДРУГОЙ календарный день.

    Вызывать сразу после записи TIMELINE_OPEN. Пишет SECOND_VISIT один раз,
    только если у пользователя уже был timeline_open в иную дату, чем сегодня.
    Возвращает True, если событие записано впервые.
    """
    from backend.models import Event
    if user_id is None:
        return False
    try:
        # уже отмечен?
        if db.query(Event.id).filter(
            Event.user_id == user_id, Event.name == EventName.SECOND_VISIT
        ).first():
            return False

        today = date.today()
        # был ли timeline_open в любой день, кроме сегодняшнего?
        prior_days = (
            db.query(Event.ts)
            .filter(Event.user_id == user_id, Event.name == EventName.TIMELINE_OPEN)
            .all()
        )
        has_other_day = any(
            ts is not None and ts.date() != today for (ts,) in prior_days
        )
        if not has_other_day:
            return False

        db.add(Event(user_id=user_id, name=EventName.SECOND_VISIT))
        db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("maybe_mark_second_visit failed user=%s: %s", user_id, e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def log_event(
    db: Session,
    user_id: Optional[str],
    name: str,
    meta: Optional[dict] = None,
) -> None:
    """Записать событие. Никогда не бросает — метрики не должны ронять запрос."""
    from backend.models import Event
    try:
        db.add(Event(user_id=user_id, name=name, meta=meta))
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("log_event failed name=%s user=%s: %s", name, user_id, e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def log_event_once(
    db: Session,
    user_id: Optional[str],
    name: str,
    meta: Optional[dict] = None,
) -> bool:
    """Записать событие, только если такого имени у пользователя ещё не было.

    Для «первых» событий воронки (first_interpretation, second_visit).
    Возвращает True, если событие записано впервые.
    """
    from backend.models import Event
    if user_id is None:
        return False
    try:
        exists = (
            db.query(Event.id)
            .filter(Event.user_id == user_id, Event.name == name)
            .first()
        )
        if exists:
            return False
        db.add(Event(user_id=user_id, name=name, meta=meta))
        db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("log_event_once failed name=%s user=%s: %s", name, user_id, e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


# ══════════════════════════════════════════════════════════════════
# РАСЧЁТ МЕТРИК (для admin/stats_router)
# ══════════════════════════════════════════════════════════════════

RETENTION_DAYS = (1, 3, 7, 14, 30)


def _cohort_start(user) -> Optional[date]:
    """Начало отсчёта для retention: пилот, иначе регистрация."""
    base = getattr(user, "pilot_started_at", None) or getattr(user, "created_at", None)
    if base is None:
        return None
    return base.date() if isinstance(base, datetime) else base


def compute_retention(db: Session) -> dict:
    """D1–D30 retention по пилот-когорте.

    Пользователь «удержан на DN», если у него есть timeline_open в календарный
    день (cohort_start + N). Знаменатель DN — те, для кого этот день уже наступил
    (иначе метрика недосчитана). Возвращает по каждому DN: retained/eligible/pct.
    """
    from backend.models import User, Event

    today = date.today()

    # берём пилот-когорту, если она есть; иначе всех пользователей
    users = db.query(User).filter(User.pilot_started_at.isnot(None)).all()
    if not users:
        users = db.query(User).all()

    starts: dict[str, date] = {}
    for u in users:
        s = _cohort_start(u)
        if s is not None:
            starts[u.id] = s

    if not starts:
        return {f"d{n}": {"retained": 0, "eligible": 0, "pct": 0} for n in RETENTION_DAYS}

    # все timeline_open этих пользователей, сгруппированные по (user, дата)
    rows = (
        db.query(Event.user_id, Event.ts)
        .filter(Event.name == EventName.TIMELINE_OPEN)
        .filter(Event.user_id.in_(list(starts.keys())))
        .all()
    )
    open_days: dict[str, set] = {}
    for uid, ts in rows:
        if ts is None:
            continue
        open_days.setdefault(uid, set()).add(ts.date())

    out: dict[str, dict] = {}
    for n in RETENTION_DAYS:
        retained = 0
        eligible = 0
        for uid, start in starts.items():
            target = start + timedelta(days=n)
            if target > today:
                continue  # день ещё не наступил — не учитываем в знаменателе
            eligible += 1
            if target in open_days.get(uid, ()):
                retained += 1
        pct = round(retained / eligible * 100) if eligible else 0
        out[f"d{n}"] = {"retained": retained, "eligible": eligible, "pct": pct}
    return out


def compute_funnel(db: Session) -> dict:
    """Воронка до ценности: register → chart → first_interpretation → second_visit.

    register / chart_created / first_interpretation считаются ИЗ ТАБЛИЦ —
    инструментация задеплоенных эндпоинтов не нужна (карта создаётся анонимно,
    интерпретация тоже может быть анонимной; привязка к юзеру — через chart.user_id):
      - registered           = count(User)
      - chart_created        = distinct NatalChart.user_id (карта привязана к юзеру)
      - first_interpretation = distinct пользователей с Interpretation (через chart)
    second_visit — поведенческий, только из событий (timeline_open в другой день).
    """
    from sqlalchemy import func
    from backend.models import User, NatalChart, Event

    registered = db.query(func.count(User.id)).scalar() or 0

    chart = (
        db.query(func.count(func.distinct(NatalChart.user_id)))
        .filter(NatalChart.user_id.isnot(None))
        .scalar()
        or 0
    )

    try:
        from backend.models import Interpretation
        first_interp = (
            db.query(func.count(func.distinct(NatalChart.user_id)))
            .join(Interpretation, Interpretation.chart_id == NatalChart.id)
            .filter(NatalChart.user_id.isnot(None))
            .scalar()
            or 0
        )
    except Exception:
        first_interp = 0

    second = (
        db.query(func.count(func.distinct(Event.user_id)))
        .filter(Event.name == EventName.SECOND_VISIT)
        .scalar()
        or 0
    )

    def pct(part: int, whole: int) -> int:
        return round(part / whole * 100) if whole else 0

    return {
        "registered": registered,
        "chart_created": chart,
        "first_interpretation": first_interp,
        "second_visit": second,
        "drop": {
            "register_to_chart_pct": pct(chart, registered),
            "chart_to_interp_pct": pct(first_interp, chart),
            "interp_to_second_pct": pct(second, first_interp),
        },
    }


def compute_astrologer_metrics(db: Session) -> dict:
    """Группа 3 — поведение астролога.

    ≥5 клиентов: по факту записей в client_profiles (не зависит от событий).
    Консультация через бриф / заход по алерту: по событиям (E9/E8 инструментируют).
    """
    from sqlalchemy import func
    from backend.models import AstrologerProfile, ClientProfile, Event

    counts = dict(
        db.query(ClientProfile.astrologer_id, func.count(ClientProfile.id))
        .group_by(ClientProfile.astrologer_id)
        .all()
    )
    with_5plus = sum(1 for c in counts.values() if c >= 5)

    def uniq(name: str) -> int:
        return (
            db.query(func.count(func.distinct(Event.user_id)))
            .filter(Event.name == name)
            .scalar()
            or 0
        )

    return {
        "total_astrologers": db.query(func.count(AstrologerProfile.id)).scalar() or 0,
        "with_5plus_clients": with_5plus,
        "did_consultation_via_brief": uniq(EventName.CRM_CONSULTATION_BRIEF),
        "opened_alert": uniq(EventName.CRM_ALERT_OPENED),
    }


def compute_promo_activation(db: Session) -> dict:
    """Группа 4 — активация промокода.

    Источник 1: gift_codes.redeemed_by (уже есть в модели).
    Источник 2: событие promo_activated (если промо не через gift_codes).
    Берём максимум, чтобы не зависеть от способа применения.
    """
    from sqlalchemy import func
    from backend.models import GiftCode, Event

    gift_activated = (
        db.query(func.count(GiftCode.id))
        .filter(GiftCode.redeemed_by.isnot(None))
        .scalar()
        or 0
    )
    event_activated = (
        db.query(func.count(func.distinct(Event.user_id)))
        .filter(Event.name == EventName.PROMO_ACTIVATED)
        .scalar()
        or 0
    )
    return {
        "activated": max(gift_activated, event_activated),
        "gift_activated": gift_activated,
        "event_activated": event_activated,
    }
