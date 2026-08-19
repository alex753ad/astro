"""Начисление и отмена комиссии партнёру за реальный платёж.

Источник сумм — payment_events (реальные суммы платежей), не MRR-прикидка
из backend/admin/stats_router.py. Партнёрская программа — отдельная сущность
(Partner/Commission), не смешивается с обычной реферальной механикой
(referred_by/referral_code на User, «2 недели Pro за друга»).

Вызывается из backend.payments.common.process_payment сразу после успешной
записи PaymentEvent, в той же транзакции, что и активация подписки — сама
функция ничего не коммитит.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import User, PaymentEvent, Partner, Commission

# «Окно атрибуции — год с момента перехода по ссылке» — так было
# договорено, но реализовано ИНАЧЕ: 365 дней от created_at приглашённого
# (регистрации), не от клика по ссылке. Момент клика нигде не фиксируется
# (ref_code живёт в localStorage до регистрации, см.
# frontend/src/utils/refCode.js), а регистрация всегда позже клика — окно
# фактически щедрее к партнёру на срок между кликом и регистрацией (до 90
# дней, TTL хранения кода в localStorage). Это сознательное отклонение от
# договорённости, а не баг: без отдельного трекинга клика (сейчас его нет)
# технически иначе не выйдет.
ATTRIBUTION_WINDOW_DAYS = 365


def credit_commission(db: Session, payment_event: PaymentEvent, buyer: User) -> Optional[Commission]:
    """Создать начисление, если платёж подпадает под условия программы.

    Ничего не возвращает (None), если условия не выполнены — это штатный
    случай (обычный пользователь без партнёра-реферера), не ошибка.
    """
    if not buyer.referred_by:
        return None

    partner = db.query(Partner).filter(
        Partner.user_id == buyer.referred_by, Partner.status == "active",
    ).first()
    if not partner:
        return None

    # Структурно не должно возникать (referred_by всегда указывает на другого
    # пользователя), но не доверяем данным в финансовом коде.
    if partner.user_id == buyer.id:
        return None

    if buyer.created_at and payment_event.created_at:
        window_end = buyer.created_at + timedelta(days=ATTRIBUTION_WINDOW_DAYS)
        if payment_event.created_at > window_end:
            return None

    commission = Commission(
        partner_id=partner.id,
        payment_event_id=payment_event.id,
        amount=(payment_event.amount or 0) * partner.rate,
        rate=partner.rate,
        kind="earned",
    )
    db.add(commission)
    return commission


def refund_commission(db: Session, payment_event: PaymentEvent, note: str | None = None) -> Optional[Commission]:
    """Возврат платежа: компенсирующая запись, не правка исходной.

    Исходная запись (kind=earned) остаётся как есть — иначе история по
    месяцам, где она уже учтена, переписывалась бы задним числом. Новая
    запись (kind=refund_adjustment) датирована моментом возврата, поэтому
    «минус» естественно попадает в тот период выплат, где возврат случился,
    а не в период исходного начисления.

    Идемпотентно: повторный вызов на тот же payment_event возвращает уже
    существующую корректировку, не создаёт вторую.
    """
    original = db.query(Commission).filter(
        Commission.payment_event_id == payment_event.id, Commission.kind == "earned",
    ).first()
    if not original:
        return None

    existing = db.query(Commission).filter(
        Commission.payment_event_id == payment_event.id, Commission.kind == "refund_adjustment",
    ).first()
    if existing:
        return existing

    adjustment = Commission(
        partner_id=original.partner_id,
        payment_event_id=payment_event.id,
        amount=-original.amount,
        rate=None,
        kind="refund_adjustment",
        note=note,
    )
    db.add(adjustment)
    return adjustment
