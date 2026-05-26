"""Stripe payments API router."""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models import User, Subscription
from backend.schemas import (
    CheckoutRequest,
    PortalRequest,
    CheckoutResponse,
    PortalResponse,
    SubscriptionResponse,
    MessageResponse,
)
from backend.auth.dependencies import get_current_user
from backend.payments.stripe_service import (
    create_checkout_session,
    create_portal_session,
    create_report_checkout_session,
    handle_checkout_completed,
    handle_subscription_updated,
    handle_payment_failed,
)

logger = logging.getLogger("astro.payments")
settings = get_settings()

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


# ═══════════════════════════════════════════════════════════
# CHECKOUT — подписка
# ═══════════════════════════════════════════════════════════

@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.tier not in ("pro", "premium"):
        raise HTTPException(status_code=400, detail="Tier must be 'pro' or 'premium'.")
    if user.tier == data.tier:
        raise HTTPException(status_code=400, detail=f"You are already on the {data.tier} plan.")

    try:
        url = create_checkout_session(
            user=user, tier=data.tier,
            success_url=data.success_url, cancel_url=data.cancel_url, db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return CheckoutResponse(checkout_url=url)


# ═══════════════════════════════════════════════════════════
# CHECKOUT — разовая покупка PDF-отчёта
# ═══════════════════════════════════════════════════════════

class ReportCheckoutRequest(BaseModel):
    report_type: str   # "basic" | "extended" | "synastry"
    chart_id: str
    success_url: str = ""
    cancel_url: str = ""


@router.post("/checkout/report", response_model=CheckoutResponse)
async def checkout_report(
    data: ReportCheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Разовая покупка PDF-отчёта (mode=payment, не subscription)."""
    if data.report_type not in ("basic", "extended", "synastry"):
        raise HTTPException(status_code=400, detail="Unknown report_type.")

    try:
        url = create_report_checkout_session(
            user=user,
            report_type=data.report_type,
            chart_id=data.chart_id,
            success_url=data.success_url,
            cancel_url=data.cancel_url,
            db=db,
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return CheckoutResponse(checkout_url=url)


# ═══════════════════════════════════════════════════════════
# CUSTOMER PORTAL
# ═══════════════════════════════════════════════════════════

@router.post("/portal", response_model=PortalResponse)
async def portal(
    data: PortalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription found.")

    try:
        url = create_portal_session(user, data.return_url, db)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return PortalResponse(portal_url=url)


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION INFO
# ═══════════════════════════════════════════════════════════

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    return SubscriptionResponse(
        tier=user.tier,
        status=sub.status if sub else "none",
        stripe_subscription_id=sub.stripe_subscription_id if sub else None,
        current_period_end=sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
    )


# ═══════════════════════════════════════════════════════════
# WEBHOOK
# ═══════════════════════════════════════════════════════════

@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header,
            secret=settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = event.get("type", "")
    logger.info("Stripe webhook: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            handle_checkout_completed(event, db)
        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(event, db)
        elif event_type == "invoice.payment_failed":
            handle_payment_failed(event, db)
    except Exception:
        logger.exception("Error processing Stripe event %s", event_type)

    return JSONResponse(content={"received": True}, status_code=200)
