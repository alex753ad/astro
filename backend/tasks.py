"""Celery tasks for heavy computations."""

from __future__ import annotations

import logging
from backend.time_utils import utcnow

from backend.celery_app import celery_app
from backend.database import SessionLocal
from backend.models import NatalChart
from backend.chart_utils import get_primary_chart as _get_primary_chart  # noqa: F401 — реэкспорт для backend.pilot.cron и др.

logger = logging.getLogger("astro.tasks")


# ═══════════════════════════════════════════════════════════
# ПИСЬМА ОНБОРДИНГА И ПОСЛЕ ПОКУПКИ — backend/lifecycle_emails.py
# ═══════════════════════════════════════════════════════════
#
# ⚠️ Отложенных запусков дольше часа здесь быть не должно: задача с
# countdown/eta дольше visibility timeout Redis-брокера (умолчание 1 час)
# выдаётся воркеру заново каждый час, и все копии срабатывают разом — так
# 23.09.2026 одно письмо пришло ~10 раз. Держит test_lifecycle_emails.py.

@celery_app.task(name="tasks.send_lifecycle_emails")
def send_lifecycle_emails() -> dict:
    """Beat, раз в час 06:15–18:15 UTC: day2/day7/day14, lite_day14, pro_day30."""
    from backend.lifecycle_emails import run_lifecycle_emails
    db = SessionLocal()
    try:
        return run_lifecycle_emails(db)
    finally:
        db.close()


@celery_app.task(name="tasks.send_purchase_welcome", ignore_result=True)
def send_purchase_welcome_task(payment_event_id: int) -> bool:
    """Приветствие сразу после оплаты, начавшей тариф (payments/common.py).

    ⚠️ `ignore_result=True` несущий, а не косметика. Без него `.delay()` перед
    отправкой подписывается на результат в Redis-бэкенде (`on_task_call`), и
    при недоступном Redis переподключается БЕСКОНЕЧНО — исключения нет, и
    `try/except` вокруг `.delay` в activate_subscription не срабатывает.
    Вызов идёт из синхронного кода внутри async-вебхука, то есть висел бы
    весь API. С флагом бэкенд не трогается, а отправка в брокер ретраится
    ограниченно и падает исключением, которое там ловится. Найдено 24.09.2026
    дампом стека: локально (без Redis) так висели все тесты оплаты.
    """
    from backend.lifecycle_emails import send_purchase_welcome
    db = SessionLocal()
    try:
        return send_purchase_welcome(db, payment_event_id)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# САМОПРОВЕРКА ПРОГНОЗОВ И СИГНАЛЫ ВЛАДЕЛЬЦУ — backend/selfcheck.py
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.selfcheck_daily")
def selfcheck_daily() -> dict:
    """Beat, 07:30 МСК: четыре шага на служебной карте."""
    import asyncio
    from backend.beat_watchdog import _sync_redis
    from backend.selfcheck import run_daily
    return asyncio.run(run_daily(_sync_redis()))


@celery_app.task(name="tasks.send_price_notice", ignore_result=True)
def send_price_notice_task(effective_date: str) -> dict:
    """Рассылка уведомления о смене цен — ставит только админ-ручка."""
    from datetime import date as _date
    from backend.payments.price_notice import build_notice, send_all
    db = SessionLocal()
    try:
        return send_all(db, build_notice(_date.fromisoformat(effective_date)))
    finally:
        db.close()


@celery_app.task(name="tasks.reconcile_payments", ignore_result=True)
def reconcile_payments() -> dict:
    """Beat, 06:00 МСК: успешные платежи ЮKassa ↔ payment_events ↔ тарифы.

    Начисляет пропущенное вебхуком теми же проверками (payments/reconcile.py).
    """
    import asyncio
    from backend.beat_watchdog import _sync_redis
    from backend.payments.reconcile import run_reconciliation
    db = SessionLocal()
    try:
        return asyncio.run(run_reconciliation(db, _sync_redis()))
    finally:
        db.close()


@celery_app.task(name="tasks.selfcheck_hourly")
def selfcheck_hourly() -> dict:
    """Beat, раз в час: ключ, бюджет, модель, доля запасных, повтор красных шагов."""
    import asyncio
    from backend.beat_watchdog import _sync_redis
    from backend.selfcheck import run_hourly
    return asyncio.run(run_hourly(_sync_redis()))


