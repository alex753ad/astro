"""Письма онбординга и письма после покупки — единственный путь отправки.

Раньше эти письма ставились отложенными задачами Celery (countdown до 30
суток), а day2/day7 вдобавок слала ручка /internal/onboarding-emails. Задача с
ETA дольше visibility timeout Redis-брокера выдавалась воркеру заново каждый
час, и 23.09.2026 одно письмо пришло ~10 раз разом (CLAUDE.md, «Письма
онбординга»). Теперь:

* **Один путь.** Beat-задача `tasks.send_lifecycle_emails` раз в час
  круглые сутки (:15, решение владельца 05.10.2026; до того 06:15–18:15 UTC)
  зовёт `run_lifecycle_emails`. Круглые сутки — ради «Важного транзита»: он
  уходит первым прогоном после 09:00 по местному времени, а 09:00 во
  Владивостоке — 23:00 UTC. Приветствие после оплаты —
  задача `tasks.send_purchase_welcome_task` сразу после активации: ждать до
  часа (а ночью — до утра) письма «оплата прошла» нельзя. Других вызовов
  send_retention_day*/send_*_day*/send_*_welcome в коде нет — это держит тест.
* **Журнал в БД** (`email_sent_log`, миграция 054) вместо ключа в Redis:
  строка пишется ДО отправки в той же транзакции, что проверка, и
  откатывается, если письмо не ушло (`send_once`).
* **Выборка «пора, ещё не опоздали, нет в журнале»**, а не «ровно сегодня»:
  пропущенный прогон (деплой, простой) догоняется следующим, а человек,
  зарегистрированный полгода назад, day2 не получит — у каждого письма есть
  последний день (`LateWindow`).

Точка отсчёта онбординга — РЕГИСТРАЦИЯ (`users.created_at`), решение владельца
23.09.2026. Первая карта не годится: дата её создания нигде не хранится как
факт, а минимум `natal_charts.created_at` сдвигается, когда человек удаляет
первую карту (слотовая модель это поощряет). Условие «есть карта» для day2/day7
проверяется в момент отправки — текст этих писем строится по карте.
"""
from __future__ import annotations

import asyncio
import logging

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import String, and_, cast, exists, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import DeviceToken, EmailSentLog, NatalChart, PaymentEvent, User
from backend.time_utils import local_today, user_tz, utcnow

logger = logging.getLogger("astro.lifecycle_emails")


@dataclass(frozen=True)
class LateWindow:
    """Письмо «пора» через due_days от точки отсчёта и уходит не позже last_day.

    Окна соседних писем онбординга не пересекаются (2–5, 7–11, 14–21): после
    долгого простоя человек не получит два письма в один день.
    """
    due_days: int
    last_day: int


# Решение владельца 23.09.2026.
ONBOARDING = {
    "retention_day2": LateWindow(2, 5),
    "retention_day7": LateWindow(7, 11),
    "retention_day14": LateWindow(14, 21),
}
PURCHASE = {
    "lite_day14": ("lite", LateWindow(14, 21)),
    "pro_day30": ("pro", LateWindow(30, 37)),
}
WELCOME_KIND = {"lite": "lite_welcome", "pro": "pro_welcome", "premium": "premium_welcome"}


# ── Отправка через журнал ───────────────────────────────────

def send_once(
    db: Session, user_id: str, kind: str, ref: str,
    send: Callable[[], Awaitable[bool]],
) -> bool:
    """Отправить письмо, если его нет в журнале. True — письмо ушло сейчас.

    Порядок несущий: INSERT (flush) → отправка → commit, при неудаче rollback.
    Второй параллельный прогон на Postgres ждёт на уникальном индексе, пока
    первый не закоммитит, и получает IntegrityError — отдельный SELECT «а не
    отправляли ли» пропустил бы оба. Блокировка держится ровно время запроса
    к Resend, поэтому у него жёсткий общий таймаут
    (`email_service.RESEND_TOTAL_TIMEOUT_SEC`).

    Остаточный риск один: письмо ушло, а commit упал — тогда будет повтор.
    Обратный порядок (commit до отправки) менял бы его на тихую потерю письма.

    Вызывать только на сессии без несохранённых чужих изменений: rollback
    откатывает всю транзакцию.
    """
    db.add(EmailSentLog(user_id=user_id, kind=kind, ref=ref, sent_at=utcnow()))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    try:
        ok = asyncio.run(send())
    except Exception as e:
        logger.warning("%s ref=%r user=%s: отправка упала: %s", kind, ref, user_id, e)
        ok = False
    if ok:
        db.commit()
    else:
        db.rollback()
    return ok


def _not_logged(kind: str, ref_expr):
    return ~exists().where(and_(
        EmailSentLog.user_id == User.id,
        EmailSentLog.kind == kind,
        EmailSentLog.ref == ref_expr,
    ))


