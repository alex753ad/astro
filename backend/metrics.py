"""backend/metrics.py — E11 трекинг пилота.

Лёгкий журнал событий (таблица `events`) + расчёт метрик из стратегии §12:
  Группа 1 — привычка: удержание D1/D7/D30 по неделям регистрации.
  Группа 2 — воронка: register → chart → first_interpretation → second_visit.
  Группа 3 — астролог: ≥5 клиентов, консультация через бриф, заход по алерту.
  Группа 4 — остаться самим: активация промокода (+ exit-причины из E10).

log_event() устойчив: любые ошибки логирования НЕ ломают основной запрос.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
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

# Правило «человек вернулся» — решение владельца 30.09.2026:
#   активный день — любой авторизованный запрос, кроме фоновых
#   (backend/activity.py); дни календарные по Москве; день регистрации — 0;
#   D1 — был в день 1, D7 — хоть раз в дни 7–13, D30 — хоть раз в дни 30–36.
# Окно в неделю, а не строго день N: при наших объёмах строгий день — шум.
RETENTION_WINDOWS = {"d1": (1, 1), "d7": (7, 13), "d30": (30, 36)}


def _msk_date(dt: datetime) -> date:
    from datetime import timezone
    from backend.activity import MSK
    return dt.replace(tzinfo=timezone.utc).astimezone(MSK).date()


def _window_summary(members: list[dict], today: date) -> dict:
    out: dict = {"users": len(members)}
    for name, (lo, hi) in RETENTION_WINDOWS.items():
        # В знаменателе — только те, чьё окно уже закончилось (сегодняшний
        # день не закончен). Иначе свежие недели тянут процент вниз.
        eligible = [m for m in members if m["d0"] + timedelta(days=hi) < today]
        retained = app = web = 0
        for m in eligible:
            plats: set = set()
            for k in range(lo, hi + 1):
                plats |= m["act"].get(m["d0"] + timedelta(days=k), set())
            if plats:
                retained += 1
                app += "app" in plats
                web += "web" in plats
        out[name] = {
            "retained": retained,
            "eligible": len(eligible),
            "pct": round(retained / len(eligible) * 100) if eligible else None,
            "app": app,
            "web": web,
        }
    return out


def _weeks(members: list[dict], today: date) -> list[dict]:
    by_week: dict[date, list] = {}
    for m in members:
        by_week.setdefault(m["d0"] - timedelta(days=m["d0"].weekday()), []).append(m)
    return [
        {"week": wk.isoformat(), **_window_summary(by_week[wk], today)}
        for wk in sorted(by_week, reverse=True)
    ]


def compute_retention_weekly(
    db: Session,
    *,
    platform: Optional[str] = None,
    tier: Optional[str] = None,
    flag: Optional[str] = None,
    source: Optional[str] = None,
    today: Optional[date] = None,
) -> dict:
    """Удержание D1/D7/D30 по неделям регистрации (таблица user_activity_days).

    ⚠️ Когорта — только зарегистрированные с первого записанного дня
    (`since`). Задним числом активность не восстанавливалась (решение
    владельца), и старые пользователи выглядели бы ушедшими.

    platform — где человек был в первый активный день («app» | «web»; в тот
    же день и там, и там — «app»). tier — ТЕКУЩИЙ тариф, а не на день
    регистрации (решение владельца, в админке сноска): платят как раз
    оставшиеся, поэтому у платных удержание выглядит выше. source —
    `users.signup_source` целиком (074; «story/share/day_card» — пришли со
    сторис, ссылка aristeatime.ru/d). flag — делит
    когорту на тех, у кого флаг был включён в день 0 или 1, и остальных.
    Не считаются администраторы и revenue_excluded (тестовые аккаунты).
    """
    from backend.activity import msk_today
    from backend.models import User, UserActivityDay

    today = today or msk_today()
    since = db.query(func.min(UserActivityDay.day)).scalar()
    if since is None:
        return {"since": None, "groups": []}

    act: dict[str, dict[date, set]] = {}
    day_flags: dict[tuple[str, date], set] = {}
    for uid, day, plat, flags in db.query(
        UserActivityDay.user_id, UserActivityDay.day,
        UserActivityDay.platform, UserActivityDay.flags,
    ):
        act.setdefault(uid, {}).setdefault(day, set()).add(plat)
        day_flags.setdefault((uid, day), set()).update(flags or [])

    q = db.query(User.id, User.created_at).filter(
        User.is_admin.is_(False),
        User.revenue_excluded.is_(False),
        User.created_at.isnot(None),
    )
    if tier:
        q = q.filter(User.tier == tier)
    if source:
        q = q.filter(User.signup_source == source)

    members = []
    for uid, created in q:
        d0 = _msk_date(created)
        if d0 < since:
            continue
        a = act.get(uid, {})
        if platform:
            first = min(a) if a else None
            if first is None or ("app" if "app" in a[first] else "web") != platform:
                continue
        had_flag = bool(flag) and any(
            flag in day_flags.get((uid, d0 + timedelta(days=k)), ()) for k in (0, 1)
        )
        members.append({"d0": d0, "act": a, "flag": had_flag})

    if flag:
        parts = [(f"С флагом {flag}", [m for m in members if m["flag"]]),
                 ("Без флага", [m for m in members if not m["flag"]])]
    else:
        parts = [("Все", members)]
    return {
        "since": since.isoformat(),
        "groups": [
            {"label": label, "total": _window_summary(ms, today), "weeks": _weeks(ms, today)}
            for label, ms in parts
        ],
    }


def _fmt_window(w: dict) -> str:
    return "—" if w["pct"] is None else f"{w['pct']}% ({w['retained']}/{w['eligible']})"


def retention_summary_text(db: Session, today: Optional[date] = None, weeks: int = 8) -> str:
    """Понедельная сводка в Telegram (tasks.retention_weekly)."""
    head = "📊 Удержание — сводка за неделю"
    rule = "Вернулся: D1 — на следующий день, D7 — в дни 7–13, D30 — в дни 30–36."
    all_ = compute_retention_weekly(db, today=today)
    if not all_["groups"]:
        return f"{head}\nДанных пока нет."
    g = all_["groups"][0]
    lines = [head, rule, f"Считаем с {all_['since']}.", "",
             "Неделя регистрации: людей · D1 · D7 · D30"]
    for w in g["weeks"][:weeks]:
        lines.append(f"{w['week']}: {w['users']} · " + " · ".join(
            _fmt_window(w[k]) for k in RETENTION_WINDOWS))
    lines.append("")
    for label, plat in (("Всего", None), ("Приложение", "app"), ("Сайт", "web")):
        t = (g if plat is None else
             compute_retention_weekly(db, platform=plat, today=today)["groups"][0])["total"]
        lines.append(f"{label}: {t['users']} · " + " · ".join(
            f"{k.upper()} {_fmt_window(t[k])}" for k in RETENTION_WINDOWS))
    lines.append("")
    lines.append(_story_line(db))
    lines.append("Разбивка по тарифу, флагам и источнику — /admin → «Пилот».")
    return "\n".join(lines)


STORY_SOURCE = "story/share/day_card"   # метки редиректа /d (nginx, astreatime.conf)


def _story_line(db: Session) -> str:
    """Сторис за 7 дней: сколько отправили (флаг story_card) и сколько
    зарегистрировались с метками /d."""
    from backend.models import User
    from backend.story_card_router import shares_since
    from backend.time_utils import utcnow

    since = utcnow() - timedelta(days=7)
    sent = shares_since(db, since)
    came = db.query(func.count(User.id)).filter(
        User.signup_source == STORY_SOURCE, User.created_at >= since).scalar() or 0
    return (f"Сторис за 7 дней: «Моя карта» — {sent.get('chart', 0)}, на фото — "
            f"{sent.get('photo', 0)}; регистраций со сторис — {came}.")


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