# ── Снятые задачи: заглушки до 24.10.2026 ──
#
# До перехода на журнал письма ставились под этими именами с countdown до 30
# суток, и их сообщения с ETA ещё лежат в Redis. Удали имена сразу — воркер
# упадёт на незарегистрированной задаче; оставь рабочими — письмо уйдёт вторым
# путём мимо журнала. Поэтому имена зарегистрированы и не делают ничего.
# Удалить после 24.10.2026 (деплой + 31 сутки: самый длинный countdown был 30
# суток) — напоминание в TASKS.md.
_RETIRED_TASK_NAMES = (
    "tasks.send_retention_day2",
    "tasks.send_retention_day7",
    "tasks.send_retention_day14",
    "tasks.schedule_retention_emails",
    "tasks.send_lite_welcome_task",
    "tasks.send_lite_day14_task",
    "tasks.schedule_lite_emails",
    "tasks.send_pro_welcome_task",
    "tasks.send_pro_day30_task",
    "tasks.schedule_pro_emails",
    "tasks.send_premium_welcome_task",
    "tasks.schedule_premium_emails",
)


def _register_retired(name: str) -> None:
    def _retired(*args, **kwargs) -> None:
        logger.info("снятая задача %s args=%s — пропущено (письма идут через журнал)", name, args)
    _retired.__name__ = name.rsplit(".", 1)[-1]
    celery_app.task(name=name)(_retired)


for _name in _RETIRED_TASK_NAMES:
    _register_retired(_name)


# ═══════════════════════════════════════════════════════════
# LUNAR RETURN CHECK (задача 2)
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.check_lunar_returns")
def check_lunar_returns() -> dict:
    """Daily Celery task: send email when Moon returns to user's natal sign.

    Should be triggered via Railway Cron POST /api/v1/internal/lunar-returns (09:00 МСК).
    """
    import asyncio
    from datetime import date as date_type
    from backend.models import User, NatalChart
    from backend.transit.engine import get_next_lunar_return
    from backend.email_service import send_lunar_return_email

    db = SessionLocal()
    sent = 0
    today = date_type.today()

    try:
        users = db.query(User).filter(User.is_active == True).all()
        for user in users:
            chart = _get_primary_chart(db, user)
            if not chart or not chart.planets:
                continue
            try:
                natal_data = {"planets": chart.planets}
                lunar_date = get_next_lunar_return(natal_data, today)
                if lunar_date == today:
                    asyncio.run(
                        send_lunar_return_email(user, today)
                    )
                    sent += 1
            except Exception as e:
                logger.warning("Lunar return check failed user=%s: %s", user.id, e)
    finally:
        db.close()

    logger.info("check_lunar_returns: sent=%d", sent)
    return {"sent": sent, "date": str(today)}


@celery_app.task(name="tasks.send_weekly_digest_task")
def send_weekly_digest_task() -> dict:
    """Daily Celery Beat task: send weekly digest to users whose digest_day == today."""
    import asyncio
    from datetime import date as date_type
    from backend.models import User
    from backend.email_service import send_weekly_digest

    db = SessionLocal()
    sent = 0
    today_weekday = date_type.today().weekday()

    try:
        users = db.query(User).filter(
            User.tier.in_(["pro", "premium"]),
            User.digest_day_of_week == today_weekday,
            User.is_active == True,
        ).all()
        for user in users:
            try:
                ok = asyncio.run(
                    send_weekly_digest(user, db)
                )
                if ok:
                    sent += 1
            except Exception as e:
                logger.warning("Weekly digest failed user=%s: %s", user.id, e)
    finally:
        db.close()

    logger.info("send_weekly_digest_task: sent=%d weekday=%d", sent, today_weekday)
    return {"sent": sent, "weekday": today_weekday}


# ═══════════════════════════════════════════════════════════
# CLIENT BROADCAST (021 / roadmap idea 5, 022 auto+unsub+ai)
# ═══════════════════════════════════════════════════════════

def _ensure_unsub_token(client, db) -> str:
    if not client.unsubscribe_token:
        import uuid
        client.unsubscribe_token = uuid.uuid4().hex
        db.commit()
    return client.unsubscribe_token


