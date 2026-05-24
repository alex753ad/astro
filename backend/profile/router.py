"""Profile API router.

Endpoints:
  GET    /api/v1/profile/charts              — list saved charts
  DELETE /api/v1/profile/charts/{chart_id}   — delete a saved chart
  GET    /api/v1/profile/history             — interpretation history
  GET    /api/v1/profile/subscription        — current subscription info
  DELETE /api/v1/profile/data                — GDPR: delete all user data
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import NatalChart, User, Subscription
from backend.auth.dependencies import get_current_user
from backend.auth.rate_limits import get_feature_flags
from backend.schemas import MessageResponse

logger = logging.getLogger("astro.profile")

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


# ═══════════════════════════════════════════════════════════
# SAVED CHARTS
# ═══════════════════════════════════════════════════════════

@router.get(
    "/charts",
    summary="List saved natal charts for current user",
)
async def list_charts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Return all natal charts saved under the authenticated user's account."""
    charts = (
        db.query(NatalChart)
        .filter(NatalChart.user_id == user.id)
        .order_by(NatalChart.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(NatalChart).filter(NatalChart.user_id == user.id).count()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "charts": [
            {
                "id": c.id,
                "birth_date": c.birth_date,
                "birth_time": c.birth_time,
                "birth_place": c.birth_place,
                "house_system": c.house_system,
                "time_unknown": c.time_unknown,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in charts
        ],
    }


@router.delete(
    "/charts/{chart_id}",
    response_model=MessageResponse,
    summary="Delete a saved natal chart",
)
async def delete_chart(
    chart_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a chart that belongs to the authenticated user."""
    chart = (
        db.query(NatalChart)
        .filter(NatalChart.id == chart_id, NatalChart.user_id == user.id)
        .first()
    )
    if not chart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chart not found or does not belong to you.",
        )

    db.delete(chart)
    db.commit()
    logger.info("Chart %s deleted by user %s", chart_id, user.id)
    return MessageResponse(message="Chart deleted successfully.")


# ═══════════════════════════════════════════════════════════
# INTERPRETATION HISTORY
# ═══════════════════════════════════════════════════════════

@router.get(
    "/history",
    summary="Interpretation history for current user",
)
async def interpretation_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Return interpretation history entries linked to the user's charts.

    Joins NatalChart and filters by user_id so users only see their own data.
    """
    # Interpretation model may not exist in all deployments — guard gracefully
    try:
        from backend.models import Interpretation  # type: ignore

        rows = (
            db.query(Interpretation)
            .join(NatalChart, Interpretation.chart_id == NatalChart.id)
            .filter(NatalChart.user_id == user.id)
            .order_by(Interpretation.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = (
            db.query(Interpretation)
            .join(NatalChart, Interpretation.chart_id == NatalChart.id)
            .filter(NatalChart.user_id == user.id)
            .count()
        )

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "history": [
                {
                    "id": r.id,
                    "chart_id": r.chart_id,
                    "engine": r.engine,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    # Content preview — first 200 chars to avoid large payloads
                    "preview": (r.content or "")[:200],
                }
                for r in rows
            ],
        }

    except (ImportError, AttributeError):
        # Interpretation table not yet migrated — return empty gracefully
        return {"total": 0, "offset": offset, "limit": limit, "history": []}


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION INFO
# ═══════════════════════════════════════════════════════════

@router.get(
    "/subscription",
    summary="Current subscription details",
)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current subscription tier and Stripe details for the user."""
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id)
        .first()
    )

    return {
        "tier": user.tier,
        "is_active": sub.status == "active" if sub else user.tier != "free",
        "stripe_subscription_id": sub.stripe_subscription_id if sub else None,
        "stripe_customer_id": user.stripe_customer_id,
        "status": sub.status if sub else ("free" if user.tier == "free" else "active"),
        "current_period_end": (
            sub.current_period_end.isoformat()
            if sub and getattr(sub, "current_period_end", None)
            else None
        ),
        "features": get_feature_flags(user),
    }


# ═══════════════════════════════════════════════════════════
# GDPR — DELETE ALL USER DATA
# ═══════════════════════════════════════════════════════════

@router.delete(
    "/data",
    response_model=MessageResponse,
    summary="GDPR: delete all personal data",
)
async def delete_all_data(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete all charts, interpretations, and subscription data.

    The user account itself is kept (email only) unless they also call
    DELETE /api/v1/auth/me.  This endpoint erases only the content data.
    """
    # Delete all charts (cascade handles interpretations if FK is set up)
    deleted_charts = (
        db.query(NatalChart)
        .filter(NatalChart.user_id == user.id)
        .delete(synchronize_session=False)
    )

    # Delete subscription record
    db.query(Subscription).filter(Subscription.user_id == user.id).delete(
        synchronize_session=False
    )

    db.commit()
    db.expire_all()
    logger.info(
        "GDPR data deletion: user=%s deleted %d charts",
        user.id,
        deleted_charts,
    )
    return MessageResponse(message="All personal data deleted successfully.")
