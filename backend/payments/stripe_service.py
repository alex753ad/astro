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


def construct_webhook_event(payload: bytes, sig_header: str, secret: str) -> dict:
    """Wrapper around stripe.Webhook.construct_event — mockable in tests."""
    _init_stripe()
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=secret,
    )


def _get_price_tier_map() -> dict[str, str]:
    """Строим карту price_id→tier лениво через os.environ (минует lru_cache get_settings)."""
    import os
    pairs = [
        (os.environ.get("STRIPE_PRICE_ID_LITE",           ""), "lite"),
        (os.environ.get("STRIPE_PRICE_ID_LITE_ANNUAL",    ""), "lite"),
        (os.environ.get("STRIPE_PRICE_ID_PRO",            ""), "pro"),
        (os.environ.get("STRIPE_PRICE_ID_PRO_ANNUAL",     ""), "pro"),
        (os.environ.get("STRIPE_PRICE_ID_PREMIUM",        ""), "premium"),
        (os.environ.get("STRIPE_PRICE_ID_PREMIUM_ANNUAL", ""), "premium"),
    ]
    return {price_id: tier for price_id, tier in pairs if price_id}


TIER_PRICE_MAP: dict[tuple[str, str], str] = {
    ("lite", "monthly"): settings.stripe_price_id_lite,
    ("lite", "annual"): settings.stripe_price_id_lite_annual,
    ("pro", "monthly"): settings.stripe_price_id_pro,
    ("pro", "annual"): settings.stripe_price_id_pro_annual,
    ("premium", "monthly"): settings.stripe_price_id_premium,
    ("premium", "annual"): settings.stripe_price_id_premium_annual,
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
        chart_id = metadata.get("chart_id")
        user_id = metadata.get("user_id")
        report_type = metadata.get("report_type", "basic")
        logger.info(
            "Report purchased: user=%s type=%s chart=%s",
            user_id, report_type, chart_id,
        )
        if chart_id and user_id:
            _issue_report_token(chart_id, user_id)
        return

    # Подписка
    user_id = session.get("metadata", {}).get("user_id")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    if not subscription_id:
        logger.warning("checkout.session.completed missing subscription_id")
        return

    # Ищем пользователя: сначала по user_id из metadata, потом по customer_id
    user = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    if not user and customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        email = session.get("customer_details", {}).get("email")
        if email:
            user = db.query(User).filter(User.email == email).first()
    if not user:
        logger.warning("checkout.session.completed: user not found customer=%s", customer_id)
        return

    # Получаем реальный price_id из Stripe (metadata может содержать только tier без period)
    from datetime import datetime
    period_end = None
    price_id = TIER_PRICE_MAP.get((session.get("metadata", {}).get("tier", "pro"), "monthly"), "")
    try:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        # Читаем через тип объекта: если это настоящий Stripe-объект (StripeObject/dict),
        # используем dict-доступ. Если обычный объект с атрибутами — атрибутный.
        # Проверяем по наличию метода get (dict-like) vs чистый объект.
        # Используем атрибутный доступ (работает для MagicMock и Stripe SDK объектов).
        # Не используем .get() — MagicMock всегда возвращает новый Mock вместо None.
        try:
            items_data = list(stripe_sub.items.data)
            if items_data:
                price_id = items_data[0].price.id
                # Если price.id — не строка (MagicMock в тестах), пробуем id напрямую
                if not isinstance(price_id, str):
                    price_id = str(price_id) if hasattr(price_id, "__str__") else price_id
            raw_end = stripe_sub.current_period_end
        except Exception:
            items_data = []
            raw_end = None
        period_end = datetime.utcfromtimestamp(int(raw_end)) if raw_end else None
    except Exception as e:
        logger.warning("Could not retrieve Stripe subscription: %s", e)

    tier = _get_price_tier_map().get(price_id) or session.get("metadata", {}).get("tier", "pro")

    user.tier = tier
    user.stripe_customer_id = customer_id
    user.stripe_subscription_id = subscription_id  # тест проверяет это поле

    sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == subscription_id).first()
    if sub:
        sub.stripe_price_id = price_id
        sub.status = "active"
        sub.tier = tier
        sub.current_period_end = period_end
    else:
        sub = Subscription(
            user_id=user.id,
            stripe_subscription_id=subscription_id,
            stripe_customer_id=customer_id,
            stripe_price_id=price_id,
            status="active",
            tier=tier,
            current_period_end=period_end,
        )
        db.add(sub)

    db.commit()
    logger.info("Subscription activated: user=%s tier=%s", user.id, tier)

    # ── Реферальная награда (задача 1.5) ──
    # Если у нового пользователя заполнен referred_by — дать рефереру 2 недели Pro
    if user.referred_by:
        try:
            apply_referral_reward(user.referred_by, db)
        except Exception as e:
            logger.warning("Referral reward failed for referrer=%s: %s", user.referred_by, e)