def _unsub_url(token: str) -> str:
    from backend.email_service import PUBLIC_API_URL
    return f"{PUBLIC_API_URL}/api/v1/crm/unsubscribe/{token}"


async def _gen_broadcast_ai(profile: dict, tier: str, period_label: str, transits: list[dict]) -> str | None:
    """AI-текст для гибридного письма. None → откат на шаблон."""
    try:
        from backend.interpretation.base import InterpretationRequest
        from backend.interpretation.router import get_router
        from backend.email_service import build_broadcast_ai_prompt
        req = InterpretationRequest(
            natal_profile=profile,
            context="transit",
            tier=tier or "premium",
            custom_prompt=build_broadcast_ai_prompt(period_label, transits),
        )
        result = await get_router().generate(req)
        return (result.content or "").strip() or None
    except Exception as e:
        logger.warning("Broadcast AI generation failed: %s", e)
        return None


@celery_app.task(name="tasks.send_client_broadcast")
def send_client_broadcast_task(astrologer_id: int, client_ids=None, period_ym: str | None = None,
                               mode: str = "template", custom_text: str | None = None) -> dict:
    """Ежемесячная брендовая рассылка прогноза клиентам астролога.

    mode="ai" → AI-текст на каждого клиента (гибрид, платно); иначе шаблон.
    Пропускает отписавшихся и уже отправленных в этом period_ym.
    """
    import asyncio
    from datetime import date, timedelta

    from backend.models import AstrologerProfile, ClientProfile, ClientBroadcastLog, User
    from backend.transit.engine import calculate_transits
    from backend.email_service import send_client_broadcast, ru_month_label

    db = SessionLocal()
    sent, failed = 0, 0
    try:
        astrologer = db.query(AstrologerProfile).filter(
            AstrologerProfile.id == astrologer_id
        ).first()
        if not astrologer:
            return {"sent": 0, "failed": 0, "error": "astrologer not found"}

        brand = astrologer.display_name or "Ваш астролог"  # вы-разрешено: письмо клиенту астролога
        owner = db.query(User).filter(User.id == astrologer.user_id).first()
        tier = owner.tier if owner else "premium"

        today = date.today()
        ym = period_ym or today.strftime("%Y-%m")
        period_label = ru_month_label(today)

        q = (
            db.query(ClientProfile, NatalChart)
            .join(NatalChart, ClientProfile.natal_chart_id == NatalChart.id)
            .filter(ClientProfile.astrologer_id == astrologer_id)
            .filter(ClientProfile.email.isnot(None))
            .filter(ClientProfile.broadcast_opt_out == False)  # noqa: E712
        )
        if client_ids:
            q = q.filter(ClientProfile.id.in_(client_ids))
        rows = q.all()

        # Логи прошлой отправки за период — одним запросом на всю рассылку,
        # а не по одному SELECT на клиента: на базе в сотни клиентов цикл ниже
        # раньше давал сотни лишних обращений к БД на каждый прогон рассылки.
        logs_by_client = {
            log.client_id: log
            for log in db.query(ClientBroadcastLog).filter(
                ClientBroadcastLog.astrologer_id == astrologer_id,
                ClientBroadcastLog.period_ym == ym,
                ClientBroadcastLog.client_id.in_([c.id for c, _ in rows]),
            )
        } if rows else {}

        for client, chart in rows:
            email = (client.email or "").strip()
            if not email:
                continue

            log = logs_by_client.get(client.id)
            if log and log.status == "success":
                continue

            try:
                events = calculate_transits(
                    natal_planets=chart.planets,
                    from_date=today,
                    to_date=today + timedelta(days=30),
                )
                transits = [
                    {
                        "transit_planet": e.transit_planet,
                        "natal_planet": e.natal_planet,
                        "aspect_type": e.aspect_type,
                        "peak_date": getattr(e, "peak_date", None),
                        "peak_orb": getattr(e, "peak_orb", None),
                    }
                    for e in events
                ]
                profile = {
                    "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
                    "ascendant": chart.ascendant, "midheaven": chart.midheaven,
                    "time_unknown": chart.time_unknown,
                }
                token = _ensure_unsub_token(client, db)

                ai_text = None
                if mode == "ai":
                    ai_text = asyncio.run(
                        _gen_broadcast_ai(profile, tier, period_label, transits)
                    )

                ok = asyncio.run(
                    send_client_broadcast(
                        email, brand, period_label, transits,
                        unsubscribe_url=_unsub_url(token), ai_text=ai_text,
                        custom_text=custom_text,
                    )
                )
            except Exception as e:
                logger.warning("Broadcast to client %s failed: %s", client.id, e)
                ok = False

            if log:
                log.status = "success" if ok else "error"
                log.sent_at = utcnow() if ok else None
            else:
                db.add(ClientBroadcastLog(
                    astrologer_id=astrologer_id,
                    client_id=client.id,
                    period_ym=ym,
                    status="success" if ok else "error",
                    sent_at=utcnow() if ok else None,
                ))
            db.commit()
            sent += 1 if ok else 0
            failed += 0 if ok else 1
    finally:
        db.close()

    logger.info("send_client_broadcast_task: astro=%s mode=%s sent=%d failed=%d",
                astrologer_id, mode, sent, failed)
    return {"sent": sent, "failed": failed}


