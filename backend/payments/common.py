"""Провайдер-независимая логика обработки платежа.

Не знает про Robokassa/Stripe/ЮKassa — принимает уже проверенные данные
(подпись и сумма сверены снаружи, в роутере конкретного провайдера) и
отвечает за: идемпотентность по идентификатору платежа, начисление
партнёрской комиссии или обычной реферальной награды в SAVEPOINT, активацию
подписки. Специфичные для провайдера вещи (проверка подписи, сверка суммы,
формат идентификатора платежа) сюда не входят — это остаётся в роутере.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import User, Subscription, PaymentEvent, Partner
from backend.partners.commission import credit_commission
from backend.time_utils import utcnow

logger = logging.getLogger("astro.payments")

PERIOD_DAYS = {"monthly": 30, "annual": 365}
REFERRAL_REWARD_DAYS = 14


class DuplicatePayment(Exception):
    """Платёж с этим payment_id уже обработан — не ошибка, вызывающая
    сторона должна подтвердить провайдеру приём (200 OK) и ничего не делать."""


class PaymentProcessingError(Exception):
    """Платёж не удалось обработать. `stage` — на каком шаге, для алертов."""

    def __init__(self, stage: str, message: str = ""):
        self.stage = stage
        super().__init__(message or stage)


# ── Активация подписки ─────────────────────────────────────

def activate_subscription(user_id: str, tier: str, period: str, db: Session) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning("activate_subscription: user %s not found", user_id)
        return

    days = PERIOD_DAYS.get(period, 30)
    period_end = utcnow() + timedelta(days=days)

    user.tier = tier

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if sub:
        sub.tier             = tier
        sub.status           = "active"
        sub.stripe_price_id  = f"{tier}_{period}"
        sub.current_period_end = period_end
    else:
        sub = Subscription(
            user_id=user.id,
            stripe_price_id=f"{tier}_{period}",
            status="active",
            tier=tier,
            current_period_end=period_end,
        )
        db.add(sub)

    db.commit()
    logger.info("Activated: user=%s tier=%s period=%s until=%s", user_id, tier, period, period_end.date())


def apply_referral_reward(referrer_user_id: str, db: Session) -> None:
    """«Пригласи друга — получи 2 недели Pro бесплатно»: продлить
    current_period_end уже активной ПЛАТНОЙ подписки реферера.

    Раньше это делалось через Stripe Coupon — требовал referrer.stripe_customer_id,
    награда молча не срабатывала для не-Stripe плательщиков. Теперь — прямое
    продление в своей БД. Free-рефереры бонус не получают: продлевать нечего,
    а выдавать pro без даты автоматического отзыва рискованно — у системы нет
    общего джоба, понижающего tier по истечении current_period_end (кроме
    отдельного cron для пилота, backend/pilot/cron.py), заводить такой ради
    этого бонуса не стали.

    Не для партнёров (Partner, backend/models.py) — та программа считает
    комиссию деньгами, а не днями подписки; вызывающая сторона (process_payment
    ниже) сама решает, что применить, эта функция ничего не проверяет про
    партнёрство.

    Ничего не коммитит — вызывается той же SAVEPOINT-веткой, что и
    credit_commission, коммит делает activate_subscription в конце общей
    транзакции с платежом.
    """
    referrer = db.query(User).filter(User.id == referrer_user_id).first()
    if not referrer:
        return

    sub = db.query(Subscription).filter(Subscription.user_id == referrer.id).first()
    if not sub or sub.status != "active" or referrer.tier == "free":
        logger.info("Referral reward skipped: referrer=%s has no active paid subscription", referrer_user_id)
        return

    base = sub.current_period_end if (sub.current_period_end and sub.current_period_end > utcnow()) else utcnow()
    sub.current_period_end = base + timedelta(days=REFERRAL_REWARD_DAYS)
    logger.info(
        "Referral reward applied: referrer=%s +%sd -> %s",
        referrer_user_id, REFERRAL_REWARD_DAYS, sub.current_period_end.date(),
    )


# ── Обработка проверенного платежа ─────────────────────────

def process_payment(
    db: Session,
    *,
    provider: str,
    payment_id: str,
    user_id: str,
    tier: str,
    period: str,
    amount: float,
) -> PaymentEvent:
    """Идемпотентно фиксирует платёж и активирует подписку.

    Вызывающая сторона (роутер конкретного провайдера) обязана сверить
    подпись и сумму ДО вызова этой функции — здесь предполагается, что
    (user_id, tier, period, amount) уже достоверны.

    Идемпотентность / anti-replay в БД: уникальный payment_id. Раньше ключ
    жил только в Redis, и при его недоступности код шёл дальше (fail-open) —
    тот же вебхук с валидной подписью продлевал подписку сколько угодно раз.

    Запись о платеже и сама активация — ОДНА транзакция. Если закоммитить
    payment_events отдельно и упасть на активации, повтор вебхука увидит
    существующий payment_id, провайдер получит подтверждение и уйдёт — деньги
    списаны, подписки нет, а ретраи провайдера конечны: почить нечем. Поэтому
    здесь flush (проверка уникальности без фиксации), затем активация, и
    только потом общий commit — его делает activate_subscription.

    Raises:
        DuplicatePayment: payment_id уже обработан — не ошибка, тот же ответ,
            что и на первый успешный вызов.
        PaymentProcessingError: сбой на шаге записи платежа или активации —
            стадия в `.stage` для алерта.
    """
    try:
        payment_event = PaymentEvent(
            provider=provider,
            inv_id=payment_id,
            user_id=user_id,
            tier=tier,
            period=period,
            amount=amount,
        )
        db.add(payment_event)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DuplicatePayment(payment_id) from None
    except Exception as exc:
        db.rollback()
        logger.exception("%s: payment_events insert failed, payment_id=%s", provider, payment_id)
        raise PaymentProcessingError("payment_events insert") from exc

    # Партнёрская комиссия и обычная реферальная награда не должны иметь
    # возможности сорвать реальный платёж. Голого try/except здесь
    # недостаточно: если код внутри падал уже после db.add()/запроса, сессия
    # SQLAlchemy оставалась в состоянии, требующем rollback, и следующий шаг
    # (activate_subscription, тот же db.commit()) валился следом за ней —
    # платёж откатывался целиком, хотя try/except формально стоял на месте.
    # begin_nested() — SAVEPOINT: при сбое откатывается только он, уже
    # сфлашенный payment_event остаётся цел.
    #
    # Комиссия и обычная награда взаимоисключающие для одного реферера —
    # партнёрская программа отдельная сущность, не смешивается с обычной
    # реферальной механикой: если реферер — активный партнёр, он получает
    # комиссию деньгами, а не 2 недели подписки в подарок.
    try:
        with db.begin_nested():
            buyer = db.query(User).filter(User.id == user_id).first()
            if buyer and buyer.referred_by:
                is_active_partner = db.query(Partner.id).filter(
                    Partner.user_id == buyer.referred_by, Partner.status == "active",
                ).first() is not None
                if is_active_partner:
                    credit_commission(db, payment_event, buyer)
                else:
                    apply_referral_reward(buyer.referred_by, db)
    except Exception:
        logger.exception("%s: referral reward/commission failed, payment_id=%s", provider, payment_id)

    try:
        activate_subscription(user_id=user_id, tier=tier, period=period, db=db)
    except Exception as exc:
        # Откатывает и активацию, и запись о платеже — ретрай провайдера
        # начнёт с чистого листа, а не упрётся в «уже обработано».
        db.rollback()
        logger.exception("%s: activate_subscription failed, payment_id=%s", provider, payment_id)
        raise PaymentProcessingError("activate_subscription") from exc

    logger.info("%s: payment OK, payment_id=%s user=%s tier=%s", provider, payment_id, user_id, tier)
    return payment_event