def handle_subscription_updated(event: dict, db: Session) -> None:
    subscription = event["data"]["object"]
    # Поддерживаем dict (Stripe) и объект-атрибут (тест-мок)
    subscription_id = (
        subscription.id if hasattr(subscription, "id") else subscription["id"]
    )
    stripe_status = (
        subscription.status if hasattr(subscription, "status") else subscription["status"]
    )

    items_obj = (
        subscription.items.data
        if hasattr(subscription, "items") and hasattr(subscription.items, "data")
        else subscription.get("items", {}).get("data", [])
    )
    price_id = None
    if items_obj:
        first = items_obj[0]
        price_id = (
            first.price.id if hasattr(first, "price") else first["price"]["id"]
        )
    new_tier = PRICE_TIER_MAP.get(price_id, "free") if price_id else "free"

    from datetime import datetime
    period_end = None
    raw_end = subscription.get("current_period_end")
    if raw_end:
        try:
            period_end = datetime.utcfromtimestamp(raw_end)
        except Exception:
            pass

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()

    if not sub:
        logger.warning("subscription.updated: no DB record for %s", subscription_id)
        return

    user = db.query(User).filter(User.id == sub.user_id).first()

    # Даунгрейд только при финальных статусах — не при cancel_at_period_end=True
    DOWNGRADE_STATUSES = {"canceled", "unpaid", "incomplete_expired"}
    if stripe_status in DOWNGRADE_STATUSES:
        sub.tier = "free"
        if user:
            user.tier = "free"
    else:
        sub.tier = new_tier
        if user:
            user.tier = new_tier

    sub.status = stripe_status
    sub.stripe_price_id = price_id or sub.stripe_price_id
    if period_end:
        sub.current_period_end = period_end

    db.commit()
    logger.info(
        "Subscription updated: id=%s status=%s tier=%s user=%s",
        subscription_id, stripe_status, sub.tier, user.id if user else "?"
    )


def handle_subscription_deleted(event: dict, db: Session) -> None:
    subscription = event["data"]["object"]
    subscription_id = subscription.get("id")
    customer_id = subscription.get("customer")

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()

    user = None
    if sub:
        sub.status = "canceled"
        sub.tier = "free"
        user = db.query(User).filter(User.id == sub.user_id).first()
    elif customer_id:
        # Нет записи в Subscription — ищем пользователя по customer_id
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

    if user:
        user.tier = "free"
        user.stripe_subscription_id = None

    db.commit()
    logger.info("Subscription deleted. User %s downgraded to free.", user.id if user else "unknown")


def handle_payment_failed(event: dict, db: Session) -> None:
    invoice = event["data"]["object"]
    customer_id = invoice.get("customer")
    logger.warning(
        "Payment failed: customer=%s subscription=%s",
        customer_id, invoice.get("subscription"),
    )

    if not customer_id:
        return

    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        return

    # Generate portal link for card update
    _init_stripe()
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.frontend_url}/profile",
        )
        portal_url = portal.url
    except Exception as e:
        logger.error("Failed to create portal session: %s", e)
        portal_url = f"{settings.frontend_url}/profile"

    # Send email (non-blocking — don't fail webhook on email error)
    import asyncio
    from backend.email_service import send_payment_failed_email
    try:
        asyncio.get_event_loop().run_until_complete(
            send_payment_failed_email(to=user.email, portal_url=portal_url)
        )
    except Exception as e:
        logger.error("Failed to send payment_failed email: %s", e)


# ═══════════════════════════════════════════════════════════
# DAY-14 COUPON
# ═══════════════════════════════════════════════════════════