@celery_app.task(name="tasks.send_broadcast_auto")
def send_broadcast_auto_task() -> dict:
    """Beat-задача (ежедневно): 1-го числа ставит рассылку всем премиум-астрологам
    с включённой автоотправкой. В остальные дни — ничего."""
    from datetime import date

    if date.today().day != 1:
        return {"skipped": "not first of month"}

    from backend.models import AstrologerProfile, User

    db = SessionLocal()
    try:
        rows = (
            db.query(AstrologerProfile.id)
            .join(User, AstrologerProfile.user_id == User.id)
            .filter(AstrologerProfile.broadcast_auto == True)  # noqa: E712
            .filter(User.tier == "premium")
            .all()
        )
        ids = [r[0] for r in rows]
    finally:
        db.close()

    for aid in ids:
        send_client_broadcast_task.delay(aid, None, None, "template")

    logger.info("send_broadcast_auto_task: queued %d astrologers", len(ids))
    return {"queued_astrologers": len(ids)}


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTIONS
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.expire_subscriptions")
def expire_subscriptions() -> dict:
    """Истёкшая подписка → тариф падает до free.

    Оплата разовая, на 30 дней (backend/payments/common.activate_subscription),
    автопродления у ЮKassa мы не подключаем. До появления этой задачи джоба,
    понижающего tier по истечении current_period_end, в системе не было вовсе
    (кроме пилотного backend/pilot/cron.py) — то есть один платёж давал платный
    тариф навсегда.

    Карты сверх лимита free при этом НЕ удаляются и остаются доступны: проверка
    в POST /chart/calculate (main.py) слотовая — `total_charts >= profiles_limit`,
    то есть новый слот просто не выдаётся, пока карт не станет меньше лимита
    free. Отдельного кода для этого случая не требуется.

    Пилотных участников задача не трогает: у них нет записи в subscriptions,
    их даунгрейдом занимается backend/pilot/cron.py. Ручная выдача тарифа
    админкой ставит срок на 10 лет и сюда тоже не попадает.
    """
    from backend.beat_watchdog import WATCHED_TASK, mark_success
    from backend.models import Subscription, User

    db = SessionLocal()
    try:
        now = utcnow()
        rows = (
            db.query(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .filter(
                Subscription.status == "active",
                Subscription.current_period_end.isnot(None),
                Subscription.current_period_end < now,
            )
            .all()
        )
        for sub, user in rows:
            logger.info(
                "Subscription expired: user=%s tier=%s until=%s → free",
                user.id, user.tier, sub.current_period_end,
            )
            sub.status = "expired"
            sub.tier = "free"
            user.tier = "free"
        if rows:
            db.commit()
        # Метка живости — ПОСЛЕ коммита и только на успешном пути. Её читает
        # сторож (backend/beat_watchdog.py), запущенный вне очереди: молчаливый
        # незапуск задачи иначе не обнаружить — падение видно по task_failure,
        # а вот не стартовавший beat не падает, он просто ничего не делает.
        # Запись не может уронить задачу, см. mark_success.
        mark_success(WATCHED_TASK)
        return {"expired": len(rows)}
    finally:
        db.close()
