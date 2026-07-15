"""Robokassa payments router.

Endpoints:
  POST /api/v1/payments/checkout          — создать ссылку на оплату
  POST /api/v1/payments/robokassa/result  — вебхук от Robokassa
  GET  /api/v1/payments/subscription      — текущая подписка
  POST /api/v1/payments/admin/set-tier    — принудительно сменить тариф (только для ADMIN_EMAIL)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status, Form
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Subscription
from backend.schemas import CheckoutRequest, CheckoutResponse, SubscriptionResponse
from backend.auth.dependencies import get_current_user
from backend.payments.robokassa_service import (
    create_payment_url,
    verify_payment,
    activate_subscription,
    TIER_PRICES,
)
from backend.redis_client import get_redis

logger = logging.getLogger("astro.payments")

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


# ── Checkout ───────────────────────────────────────────────

@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.tier not in ("lite", "pro", "premium"):
        raise HTTPException(400, "Tier must be 'lite', 'pro' or 'premium'.")

    if user.tier == data.tier:
        raise HTTPException(400, f"Вы уже на тарифе {data.tier}.")

    try:
        url = create_payment_url(user=user, tier=data.tier, billing_period=data.billing_period)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return CheckoutResponse(checkout_url=url)


# ── Stripe webhook (legacy — kept for tests) ──────────────

# Legacy Stripe webhook удалён: провайдер — Robokassa. Маршрут закрыт, чтобы не
# держать неиспользуемую платёжную поверхность. При необходимости вернуть —
# восстановить из истории git вместе с backend/payments/stripe_service.py.


# ── Robokassa webhook ──────────────────────────────────────

@router.post("/robokassa/result", include_in_schema=False)
async def robokassa_result(request: Request, db: Session = Depends(get_db)):
    """
    Robokassa вызывает этот URL после успешной оплаты.
    Ответ должен быть строго: OK{InvId}
    """
    form = dict(await request.form())
    inv_id = form.get("InvId", "")

    valid, user_id, tier, period = verify_payment(form)

    if not valid:
        logger.warning("Robokassa: invalid signature, InvId=%s", inv_id)
        return PlainTextResponse("bad signature", status_code=400)

    if not user_id or not tier:
        logger.warning("Robokassa: missing Shp params, InvId=%s", inv_id)
        return PlainTextResponse("missing params", status_code=400)

    # Сверка суммы: подпись Robokassa покрывает OutSum, но добавляем проверку
    # соответствия ожидаемой цене тарифа как defense-in-depth.
    expected = TIER_PRICES.get((tier, period))
    try:
        paid = float(form.get("OutSum", "0"))
    except ValueError:
        paid = -1.0
    if expected is None or abs(paid - float(expected)) > 0.01:
        logger.warning(
            "Robokassa: amount mismatch InvId=%s tier=%s period=%s paid=%s expected=%s",
            inv_id, tier, period, paid, expected,
        )
        return PlainTextResponse("amount mismatch", status_code=400)

    # Идемпотентность / anti-replay: обрабатываем каждый InvId только один раз.
    try:
        first_time = await get_redis().set(f"robokassa:inv:{inv_id}", "1", nx=True, ex=90 * 24 * 3600)
    except Exception as exc:  # noqa: BLE001
        logger.error("Robokassa idempotency store failed, proceeding: %s", exc)
        first_time = True
    if not first_time:
        logger.info("Robokassa: duplicate InvId=%s ignored", inv_id)
        return PlainTextResponse(f"OK{inv_id}")

    try:
        activate_subscription(user_id=user_id, tier=tier, period=period, db=db)
    except Exception as e:
        logger.exception("Robokassa: activate_subscription failed")
        return PlainTextResponse("internal error", status_code=500)

    logger.info("Robokassa: payment OK, InvId=%s user=%s tier=%s", inv_id, user_id, tier)
    return PlainTextResponse(f"OK{inv_id}")


# ── Admin: set tier ───────────────────────────────────────

@router.post("/admin/set-tier")
async def admin_set_tier(
    request: Request,
    admin: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Принудительно сменить тариф без оплаты. Только для ADMIN_EMAIL."""
    import os
    from datetime import datetime, timedelta

    admin_emails = [e.strip().lower() for e in os.getenv("ADMIN_EMAIL", "").split(",") if e.strip()]
    if not admin_emails or admin.email.lower() not in admin_emails:
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    tier = body.get("tier", "")
    user_id = body.get("user_id")
    if tier not in ("free", "lite", "pro", "premium"):
        raise HTTPException(400, "tier must be: free, lite, pro, premium")

    # Если передан user_id — меняем тариф этому пользователю, иначе себе
    if user_id:
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise HTTPException(404, "User not found")
    else:
        target = admin

    target.tier = tier
    sub = db.query(Subscription).filter(Subscription.user_id == target.id).first()

    if tier == "free":
        if sub:
            sub.status = "canceled"
            sub.tier = "free"
    else:
        period_end = datetime.utcnow() + timedelta(days=3650)
        if sub:
            sub.tier = tier
            sub.status = "active"
            sub.current_period_end = period_end
        else:
            db.add(Subscription(
                user_id=target.id,
                stripe_price_id=f"admin_{tier}",
                status="active",
                tier=tier,
                current_period_end=period_end,
            ))

    db.commit()
    logger.info("Admin set tier: admin=%s target=%s tier=%s", admin.email, target.email, tier)
    return {"ok": True, "tier": tier}


# ── Subscription info ──────────────────────────────────────

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    return SubscriptionResponse(
        tier=user.tier,
        status=sub.status if sub else "none",
        stripe_subscription_id=None,
        current_period_end=sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
    )