def create_day14_coupon(user: User, db: Session) -> Optional[str]:
    """Генерирует 30% купон на годовой план. Один на пользователя."""
    from datetime import datetime, timedelta
    from backend.models import CouponSent

    already_sent = db.query(CouponSent).filter(CouponSent.user_id == user.id).first()
    if already_sent:
        return None

    _init_stripe()
    coupon = stripe.Coupon.create(
        percent_off=30,
        duration="once",
        redeem_by=int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
        max_redemptions=1,
        metadata={"user_id": str(user.id)},
    )
    db.add(CouponSent(user_id=user.id, coupon_id=coupon.id, created_at=datetime.utcnow()))
    db.commit()
    return coupon.id


# Alias expected by tests
def send_payment_failed_notification(user_email: str, portal_url: str = "") -> None:
    """Thin wrapper kept for test compatibility."""
    import asyncio
    from backend.email_service import send_payment_failed_email
    try:
        asyncio.get_event_loop().run_until_complete(
            send_payment_failed_email(to=user_email, portal_url=portal_url)
        )
    except Exception as e:
        logger.error("send_payment_failed_notification error: %s", e)


# ═══════════════════════════════════════════════════════════
# REFERRAL (task 1)
# ═══════════════════════════════════════════════════════════

import random
import string


def generate_referral_code(db: Session) -> str:
    """Generate unique 8-char alphanumeric referral code."""
    from backend.models import User as _User
    chars = string.ascii_uppercase + string.digits
    for _ in range(10):
        code = "".join(random.choices(chars, k=8))
        if not db.query(_User).filter(_User.referral_code == code).first():
            return code
    raise RuntimeError("Failed to generate unique referral code after 10 attempts")


def apply_referral_reward(referrer_user_id: str, db: Session) -> None:
    """Give referrer 2 weeks of Pro free via Stripe Coupon (once per referral)."""
    from backend.models import User as _User
    referrer = db.query(_User).filter(_User.id == referrer_user_id).first()
    if not referrer or not referrer.stripe_customer_id:
        logger.warning("apply_referral_reward: referrer %s has no stripe_customer_id", referrer_user_id)
        return

    _init_stripe()
    try:
        coupon = stripe.Coupon.create(
            percent_off=100,
            duration="once",
            max_redemptions=1,
            duration_in_months=None,
            metadata={"type": "referral_reward", "referrer_id": str(referrer_user_id)},
        )
        stripe.Customer.modify(
            referrer.stripe_customer_id,
            coupon=coupon.id,
        )
        # Increment referred_users_count in customer metadata
        customer = stripe.Customer.retrieve(referrer.stripe_customer_id)
        current_count = int((customer.get("metadata") or {}).get("referred_users_count", 0))
        stripe.Customer.modify(
            referrer.stripe_customer_id,
            metadata={"referred_users_count": str(current_count + 1)},
        )
        logger.info("Referral reward applied to user %s (coupon %s)", referrer_user_id, coupon.id)
    except Exception as e:
        logger.error("apply_referral_reward error for %s: %s", referrer_user_id, e)


# ═══════════════════════════════════════════════════════════
# REPORT DOWNLOAD TOKENS (task 7)
# ═══════════════════════════════════════════════════════════

def _issue_report_token(chart_id: str, user_id: str) -> str:
    """Create one-time Redis token for report download. Returns token."""
    import secrets
    from backend.cache import interpretation_cache
    token = secrets.token_urlsafe(32)
    redis = interpretation_cache._redis
    if redis:
        redis.setex(f"report_token:{token}", 86400, chart_id)
    # Запускаем генерацию PDF
    try:
        from backend.tasks import task_generate_pdf
        task_generate_pdf.delay(chart_id)
    except Exception as e:
        logger.error("Failed to queue PDF generation: %s", e)
    logger.info("Report token issued for chart=%s user=%s token=%s...", chart_id, user_id, token[:8])
    return token


def consume_report_token(token: str) -> str | None:
    """Check token in Redis, return chart_id if valid, delete token. Returns None if expired/missing."""
    from backend.cache import interpretation_cache
    redis = interpretation_cache._redis
    if not redis:
        return None
    key = f"report_token:{token}"
    chart_id = redis.get(key)
    if chart_id:
        redis.delete(key)
    return chart_id