# ── Текст day2 ──
# С 05.10.2026 (шаг 5 аудита) — самое сильное главное событие дня
# (day_event.main_event) из 7 дней, его заголовок и совет, как в пуше и
# «Неделе вперёд». До того — свой отбор «позитивных» (Венера, Юпитер, Солнце;
# трин, секстиль, соединение) и восемь своих фраз: письмо называло событием
# недели не то, что приложение.
DAY2_DAYS = 7


def _day2_event(chart, user, today: date):
    from backend.day_event import main_event
    from backend.week_ahead import _ctx
    ctx = _ctx(user, chart)
    evs = (main_event(chart, today + timedelta(days=i), *ctx) for i in range(DAY2_DAYS))
    return min((e for e in evs if e), key=lambda e: (-e.score, e.at_local), default=None)


def _day2_text(ev) -> str:
    """«8 октября · <strong>Юпитер к твоей Венере</strong><br><br>совет» —
    таблица владельца 05.10.2026."""
    from backend.day_event import _MONTHS_GEN, _what, advice
    d = ev.at_local
    return f"{d.day} {_MONTHS_GEN[d.month]} · <strong>{_what(ev)}</strong><br><br>{advice(ev)}"


def _latest_charts_by_user(db: Session, user_ids: list[str]) -> dict[str, NatalChart]:
    """Последняя карта каждого пользователя — одним запросом, а не в цикле."""
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
        .join(latest, (NatalChart.user_id == latest.c.user_id)
              & (NatalChart.created_at == latest.c.max_created))
        .all()
    )
    return {c.user_id: c for c in charts}


# ── Отбор и отправка ────────────────────────────────────────

def _onboarding_candidates(db: Session, kind: str, now: datetime) -> list[User]:
    w = ONBOARDING[kind]
    q = db.query(User).filter(
        User.created_at <= now - timedelta(days=w.due_days),
        User.created_at > now - timedelta(days=w.last_day),
        _not_logged(kind, ""),
    )
    if kind in ("retention_day7", "retention_day14"):
        q = q.filter(User.tier == "free")
    return q.all()


def _send_onboarding(db: Session, kind: str, now: datetime) -> int:
    from backend import email_service
    from backend.profile.email_unsubscribe import unsubscribe_url

    users = _onboarding_candidates(db, kind, now)
    charts = _latest_charts_by_user(db, [u.id for u in users]) if kind != "retention_day14" else {}
    sent = 0
    for user in users:
        # Всё, что зависит от карты и эфемерид, — ДО захвата строки журнала:
        # блокировка на уникальном индексе должна жить только время отправки.
        email, uid = user.email, user.id
        unsub = unsubscribe_url(user)
        if not unsub:
            continue  # отписка от писем (068); в журнал не пишем
        if kind == "retention_day14":
            send = lambda: email_service.send_retention_day14(email, unsubscribe_url=unsub)
        else:
            chart = charts.get(uid)
            if not chart:
                continue  # карты ещё нет — попробуем в следующий прогон, пока открыто окно
            # Первая неделя (флаг first_week, backend/first_week.py): день 2
            # не уходит тем, у кого есть приложение — прогноз дня и так в
            # ленте; день 7 — итог недели вместо «Разбери свои транзиты».
            from backend.flags import flag_on
            if flag_on(db, "first_week", user):
                if kind == "retention_day2" and db.query(DeviceToken.id).filter(
                        DeviceToken.user_id == uid).first():
                    continue
                if kind == "retention_day7":
                    from backend.first_week import summary
                    data = summary(db, user, chart)
                    send = lambda: email_service.send_first_week_summary(email, data, unsubscribe_url=unsub)
                    if send_once(db, uid, kind, "", send):
                        sent += 1
                    continue
            # Местное «сегодня» (user_tz); `now` — наивный UTC (utcnow).
            today = local_today(user_tz(None, user, chart), now.replace(tzinfo=timezone.utc))
            if kind == "retention_day2":
                event = _day2_event(chart, user, today)
                if event is None:
                    send = lambda: email_service.send_retention_day2_calm(email, unsubscribe_url=unsub)
                else:
                    text = _day2_text(event)
                    send = lambda: email_service.send_retention_day2(email, text, unsubscribe_url=unsub)
            else:
                count = _transit_count(chart, today, 30)
                if not count:
                    continue  # звать разбирать нечего
                send = lambda: email_service.send_retention_day7(email, count, unsubscribe_url=unsub)
        if send_once(db, uid, kind, "", send):
            sent += 1
    return sent


def _transit_count(chart, today: date, days: int) -> int:
    """Транзиты за `days` дней — те же точки и правило узлов, что у ленты
    (day_event.points/counts, шаг 5 аудита)."""
    from backend.day_event import counts, points
    from backend.transit.engine import calculate_transits
    events = calculate_transits(natal_planets=points(chart), from_date=today,
                                to_date=today + timedelta(days=days))
    return sum(1 for e in events if counts(e.natal_planet, e.aspect_type))


