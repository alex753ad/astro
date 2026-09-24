"""Ежедневная сверка: успешные платежи в ЮKassa ↔ payment_events ↔ тарифы.

Зачем. Вебхук — единственный путь, которым деньги превращаются в тариф, и у
него есть конечный предел: ЮKassa ретраит доставку около суток. Лежал API
дольше, сломался IP-фильтр, отвалился nginx — платёж потерян: деньги списаны,
тарифа нет, записи нет, узнать неоткуда. У конкурентов ровно это звучит как
«заплатила 300 ₽, покупки нет, поддержка молчит».

Что делает (Beat, раз в сутки, `tasks.reconcile_payments`):

* берёт из API ЮKassa успешные платежи за LOOKBACK_DAYS;
* **деньги есть — записи нет** → начисляет тем же `settle_payment`, что и
  вебхук, то есть с ТЕМИ ЖЕ проверками (пользователь есть, тариф продаётся,
  сумма и валюта — по цене на момент создания, возврата нет). Решение
  владельца 24.09.2026: автоначисление только так и не шире. Каждое
  начисление — информационное сообщение владельцу, даже когда всё починилось
  само: сверка нашла платёж, значит вебхук не дошёл, и это само по себе
  сигнал. Не прошло проверки — сигнал даёт сам `settle_payment`;
* **запись есть — тарифа нет** (оплачено меньше 30 дней назад, возврата не
  было, а человек на free) → только сигнал, без начисления: причин может быть
  несколько (ручная смена тарифа, откат базы), и угадывать нельзя;
* API ЮKassa не ответил → сигнал, начислений нет.

Сигналы — через инциденты самопроверки (`selfcheck.settle`): один на
проблему, с «починилось», когда она уходит.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy.orm import Session

from backend.models import PaymentEvent, User
from backend.payments import yookassa_router as yk
from backend.payments.common import PaymentProcessingError, PERIOD_DAYS

logger = logging.getLogger("astro.payments.reconcile")

LOOKBACK_DAYS = 7
_PAGE_LIMIT = 100
_MAX_PAGES = 50   # 5000 платежей за неделю — с запасом; дальше — не бесконечный цикл


async def list_succeeded(since: datetime) -> list[dict[str, Any]] | None:
    """Успешные платежи магазина, созданные после `since`. None — API недоступен."""
    params: dict[str, Any] = {
        "status": "succeeded",
        "created_at.gte": since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "limit": _PAGE_LIMIT,
    }
    items: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            for _ in range(_MAX_PAGES):
                resp = await http.get(f"{yk.API_BASE}/payments", params=params, auth=yk._auth())
                resp.raise_for_status()
                data = resp.json()
                items.extend(data.get("items") or [])
                cursor = data.get("next_cursor")
                if not cursor:
                    return items
                params = {"cursor": cursor, "limit": _PAGE_LIMIT}
    except Exception as exc:
        logger.warning("Сверка: список платежей ЮKassa недоступен: %s", exc)
        return None
    logger.error("Сверка: больше %d страниц платежей — прервано", _MAX_PAGES)
    return items


def _no_tier_problem(db: Session, event: PaymentEvent, payment: dict, now: datetime) -> str | None:
    """Оплачено недавно, возврата не было, а тарифа нет.

    Возврат берётся из самого платежа в ЮKassa (`refunded_amount`), а не из
    журнала: запись возврата в payment_events лежит под id ВОЗВРАТА
    (`refund:<refund_id>`), по id платежа её не найти. После возврата владелец
    мог снять тариф руками — это законный free, сигналить не о чем.
    """
    if not event.period or not event.user_id or not event.created_at:
        return None
    if event.created_at + timedelta(days=PERIOD_DAYS.get(event.period, 30)) < now:
        return None   # срок оплаченного уже вышел — free законно
    if yk._amount_value({"amount": payment.get("refunded_amount") or {}}) > 0:
        return None
    user = db.query(User).filter(User.id == event.user_id).first()
    if user is None or user.tier != "free":
        return None
    return (f"платёж {event.inv_id} на {event.amount:.0f} ₽ ({event.tier}) от "
            f"{event.created_at:%d.%m.%Y}, а у пользователя {event.user_id} тариф free")


async def run_reconciliation(
    db: Session,
    redis,
    *,
    now: datetime | None = None,
    lister: Callable[[datetime], Awaitable[list[dict] | None]] = list_succeeded,
    send: Callable[[str], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    from backend.selfcheck import settle

    if send is None:
        from backend.notifications.telegram import send_support_message as send
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    summary = {"checked": 0, "credited": [], "no_tier": [], "failed": []}

    payments = await lister((now - timedelta(days=LOOKBACK_DAYS)).replace(tzinfo=timezone.utc))
    await settle(redis, "payments_api", None if payments is not None else
                 "API ЮKassa не ответил при сверке платежей — начисления не проверены",
                 send=send)
    if payments is None:
        return summary

    for payment in payments:
        pid = str(payment.get("id") or "")
        if not pid:
            continue
        summary["checked"] += 1
        event = db.query(PaymentEvent).filter(PaymentEvent.inv_id == pid).first()
        if event is not None:
            problem = _no_tier_problem(db, event, payment, now)
            if problem:
                summary["no_tier"].append(pid)
            await settle(redis, f"payment_no_tier:{pid}", problem, send=send)
            continue

        try:
            outcome = await yk.settle_payment(db, payment)
        except PaymentProcessingError:
            summary["failed"].append(pid)
            await settle(redis, f"payment_credit_failed:{pid}",
                         f"сверка не смогла начислить платёж {pid} — сбой обработки, повторит завтра",
                         send=send)
            continue
        await settle(redis, f"payment_credit_failed:{pid}", None, send=send)

        if outcome == yk.ACTIVATED:
            meta = payment.get("metadata") or {}
            summary["credited"].append(pid)
            try:
                await send(
                    "💳 Начислено сверкой — вебхук не дошёл\n"
                    f"Платёж: {pid}\n"
                    f"Пользователь: {meta.get('user_id')}\n"
                    f"Тариф: {meta.get('tier')}, {yk._amount_value(payment):.2f} ₽\n"
                    "Тариф включён. Стоит проверить, почему не дошёл вебхук "
                    "(IP-фильтр, nginx, недоступность API)."
                )
            except Exception:
                logger.warning("Сверка: сообщение о начислении %s не отправлено", pid)

    logger.info("Сверка: %s", {k: (v if isinstance(v, int) else len(v)) for k, v in summary.items()})
    return summary
