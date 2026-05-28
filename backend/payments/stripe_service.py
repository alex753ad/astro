"""Stripe service layer."""

from __future__ import annotations

import logging
from typing import Optional

import stripe
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import User, Subscription

settings = get_settings()
logger = logging.getLogger("astro.stripe")


def _init_stripe() -> None:
    if not stripe.api_key:
        stripe.api_key = settings.stripe_secret_key


TIER_PRICE_MAP: dict[tuple[str, str], str] = {
    ("lite", "monthly"): settings.stripe_price_id_lite,
    ("lite", "annual"): getattr(settings, "stripe_price_id_lite_annual", ""),
    ("pro", "monthly"): settings.stripe_price_id_pro,
    ("pro", "annual"): getattr(settings, "stripe_price_id_pro_annual", ""),
    ("premium", "monthly"): settings.stripe_price_id_premium,
    ("premium", "annual"): getattr(settings, "stripe_price_id_premium_annual", ""),
}
PRICE_TIER_MAP: dict[str, str] = {v: k[0] for k, v in TIER_PRICE_MAP.items() if v}

# Разовые отчёты — цены в центах
REPORT_PRODUCTS = {
    "basic":    {"name": "Базовый натальный отчёт",          "amount": 500},
    "extended": {"name": "Расширенный отчёт с транзитами",   "amount": 900},
    "synastry": {"name": "Отчёт о совместимости",            "amount": 900},
}


# ═══════════════════════════════════════════════════════════
# CUSTOMER
# ═══════════════════════════════════════════════════════════

def get_or_create_customer(user: User, db: Session) -> str:
    _init_stripe()
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": user.id},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


# ═══════════════════════════════════════════════════════════
# CHECKOUT — подписка
# ═══════════════════════════════════════════════════════════

def create_checkout_session(
    user: User, tier: str,
    success_url: str, cancel_url: str, db: Session,
    billing_period: str = "monthly",
) -> str:
    _init_stripe()
    price_id = TIER_PRICE_MAP.get((tier, billing_period))
    if not price_id:
        raise ValueError(f"Unknown tier/period: {tier}/{billing_period}")

    customer_id = get_or_create_customer(user, db)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": user.id, "tier": tier},
        subscription_data={"metadata": {"user_id": user.id, "tier": tier}},
    )
    return session.url


# ═══════════════════════════════════════════════════════════
# CHECKOUT — разовая покупка PDF
# ═══════════════════════════════════════════════════════════

def create_report_checkout_session(
    user: User,
    report_type: str,
    chart_id: str,
    success_url: str,
    cancel_url: str,
    db: Session,
) -> str:
    _init_stripe()
    product = REPORT_PRODUCTS[report_type]
    customer_id = get_or_create_customer(user, db)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": product["amount"],
                "product_data": {"name": product["name"]},
            },
        }],
        success_url=success_url or f"{settings.frontend_url}/chart/{chart_id}?report=success",
        cancel_url=cancel_url or f"{settings.frontend_url}/chart/{chart_id}",
        metadata={
            "user_id": str(user.id),
            "report_type": report_type,
            "chart_id": chart_id,
        },
    )

    logger.info("Report checkout: user=%s type=%s chart=%s", user.id, report_type, chart_id)
    return session.url


# ═══════════════════════════════════════════════════════════
# CUSTOMER PORTAL
# ═══════════════════════════════════════════════════════════

def create_portal_session(user: User, return_url: str, db: Session) -> str:
    _init_stripe()
    customer_id = get_or_create_customer(user, db)
    session = stripe.billing_portal.Session.create(
        customer=customer_id, return_url=return_url,
    )
    return session.url


# ═══════════════════════════════════════════════════════════
# WEBHOOK HANDLERS
# ═══════════════════════════════════════════════════════════

def handle_checkout_completed(event: dict, db: Session) -> None:
    session = event["data"]["object"]
    mode = session.get("mode")

    # Разовая покупка — не меняем тир
    if mode == "payment":
        metadata = session.get("metadata", {})
        logger.info(
            "Report purchased: user=%s type=%s chart=%s",
            metadata.get("user_id"), metadata.get("report_type"), metadata.get("chart_id"),
        )
        # TODO: запустить генерацию PDF и отправить на email
        return

    # Подписка
    user_id = session.get("metadata", {}).get("user_id")
    tier = session.get("metadata", {}).get("tier", "pro")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    if not user_id:
        return

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return

    user.tier = tier
    user.stripe_customer_id = customer_id

    from datetime import datetime
    period_end = None
    try:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        period_end = datetime.fromtimestamp(stripe_sub["current_period_end"])
    except Exception as e:
        logger.warning("Could not retrieve period_end: %s", e)

    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if sub:
        sub.stripe_subscription_id = subscription_id
        sub.stripe_price_id = TIER_PRICE_MAP.get((tier, "monthly"), "")
        sub.status = "active"
        sub.tier = tier
        sub.current_period_end = period_end
    else:
        sub = Subscription(
            user_id=user_id,
            stripe_subscription_id=subscription_id,
            stripe_customer_id=customer_id,
            stripe_price_id=TIER_PRICE_MAP.get((tier, "monthly"), ""),
            status="active", tier=tier, current_period_end=period_end,
        )
        db.add(sub)

    db.commit()
    logger.info("Subscription activated: user=%s tier=%s", user_id, tier)


def handle_subscription_updated(event: dict, db: Session) -> None:
    subscription = event["data"]["object"]
    subscription_id = subscription["id"]
    status_val = subscription["status"]

    items = subscription.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else None
    tier = PRICE_TIER_MAP.get(price_id, "free") if price_id else "free"

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()

    if sub:
        sub.status = status_val
        sub.tier = tier
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            user.tier = tier if status_val in ("active", "trialing") else "free"
            db.commit()


def handle_subscription_deleted(event: dict, db: Session) -> None:
    subscription = event["data"]["object"]
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription["id"]
    ).first()
    if sub:
        sub.status = "canceled"
        sub.tier = "free"
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            user.tier = "free"
        db.commit()


def handle_payment_failed(event: dict, db: Session) -> None:
    invoice = event["data"]["object"]
    logger.warning(
        "Payment failed: customer=%s subscription=%s",
        invoice.get("customer"), invoice.get("subscription"),
    )
