"""Profile API router.

Endpoints:
  GET    /api/v1/profile/charts              — list saved charts
  PATCH  /api/v1/profile/primary-chart       — set primary chart (pin)
  DELETE /api/v1/profile/charts/{chart_id}   — delete a saved chart
  GET    /api/v1/profile/history             — interpretation history
  GET    /api/v1/profile/subscription        — current subscription info
  DELETE /api/v1/profile/data                — GDPR: delete all user data
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
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
        "primary_chart_id": user.primary_chart_id,
        "charts": [
            {
                "id": c.id,
                "birth_date": c.birth_date,
                "birth_time": c.birth_time,
                "birth_place": c.birth_place,
                "house_system": c.house_system,
                "time_unknown": c.time_unknown,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "is_primary": c.id == user.primary_chart_id,
            }
            for c in charts
        ],
    }


# ═══════════════════════════════════════════════════════════
# PRIMARY CHART
# ═══════════════════════════════════════════════════════════

class SetPrimaryChartRequest(BaseModel):
    chart_id: str


@router.patch(
    "/primary-chart",
    response_model=MessageResponse,
    summary="Set primary chart (pin)",
)
async def set_primary_chart(
    body: SetPrimaryChartRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pin a chart as primary.

    All emails, planner, and natal chart tab will use this chart.
    The chart must belong to the current user.
    """
    chart = (
        db.query(NatalChart)
        .filter(NatalChart.id == body.chart_id, NatalChart.user_id == user.id)
        .first()
    )
    if not chart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chart not found or does not belong to you.",
        )

    user.primary_chart_id = chart.id
    db.commit()
    logger.info("Primary chart set: user=%s chart=%s", user.id, chart.id)
    return MessageResponse(message="Primary chart updated.")


# ═══════════════════════════════════════════════════════════
# DELETE CHART
# ═══════════════════════════════════════════════════════════

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

    # Если удаляется главная карта — сбрасываем pin
    if user.primary_chart_id == chart_id:
        user.primary_chart_id = None

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
    """Return interpretation history entries linked to the user's charts."""
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
                    "preview": (r.content or "")[:200],
                }
                for r in rows
            ],
        }

    except (ImportError, AttributeError):
        return {"total": 0, "offset": offset, "limit": limit, "history": []}


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION INFO
# ═══════════════════════════════════════════════════════════

@router.get(
    "/subscription",
    summary="Current subscription details with limits and usage",
)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current subscription tier, limits, and monthly usage."""
    from datetime import datetime
    from sqlalchemy import func

    tier = user.tier or "free"
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id)
        .first()
    )

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ai_used = 0
    transit_ai_used = 0
    charts_used = 0

    # Интерпретации и AI-транзиты считаем из usage_counters — того же
    # источника, что и лимитер (rate_limits), чтобы цифры на фронте
    # совпадали с реальным лимитом.
    try:
        from backend.auth.rate_limits import get_monthly_usage
        ai_used = get_monthly_usage(db, str(user.id), "interpretation")
        transit_ai_used = get_monthly_usage(db, str(user.id), "transit_ai")
    except Exception:
        # запасной путь: старый способ по таблице Interpretation
        try:
            from backend.models import Interpretation
            ai_used = (
                db.query(func.count(Interpretation.id))
                .join(NatalChart, Interpretation.chart_id == NatalChart.id)
                .filter(
                    NatalChart.user_id == user.id,
                    Interpretation.created_at >= month_start,
                )
                .scalar() or 0
            )
        except (ImportError, AttributeError):
            pass

    charts_used = (
        db.query(func.count(NatalChart.id))
        .filter(
            NatalChart.user_id == user.id,
            NatalChart.created_at >= month_start,
        )
        .scalar() or 0
    )

    from backend.auth.rate_limits import get_tier_limits
    features = get_feature_flags(user)
    limits = get_tier_limits(tier)

    return {
        "tier": tier,
        "is_active": sub.status == "active" if sub else tier != "free",
        "stripe_subscription_id": sub.stripe_subscription_id if sub else None,
        "stripe_customer_id": user.stripe_customer_id,
        "status": sub.status if sub else ("free" if tier == "free" else "active"),
        "current_period_end": (
            sub.current_period_end.isoformat()
            if sub and getattr(sub, "current_period_end", None)
            else None
        ),
        "features": features,
        "limits": limits,
        "usage": {
            "ai_interpretations_this_month": ai_used,
            "transit_ai_this_month": transit_ai_used,
            "charts_this_month": charts_used,
        },
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
    """Permanently delete all charts, interpretations, and subscription data."""
    # Сбрасываем primary_chart_id перед удалением карт (FK constraint)
    user.primary_chart_id = None
    db.flush()

    deleted_charts = (
        db.query(NatalChart)
        .filter(NatalChart.user_id == user.id)
        .delete(synchronize_session=False)
    )

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


# ═══════════════════════════════════════════════════════════
# REFERRAL (задача 1.6)
# ═══════════════════════════════════════════════════════════

@router.get(
    "/referral",
    summary="Get referral link and stats",
)
async def get_referral(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return referral code, share URL, and stats for the current user."""
    from backend.config import get_settings as _get_settings
    settings = _get_settings()

    if not user.referral_code:
        from backend.payments.robokassa_service import _generate_referral_code as generate_referral_code
        try:
            user.referral_code = generate_referral_code(db)
            db.commit()
            db.refresh(user)
        except Exception as e:
            logger.warning("Could not generate referral_code: %s", e)

    referrals_count = db.query(User).filter(
        User.referred_by == user.id,
        User.tier != "free",
    ).count()

    reward_weeks_earned = referrals_count * 2

    base_url = getattr(settings, "frontend_url", "https://astreatime.ru")
    ref_code = user.referral_code or ""
    ref_url = f"{base_url}?ref={ref_code}" if ref_code else ""

    return {
        "ref_code": ref_code,
        "ref_url": ref_url,
        "referrals_count": referrals_count,
        "reward_weeks_earned": reward_weeks_earned,
    }
