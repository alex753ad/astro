# backend/admin/stats_router.py
from datetime import timedelta
from backend.time_utils import utcnow
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import User, NatalChart, Interpretation, Subscription, CouponSent, GiftCode
from backend.admin.admin_router import require_admin
from backend.metrics import (compute_retention, compute_funnel, compute_astrologer_metrics, compute_promo_activation)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    # Users
    total_users = db.query(func.count(User.id)).scalar() or 0
    new_month   = db.query(func.count(User.id)).filter(User.created_at >= month_start).scalar() or 0
    new_week    = db.query(func.count(User.id)).filter(User.created_at >= week_start).scalar() or 0
    google_users = db.query(func.count(User.id)).filter(User.google_sub.isnot(None)).scalar() or 0
    google_pct  = round(google_users / total_users * 100) if total_users else 0

    by_plan = {}
    for tier in ("free", "lite", "pro", "premium"):
        by_plan[tier] = db.query(func.count(User.id)).filter(User.tier == tier).scalar() or 0

    # Activity (all time — charts & interpretations)
    charts_total        = db.query(func.count(NatalChart.id)).scalar() or 0
    interpretations_total = db.query(func.count(Interpretation.id)).scalar() or 0

    # Activity last 30 days
    day30 = now - timedelta(days=30)
    charts_30d          = db.query(func.count(NatalChart.id)).filter(NatalChart.created_at >= day30).scalar() or 0
    interpretations_30d = db.query(func.count(Interpretation.id)).filter(Interpretation.created_at >= day30).scalar() or 0

    # Revenue (simple MRR estimate)
    prices = {"lite": 790, "pro": 1990, "premium": 7990}
    mrr = sum(by_plan.get(t, 0) * p for t, p in prices.items())

    # Funnel
    made_chart = db.query(func.count(func.distinct(NatalChart.user_id))).filter(NatalChart.user_id.isnot(None)).scalar() or 0

    # Gift codes
    gift_total     = db.query(func.count(GiftCode.id)).scalar() or 0
    gift_activated = db.query(func.count(GiftCode.id)).filter(GiftCode.redeemed_by.isnot(None)).scalar() or 0
    gift_pct       = round(gift_activated / gift_total * 100) if gift_total else 0

    # Recent users. Раньше на каждого из 10 юзеров уходило по два отдельных
    # запроса (карты + интерпретации) — 20 лишних SELECT на один рендер admin
    # dashboard. Считаем агрегатами по всем юзерам сразу и подставляем нулями
    # там, где счётчика нет.
    recent = db.query(User).order_by(User.created_at.desc()).limit(10).all()
    recent_ids = [u.id for u in recent]

    charts_by_user = dict(
        db.query(NatalChart.user_id, func.count(NatalChart.id))
        .filter(NatalChart.user_id.in_(recent_ids))
        .group_by(NatalChart.user_id)
        .all()
    ) if recent_ids else {}

    interps_by_user = dict(
        db.query(NatalChart.user_id, func.count(Interpretation.id))
        .join(Interpretation, Interpretation.chart_id == NatalChart.id)
        .filter(NatalChart.user_id.in_(recent_ids))
        .group_by(NatalChart.user_id)
        .all()
    ) if recent_ids else {}

    recent_users = [
        {
            "id": u.id,
            "email": u.email,
            "plan": u.tier,
            "charts": charts_by_user.get(u.id, 0),
            "interpretations": interps_by_user.get(u.id, 0),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in recent
    ]

    retention = compute_retention(db)
    funnel_v2 = compute_funnel(db)
    astro = compute_astrologer_metrics(db)
    promo = compute_promo_activation(db)

    return {
        "users": {
            "total": total_users,
            "new_month": new_month,
            "new_week": new_week,
            "google_pct": google_pct,
            "by_plan": by_plan,
        },
        "activity_30d": {
            "charts": charts_30d,
            "interpretations": interpretations_30d,
            "pdf_reports": 0,
            "rag_sessions": 0,
            "crm_cards": 0,
            "lunar_calendar_views": 0,
            "planner_views": 0,
        },
        "revenue": {
            "mrr": mrr,
            "mrr_growth_pct": 0,
            "arr": mrr * 12,
            "arpu": round(mrr / max(sum(by_plan[t] for t in ("lite","pro","premium")), 1)),
        },
        "funnel": {
            "registered": total_users,
            "made_chart": made_chart,
            "lite": by_plan["lite"],
            "pro": by_plan["pro"],
            "premium": by_plan["premium"],
        },
        "gift_codes": {
            "total": gift_total,
            "activated": gift_activated,
            "activation_pct": gift_pct,
        },
        "recent_users": recent_users,
        "retention": retention,
        "funnel_v2": funnel_v2,
        "astrologer": astro,
        "promo": promo,
        "churn": {"count": 0, "rate_pct": 0},
        "payment_errors": {"total": 0, "items": []},
        "ai_costs": {"gpt4o": 0, "deepseek": 0, "total": 0, "fallback_rate_pct": 0},
        "rate_limits_24h": {"lite": 0, "pro": 0, "premium": 0},
        "email_chains": [],
    }


# GET /api/v1/admin/export НЕ определён здесь: он уже есть в
# backend/admin/promo_router.py, который в main.py регистрируется раньше этого
# роутера. Одноимённый маршрут здесь раньше существовал, но был на практике
# недостижим (FastAPI матчит по порядку регистрации) — при этом OpenAPI
# ругался на Duplicate Operation ID, а сама функция ни разу не выполнялась.
