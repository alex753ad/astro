"""Чеки «Мой налог»: подсказка владельцу на каждую оплату и сводка за месяц.

Автоматизации чеков нет и сейчас не будет: ЮKassa закрыла «Чеки для
самозанятых» 29.12.2025, а API ФНС — отдельная задача (CLAUDE.md, «Чек по
54-ФЗ»). Поэтому владелец проводит доход руками, и задача кода — дать ему всё,
что нужно ввести, и не дать ни одной оплате потеряться.

* **Сообщение на каждую успешную оплату** (`notify_receipt`) — одно на платёж.
  Зовётся из `settle_payment` (вебхук, ручка статуса, сверка) ровно там, где
  платёж ВПЕРВЫЕ записан в payment_events: повтор любой дорожки упирается в
  уникальный inv_id раньше. Уходит и тогда, когда тариф НЕ выдан (сумма не
  сошлась, пользователь удалён): деньги получены — доход есть, чек нужен.
* **Сводка за прошлый месяц** (`run_monthly_summary`, Beat 1-го числа) — все
  оплаты месяца списком плюс сверка со списком ЮKassa: платёж, которого нет в
  базе, — первый кандидат на пропущенный чек.

⚠️ Дата — момент ОПЛАТЫ по Москве (`paid_at`), а не момент обработки. Сверка
может начислить через несколько дней; чек «Мой налог» пробивается датой
поступления денег.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from backend.models import PaymentEvent, User

logger = logging.getLogger("astro.payments.receipts")

_MSK = timezone(timedelta(hours=3))
_TG_LIMIT = 3500   # у Telegram 4096 на сообщение; запас на разметку
_MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
           "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def paid_at_from(payment: dict[str, Any]) -> datetime | None:
    """captured_at, иначе created_at из API ЮKassa → наивный UTC."""
    for key in ("captured_at", "created_at"):
        raw = str(payment.get(key) or "")
        if raw:
            try:
                return (datetime.fromisoformat(raw.replace("Z", "+00:00"))
                        .astimezone(timezone.utc).replace(tzinfo=None))
            except ValueError:
                continue
    return None


def _msk(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc).astimezone(_MSK)


def service_name(tier: str | None) -> str:
    """Название услуги для чека — одно и то же в сообщении и сводке."""
    from backend.email_service import TIER_NAMES
    name = TIER_NAMES.get(tier or "", tier or "")
    return (f"Доступ к сервису Aristea Timeline, тариф «{name}», 30 дней" if name
            else "Доступ к сервису Aristea Timeline")


def _tier_name(tier: str | None) -> str:
    from backend.email_service import TIER_NAMES
    return TIER_NAMES.get(tier or "", tier or "—")


def _rub(amount: float, currency: str = "RUB") -> str:
    sign = "₽" if currency == "RUB" else currency
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + f" {sign}"


def receipt_text(*, payment_id: str, amount: float, paid_at: datetime | None,
                 tier: str | None, email: str | None, note: str = "",
                 currency: str = "RUB") -> str:
    when = _msk(paid_at).strftime("%d.%m.%Y %H:%M") + " МСК" if paid_at else "—"
    return (
        "🧾 Чек в «Мой налог»\n"
        f"Сумма: {_rub(amount, currency)}\n"
        f"Дата: {when}\n"
        f"Услуга: {service_name(tier)}\n"
        f"Покупатель: {email or 'не определён'}\n"
        f"Платёж: {payment_id}"
        + (f"\n\n{note}" if note else "")
    )


async def notify_receipt(db: Session, *, payment_id: str, amount: float,
                         paid_at: datetime | None, tier: str | None,
                         user_id: str | None, note: str = "", currency: str = "RUB") -> None:
    """Одно сообщение на платёж. Ошибку глотает: чек подстрахует сводка."""
    from backend.notifications.telegram import send_support_message
    if amount <= 0:
        return
    try:
        user = db.query(User).filter(User.id == user_id).first() if user_id else None
        await send_support_message(receipt_text(
            payment_id=payment_id, amount=amount, paid_at=paid_at, tier=tier,
            email=user.email if user else None, note=note, currency=currency,
        ))
    except Exception:
        logger.warning("Чек: сообщение по платежу %s не отправлено", payment_id)


# ── Сводка за месяц ─────────────────────────────────────────

def month_bounds(today_msk: date) -> tuple[datetime, datetime, date]:
    """Прошлый календарный месяц по Москве → (начало, конец) наивным UTC и 1-е число."""
    first_this = today_msk.replace(day=1)
    first_prev = (first_this - timedelta(days=1)).replace(day=1)
    to_utc = lambda d: (datetime(d.year, d.month, d.day, tzinfo=_MSK)
                        .astimezone(timezone.utc).replace(tzinfo=None))
    return to_utc(first_prev), to_utc(first_this), first_prev


def _chunks(lines: list[str]) -> list[str]:
    out, cur = [], ""
    for line in lines:
        if cur and len(cur) + len(line) + 1 > _TG_LIMIT:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def build_summary(db: Session, start: datetime, end: datetime, month: date,
                  api_payments: list[dict] | None) -> list[str]:
    """Тексты сводки (уже порезанные под Telegram)."""
    from sqlalchemy import func
    when = func.coalesce(PaymentEvent.paid_at, PaymentEvent.created_at)
    rows = (db.query(PaymentEvent).filter(when >= start, when < end)
            .order_by(when).all())
    paid = [r for r in rows if (r.amount or 0) > 0 and not str(r.inv_id).startswith("refund:")]
    refunds = [r for r in rows if str(r.inv_id).startswith("refund:") or (r.amount or 0) < 0]
    emails = {u.id: u.email for u in db.query(User).filter(
        User.id.in_({r.user_id for r in rows if r.user_id})).all()} if rows else {}

    title = f"{_MONTHS[month.month - 1]} {month.year}"
    total = sum(r.amount for r in paid)
    lines = [
        f"🧾 Сводка оплат за {title} — сверь, что по каждой пробит чек в «Мой налог»",
        f"Оплат: {len(paid)}, сумма: {_rub(total)}",
        "",
    ]
    for r in paid:
        at = _msk(r.paid_at or r.created_at).strftime("%d.%m %H:%M")
        mark = "" if r.period else " ⚠️ тариф не выдан"
        lines.append(f"{at} · {_rub(r.amount)} · {_tier_name(r.tier)}"
                     f" · {emails.get(r.user_id, '—')} · {r.inv_id}{mark}")
    if not paid:
        lines.append("Оплат не было.")
    if refunds:
        lines += ["", f"Возвраты ({len(refunds)}) — чеки по ним аннулировать:"]
        for r in refunds:
            at = _msk(r.paid_at or r.created_at).strftime("%d.%m %H:%M")
            lines.append(f"{at} · {_rub(abs(r.amount or 0))} · {emails.get(r.user_id, '—')} · {r.inv_id}")

    if api_payments is None:
        lines += ["", "⚠️ Список ЮKassa не получен — сверку с кабинетом сделай вручную."]
    else:
        known = {r.inv_id for r in rows}
        known |= {r.inv_id for r in db.query(PaymentEvent.inv_id).filter(
            PaymentEvent.inv_id.in_([str(p.get("id")) for p in api_payments])).all()}
        missing = [p for p in api_payments
                   if start <= (paid_at_from(p) or start) < end and str(p.get("id")) not in known]
        if missing:
            lines += ["", f"⚠️ Есть в ЮKassa, нет в базе ({len(missing)}) — чек тоже нужен:"]
            for p in missing:
                pa = paid_at_from(p)
                amount = float((p.get("amount") or {}).get("value") or 0)
                lines.append(f"{_msk(pa).strftime('%d.%m %H:%M') if pa else '—'} · {_rub(amount)} · {p.get('id')}")
        else:
            lines += ["", "✅ Со списком ЮKassa сходится."]
    return _chunks(lines)


async def run_monthly_summary(
    db: Session,
    *,
    today_msk: date | None = None,
    lister: Callable[[datetime], Awaitable[list[dict] | None]] | None = None,
    send: Callable[[str], Awaitable[bool]] | None = None,
) -> int:
    """Отправить сводку за прошлый месяц. Возвращает число сообщений."""
    if send is None:
        from backend.notifications.telegram import send_support_message as send
    if lister is None:
        from backend.payments.reconcile import list_succeeded as lister
    today_msk = today_msk or datetime.now(_MSK).date()
    start, end, month = month_bounds(today_msk)
    api = await lister(start.replace(tzinfo=timezone.utc))
    parts = build_summary(db, start, end, month, api)
    for part in parts:
        await send(part)
    return len(parts)