# ── «Важный транзит» ────────────────────────────────────────
# Решение владельца 02.10.2026 / 05.10.2026: письмо уходит в день точного
# касания медленной планеты (transit.engine.alert_event), первым прогоном
# после ALERT_HOUR по местному времени. До 05.10.2026 оно было побочным
# эффектом GET /transits и не уходило, пока человек не открыл транзиты на
# вебе. Одно письмо в сутки — о самом сильном касании дня (ref — его ключ,
# поэтому следующие прогоны того же дня его не повторят). Ретроградная петля
# даёт до трёх точных касаний — до трёх писем за проход, это верно по сути.
ALERT_KIND = "transit_alert"
ALERT_TIERS = ("pro", "premium")   # Лира и Орион
ALERT_HOUR = 9


def _send_transit_alerts(db: Session, now: datetime) -> int:
    from zoneinfo import ZoneInfo
    from backend.chart_utils import get_primary_chart
    from backend.profile.email_unsubscribe import unsubscribe_url
    from backend.transit.engine import alert_event, send_transit_alert

    users = db.query(User).filter(User.is_active.is_(True), User.tier.in_(ALERT_TIERS)).all()
    sent = 0
    for user in users:
        email, uid = user.email, user.id
        unsub = unsubscribe_url(user)
        if not unsub:
            continue  # отписка от писем (068)
        chart = get_primary_chart(db, user)
        if not chart or not chart.planets:
            continue
        tzname = user_tz(None, user, chart)
        local_now = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tzname))
        if local_now.hour < ALERT_HOUR:
            continue
        ev = alert_event(chart, local_now.date(), tzname)
        if ev is None:
            continue
        chart_id = str(chart.id)
        if send_once(db, uid, ALERT_KIND, ev.key,
                     lambda: send_transit_alert(email, chart_id, ev, unsub)):
            sent += 1
    return sent


def _send_purchase(db: Session, kind: str, now: datetime) -> int:
    from backend import email_service
    from backend.profile.email_unsubscribe import unsubscribe_url

    tier, w = PURCHASE[kind]
    ref_expr = cast(PaymentEvent.id, String)
    rows = (
        db.query(PaymentEvent.id, User)
        .join(User, User.id == PaymentEvent.user_id)
        .filter(
            PaymentEvent.starts_chain.is_(True),
            PaymentEvent.tier == tier,
            PaymentEvent.created_at <= now - timedelta(days=w.due_days),
            PaymentEvent.created_at > now - timedelta(days=w.last_day),
            User.tier == tier,  # ушёл с тарифа — письмо про него неуместно
            _not_logged(kind, ref_expr),
        )
        .all()
    )
    fn = {"lite_day14": email_service.send_lite_day14, "pro_day30": email_service.send_pro_day30}[kind]
    sent = 0
    for pid, user in rows:
        unsub = unsubscribe_url(user)
        if not unsub:
            continue  # отписка от писем (068)
        uid, email, name = user.id, user.email, user.name
        if send_once(db, uid, kind, str(pid), lambda: fn(email, name=name, unsubscribe_url=unsub)):
            sent += 1
    return sent


def run_lifecycle_emails(db: Session, now: datetime | None = None) -> dict:
    """Один прогон. Идемпотентен: повтор в тот же час ничего не шлёт."""
    now = now or utcnow()
    result = {}
    for kind in ONBOARDING:
        try:
            result[kind] = _send_onboarding(db, kind, now)
        except Exception:
            db.rollback()
            logger.exception("lifecycle: %s упал", kind)
            result[kind] = None
    for kind in PURCHASE:
        try:
            result[kind] = _send_purchase(db, kind, now)
        except Exception:
            db.rollback()
            logger.exception("lifecycle: %s упал", kind)
            result[kind] = None
    try:
        result[ALERT_KIND] = _send_transit_alerts(db, now)
    except Exception:
        db.rollback()
        logger.exception("lifecycle: %s упал", ALERT_KIND)
        result[ALERT_KIND] = None
    return result


def send_purchase_welcome(db: Session, payment_event_id: int) -> bool:
    """Приветствие по оплате, начавшей тариф. ref = id платежа: раз на покупку."""
    from backend import email_service

    row = (
        db.query(PaymentEvent.tier, PaymentEvent.starts_chain, User.id, User.email, User.name)
        .join(User, User.id == PaymentEvent.user_id)
        .filter(PaymentEvent.id == payment_event_id)
        .first()
    )
    if not row:
        return False
    tier, starts_chain, uid, email, name = row
    kind = WELCOME_KIND.get(tier)
    if not kind or not starts_chain:
        return False
    fn = {
        "lite": email_service.send_lite_welcome,
        "pro": email_service.send_pro_welcome,
        "premium": email_service.send_premium_welcome,
    }[tier]
    return send_once(db, uid, kind, str(payment_event_id), lambda: fn(email, name=name))
