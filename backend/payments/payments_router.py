"""Stripe payments API router.

Endpoints:
  POST /api/v1/payments/checkout       — create Stripe Checkout session
  POST /api/v1/payments/portal         — create Stripe Customer Portal session
  POST /api/v1/payments/webhook        — Stripe webhook receiver
  GET  /api/v1/payments/subscription   — current subscription info
"""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
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
    handle_checkout_completed,
    handle_subscription_updated,
    handle_subscription_deleted,
    handle_payment_failed,
    create_report_checkout_session,
    consume_report_token,
)

logger = logging.getLogger("astro.payments")
settings = get_settings()

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


# ═══════════════════════════════════════════════════════════
# CHECKOUT
# ═══════════════════════════════════════════════════════════

@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Create Stripe Checkout session",
)
async def checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout session.

    Returns a URL to redirect the user to Stripe's hosted checkout page.
    """
    if data.tier not in ("lite", "pro", "premium"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tier must be 'lite', 'pro' or 'premium'.",
        )

    if user.tier == data.tier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You are already on the {data.tier} plan.",
        )

    active_sub = db.query(Subscription).filter(
        Subscription.user_id == user.id,
        Subscription.status == "active",
    ).first()
    if active_sub and user.tier != "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У вас уже есть активная подписка. Управлять тарифом можно через Личный кабинет Stripe.",
        )

    try:
        url = create_checkout_session(
            user=user,
            tier=data.tier,
            billing_period=data.billing_period,
            success_url=data.success_url,
            cancel_url=data.cancel_url,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.StripeError as e:
        logger.exception("Stripe checkout error")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return CheckoutResponse(checkout_url=url)


# ═══════════════════════════════════════════════════════════
# CUSTOMER PORTAL
# ═══════════════════════════════════════════════════════════

@router.post(
    "/portal",
    response_model=PortalResponse,
    summary="Create Stripe Customer Portal session",
)
async def portal(
    data: PortalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Stripe Customer Portal session.

    Allows users to manage billing, update payment method, or cancel.
    """
    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found.",
        )

    try:
        url = create_portal_session(user, data.return_url, db)
    except stripe.error.StripeError as e:
        logger.exception("Stripe portal error")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return PortalResponse(portal_url=url)


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION INFO
# ═══════════════════════════════════════════════════════════

@router.get(
    "/subscription",
    response_model=SubscriptionResponse,
    summary="Get current subscription",
)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current user's subscription status."""
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id)
        .first()
    )

    return SubscriptionResponse(
        tier=user.tier,
        status=sub.status if sub else "none",
        stripe_subscription_id=sub.stripe_subscription_id if sub else None,
        current_period_end=sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
    )


# ═══════════════════════════════════════════════════════════
# WEBHOOK
# ═══════════════════════════════════════════════════════════

@router.post(
    "/webhook",
    summary="Stripe webhook receiver",
    include_in_schema=False,  # Don't expose in OpenAPI docs
)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive and process Stripe webhook events.

    Verifies the webhook signature to ensure authenticity.

    Handled events:
    - checkout.session.completed   → activate subscription
    - customer.subscription.updated → plan change / cancellation
    - invoice.payment_failed       → log + notify
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        from backend.payments.stripe_service import construct_webhook_event
        event = construct_webhook_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except ValueError:
        logger.warning("Invalid Stripe webhook payload")
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = event.get("type", "")
    logger.info("Stripe webhook received: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            handle_checkout_completed(event, db)
        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(event, db)
        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(event, db)
        elif event_type == "invoice.payment_failed":
            handle_payment_failed(event, db)
        else:
            logger.debug("Unhandled Stripe event: %s", event_type)
    except Exception:
        logger.exception("Error processing Stripe event %s", event_type)
        if settings.testing:
            raise
        # Return 200 anyway — Stripe retries on non-2xx,
        # and we don't want infinite retries for a processing bug.

    return JSONResponse(content={"received": True}, status_code=200)


# ═══════════════════════════════════════════════════════════
# PAY-PER-REPORT (task 7)
# ═══════════════════════════════════════════════════════════

from fastapi.responses import FileResponse
from pydantic import BaseModel as _BaseModel

class ReportCheckoutRequest(_BaseModel):
    report_type: str = "basic"   # basic | extended
    chart_id: str
    success_url: str = ""
    cancel_url: str = ""


@router.post(
    "/report-checkout",
    summary="Create one-time payment session for PDF report",
)
async def report_checkout(
    data: ReportCheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create Stripe Checkout for a one-time report purchase (no subscription required)."""
    if data.report_type not in ("basic", "extended"):
        raise HTTPException(status_code=400, detail="report_type must be 'basic' or 'extended'")
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
    return {"checkout_url": url}


@router.get(
    "/report/download/{token}",
    summary="Download PDF report by one-time token",
    include_in_schema=True,
)
async def download_report(token: str, db: Session = Depends(get_db)):
    """Verify one-time token and return PDF. Token is deleted after successful download."""
    import os
    chart_id = consume_report_token(token)
    if not chart_id:
        raise HTTPException(status_code=404, detail="Token expired or not found")

    # Look for generated PDF
    pdf_path = f"/tmp/reports/{chart_id}.pdf"
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Report not ready yet, please try again later")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"astrea_report_{chart_id[:8]}.pdf",
    )
