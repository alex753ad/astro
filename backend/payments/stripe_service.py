"""Stripe service layer.

Handles:
- Customer creation / retrieval
- Checkout Session creation (redirect flow)
- Customer Portal session
- Webhook event processing
- Subscription tier mapping
"""

from __future__ import annotations

import logging
from typing import Optional

import stripe
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import User, Subscription

settings = get_settings()
logger = logging.getLogger("astro.stripe")

# Initialize Stripe SDK lazily to avoid silent failures when key is missing at import
def _init_stripe() -> None:
    if not stripe.api_key:
        stripe.api_key = settings.stripe_secret_key

# ── Tier ↔ Price mapping ──
# In production these would be Stripe Price IDs from the dashboard.
# Set them as env vars; placeholders below.
TIER_PRICE_MAP: dict[str, str] = {
    "pro": settings.stripe_price_id_pro,
    "premium": settings.stripe_price_id_premium,
}

PRICE_TIER_MAP: dict[str, str] = {v: k for k, v in TIER_PRICE_MAP.items() if v}


# ═══════════════════════════════════════════════════════════
# CUSTOMER MANAGEMENT
# ═══════════════════════════════════════════════════════════

def get_or_create_customer(user: User, db: Session) -> str:
    """Return existing Stripe customer ID, or create one and persist it."""
    _init_stripe()
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": user.id},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    logger.info("Stripe customer created: %s for user %s", customer.id, user.id)
    return customer.id


# ═══════════════════════════════════════════════════════════
# CHECKOUT
# ═══════════════════════════════════════════════════════════

def create_checkout_session(
    user: User,
    tier: str,
    success_url: str,
    cancel_url: str,
    db: Session,
) -> str:
    """Create a Stripe Checkout Session and return its URL.

    Uses redirect flow (not embedded) — simpler and more secure.
    """
    price_id = TIER_PRICE_MAP.get(tier)
    if not price_id:
        raise ValueError(f"Unknown tier: {tier}")

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

    logger.info(
        "Checkout session created: %s for user %s (tier=%s)",
        session.id, user.id, tier,
    )
    return session.url


# ═══════════════════════════════════════════════════════════
# CUSTOMER PORTAL
# ═══════════════════════════════════════════════════════════

def create_portal_session(user: User, return_url: str, db: Session) -> str:
    """Create a Stripe Customer Portal session URL.

    Allows users to manage subscriptions, update payment, cancel, etc.
    """
    customer_id = get_or_create_customer(user, db)

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


# ═══════════════════════════════════════════════════════════
# WEBHOOK PROCESSING
# ═══════════════════════════════════════════════════════════

def handle_checkout_completed(event: dict, db: Session) -> None:
    """Process checkout.session.completed — activate subscription."""
    session = event["data"]["object"]
    user_id = session.get("metadata", {}).get("user_id")
    tier = session.get("metadata", {}).get("tier", "pro")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    if not user_id:
        logger.warning("checkout.session.completed without user_id in metadata")
        return

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error("User %s not found for checkout completion", user_id)
        return

    # Update user tier
    user.tier = tier
    user.stripe_customer_id = customer_id

    # Create or update subscription record
    from datetime import datetime
    period_end = None
    try:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        period_end = datetime.fromtimestamp(stripe_sub["current_period_end"])
    except Exception as e:
        logger.warning("Could not retrieve subscription period_end: %s", e)

    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .first()
    )
    if sub:
        sub.stripe_subscription_id = subscription_id
        sub.stripe_price_id = TIER_PRICE_MAP.get(tier, "")
        sub.status = "active"
        sub.tier = tier
        sub.current_period_end = period_end
    else:
        sub = Subscription(
            user_id=user_id,
            stripe_subscription_id=subscription_id,
            stripe_customer_id=customer_id,
            stripe_price_id=TIER_PRICE_MAP.get(tier, ""),
            status="active",
            tier=tier,
            current_period_end=period_end,
        )
        db.add(sub)

    db.commit()
    logger.info("Subscription activated: user=%s tier=%s", user_id, tier)


def handle_subscription_updated(event: dict, db: Session) -> None:
    """Process customer.subscription.updated — plan change or cancellation."""
    subscription = event["data"]["object"]
    subscription_id = subscription["id"]
    status_val = subscription["status"]  # active, past_due, canceled, etc.
    user_id = subscription.get("metadata", {}).get("user_id")

    # Determine tier from price
    items = subscription.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else None
    tier = PRICE_TIER_MAP.get(price_id, "free") if price_id else "free"

    sub = (
        db.query(Subscription)
        .filter(Subscription.stripe_subscription_id == subscription_id)
        .first()
    )

    if sub:
        sub.status = status_val
        sub.tier = tier
        sub.stripe_price_id = price_id or sub.stripe_price_id

        # Update user tier based on subscription status
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            if status_val in ("active", "trialing"):
                user.tier = tier
            elif status_val in ("canceled", "unpaid", "past_due"):
                user.tier = "free"
            db.commit()
            logger.info(
                "Subscription updated: user=%s status=%s tier=%s",
                sub.user_id, status_val, tier,
            )
    else:
        logger.warning(
            "Subscription %s not found in DB for update event", subscription_id
        )


def handle_subscription_deleted(event: dict, db: Session) -> None:
    """Process customer.subscription.deleted — downgrade user to free."""
    subscription = event["data"]["object"]
    subscription_id = subscription["id"]
    customer_id = subscription.get("customer")

    sub = (
        db.query(Subscription)
        .filter(Subscription.stripe_subscription_id == subscription_id)
        .first()
    )
    if sub:
        sub.status = "canceled"
        sub.tier = "free"
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            user.tier = "free"
        db.commit()
        logger.info("Subscription deleted: user=%s → free", sub.user_id)
    else:
        logger.warning("Subscription %s not found for deletion event", subscription_id)


def handle_payment_failed(event: dict, db: Session) -> None:
    """Process invoice.payment_failed — notify and optionally downgrade."""
    invoice = event["data"]["object"]
    customer_id = invoice.get("customer")
    subscription_id = invoice.get("subscription")

    logger.warning(
        "Payment failed: customer=%s subscription=%s",
        customer_id, subscription_id,
    )

    # Find user by stripe customer ID
    user = (
        db.query(User)
        .filter(User.stripe_customer_id == customer_id)
        .first()
    )
    if user:
        # Don't immediately downgrade — Stripe retries.
        # Just log for now. Stripe's dunning handles further retries.
        # After final failure, subscription.updated with status=canceled fires.
        logger.warning(
            "Payment failed for user %s (%s). Stripe will retry.",
            user.id, user.email,
        )
        # TODO: Send notification email about payment failure
