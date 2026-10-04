"""Письма онбординга и письма после покупки — единственный путь отправки.

Раньше эти письма ставились отложенными задачами Celery (countdown до 30
суток), а day2/day7 вдобавок слала ручка /internal/onboarding-emails. Задача с
ETA дольше visibility timeout Redis-брокера выдавалась воркеру заново каждый
час, и 23.09.2026 одно письмо пришло ~10 раз разом (CLAUDE.md, «Письма
онбординга»). Теперь:

* **Один путь.** Beat-задача `tasks.send_lifecycle_emails` раз в час
  (06:15–18:15 UTC) зовёт `run_lifecycle_emails`. Приветствие после оплаты —
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


# ── Тексты day2 (перенесены из onboarding_router.py вместе с ручкой) ──

_PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий",
    "Venus": "Венера", "Mars": "Марс", "Jupiter": "Юпитер",
    "Saturn": "Сатурн", "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон",
}
_ASPECT_RU = {
    "conjunction": "соединение", "sextile": "секстиль",
    "square": "квадрат", "trine": "трин", "opposition": "оппозиция",
}
_POSITIVE_ASPECTS = {"trine", "sextile", "conjunction"}
_POSITIVE_PLANETS = {"Venus", "Jupiter", "Sun"}
_TRANSIT_TEMPLATES = {
    ("Venus",   "trine"):       "Венера образует гармоничный трин — прекрасное время для отношений, творчества и приятных встреч.",
    ("Venus",   "sextile"):     "Венера в секстиле открывает возможности для новых знакомств и укрепления связей.",
    ("Venus",   "conjunction"): "Венера в соединении усиливает твою привлекательность и желание гармонии.",
    ("Jupiter", "trine"):       "Юпитер в трине приносит удачу и расширение возможностей — действуй смело.",
    ("Jupiter", "sextile"):     "Юпитер в секстиле открывает двери там, где раньше были препятствия.",
    ("Jupiter", "conjunction"): "Юпитер в соединении — один из лучших транзитов года. Энергия роста на максимуме.",
    ("Sun",     "trine"):       "Солнечный трин наполняет энергией и уверенностью в собственных силах.",
    ("Mars",    "trine"):       "Марс в трине даёт прилив сил и решимости — отличный момент для активных действий.",
}


# Натальная планета в творительном вместе с «твой натальный» — готовой фразой
# по роду. До 24.09.2026 было «с вашим натальным {имя}» с именем в
# именительном: «с вашим натальным Луна».
_NATAL_WITH_YOURS = {
    "Sun": "твоим натальным Солнцем", "Moon": "твоей натальной Луной",
    "Mercury": "твоим натальным Меркурием", "Venus": "твоей натальной Венерой",
    "Mars": "твоим натальным Марсом", "Jupiter": "твоим натальным Юпитером",
    "Saturn": "твоим натальным Сатурном", "Uranus": "твоим натальным Ураном",
    "Neptune": "твоим натальным Нептуном", "Pluto": "твоим натальным Плутоном",
}


def _pick_best_transit(events: list):
    for e in events:
        if e.transit_planet in _POSITIVE_PLANETS and e.aspect_type in _POSITIVE_ASPECTS:
            return e
    for e in events:
        if e.aspect_type in {"trine", "sextile"}:
            return e
    return events[0] if events else None


_MONTHS_GEN = ("", "января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря")


def _when(event, today: date) -> str:
    """Когда транзит: точный день в окне недели, «Сейчас» — уже идёт, иначе
    «С …». ⚠️ До 01.10.2026 здесь стояло «Сегодня» для любого транзита
    недели — событие через пять дней называлось сегодняшним."""
    exact = date.fromisoformat(event.exact_date[:10]) if event.exact_date else None
    if exact and today <= exact <= today + timedelta(days=7):
        return f"{exact.day} {_MONTHS_GEN[exact.month]}"
    start = date.fromisoformat(event.start_date[:10])
    if start <= today:
        return "Сейчас"
    return f"С {start.day} {_MONTHS_GEN[start.month]}"


def _build_transit_text(event, today: date) -> str:
    tp, np_, at = event.transit_planet, event.natal_planet, event.aspect_type
    template = _TRANSIT_TEMPLATES.get((tp, at), "")
    base = (
        f"{_when(event, today)} <strong>{_PLANET_RU.get(tp, tp)}</strong> образует "
        f"{_ASPECT_RU.get(at, at)} с <strong>{_NATAL_WITH_YOURS.get(np_, _PLANET_RU.get(np_, np_))}</strong>."
    )
    return f"{base}<br><br>{template}" if template else base


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
    from backend.transit.engine import calculate_transits

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
            horizon = 7 if kind == "retention_day2" else 30
            events = calculate_transits(
                natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=horizon),
            )
            if kind == "retention_day2":
                event = _pick_best_transit(events)
                if not event:
                    continue
                text = _build_transit_text(event, today)
                send = lambda: email_service.send_retention_day2(email, text, unsubscribe_url=unsub)
            else:
                if not events:
                    continue  # звать разбирать нечего
                count = len(events)
                send = lambda: email_service.send_retention_day7(email, count, unsubscribe_url=unsub)
        if send_once(db, uid, kind, "", send):
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
