# backend/admin/stats_router.py
from datetime import timedelta
from backend.time_utils import utcnow
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import User, NatalChart, Interpretation, Subscription, CouponSent, GiftCode
from backend.admin.admin_router import require_admin
from backend.admin.online import count_online
from backend.metrics import (compute_retention, compute_funnel, compute_astrologer_metrics, compute_promo_activation)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
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
    paying_by_plan = {}
    for tier in ("free", "lite", "pro", "premium"):
        by_plan[tier] = db.query(func.count(User.id)).filter(User.tier == tier).scalar() or 0
        paying_by_plan[tier] = db.query(func.count(User.id)).filter(
            User.tier == tier,
            User.pilot_started_at.is_(None),
            User.revenue_excluded.is_(False),
        ).scalar() or 0

    pilot_count = db.query(func.count(User.id)).filter(User.pilot_started_at.isnot(None)).scalar() or 0
    revenue_excluded_count = db.query(func.count(User.id)).filter(User.revenue_excluded.is_(True)).scalar() or 0

    # Activity (all time — charts & interpretations)
    charts_total        = db.query(func.count(NatalChart.id)).scalar() or 0
    interpretations_total = db.query(func.count(Interpretation.id)).scalar() or 0

    # Activity last 30 days
    day30 = now - timedelta(days=30)
    charts_30d          = db.query(func.count(NatalChart.id)).filter(NatalChart.created_at >= day30).scalar() or 0
    interpretations_30d = db.query(func.count(Interpretation.id)).filter(Interpretation.created_at >= day30).scalar() or 0

    # Revenue (simple MRR estimate). Пилотные участники (pilot_started_at) и
    # вручную помеченные (revenue_excluded — друзья/тест/промо) считаются в
    # by_plan (честная картина использования), но не в paying_by_plan/MRR.
    from backend.payments.common import TIER_PRICES_RUB
    mrr = sum(paying_by_plan.get(t, 0) * p for t, p in TIER_PRICES_RUB.items())

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

    # Срок действия подписки. Раньше в этом блоке его не было вовсе — ни в API,
    # ни в интерфейсе: тариф виден (users.tier), а дата окончания лежит в другой
    # таблице и наружу не отдавалась. Отличить «оплачено до 21.09» от «платный
    # тариф без срока, который tasks.expire_subscriptions не понизит никогда»
    # было нечем.
    #
    # На subscriptions.user_id нет уникального индекса (наследство Stripe, где
    # у клиента законно несколько подписок), поэтому строк на пользователя может
    # оказаться больше одной. Берём ту же, что и остальной код: самую позднюю,
    # NULL в конце — как в crm/router.py:427. Одним запросом на всех, не по
    # запросу на юзера: блок выше специально избавлялись от N+1.
    subs_by_user: dict[str, Subscription] = {}
    if recent_ids:
        for sub in (
            db.query(Subscription)
            .filter(Subscription.user_id.in_(recent_ids))
            .order_by(Subscription.current_period_end.desc().nullslast())
            .all()
        ):
            subs_by_user.setdefault(sub.user_id, sub)

    recent_users = []
    for u in recent:
        sub = subs_by_user.get(u.id)
        recent_users.append({
            "id": u.id,
            "email": u.email,
            "plan": u.tier,
            "charts": charts_by_user.get(u.id, 0),
            "interpretations": interps_by_user.get(u.id, 0),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "revenue_excluded": bool(u.revenue_excluded),
            "is_pilot": u.pilot_started_at is not None,
            # None здесь неоднозначен, поэтому отдаём и статус: has_subscription
            # различает «строки нет» и «строка есть, но дата пустая». Фронт по
            # этой паре разводит пять состояний, см. AdminPage.jsx.
            "has_subscription": sub is not None,
            "subscription_status": sub.status if sub else None,
            "subscription_end": (
                sub.current_period_end.isoformat()
                if sub and sub.current_period_end else None
            ),
        })

    retention = compute_retention(db)
    funnel_v2 = compute_funnel(db)
    astro = compute_astrologer_metrics(db)
    promo = compute_promo_activation(db)
    online_count = await count_online()  # None, если Redis недоступен — фронт покажет "—"

    return {
        "online_count": online_count,
        "users": {
            "total": total_users,
            "new_month": new_month,
            "new_week": new_week,
            "google_pct": google_pct,
            "by_plan": by_plan,
            "paying_by_plan": paying_by_plan,
            "pilot_count": pilot_count,
            "revenue_excluded_count": revenue_excluded_count,
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
            "arpu": round(mrr / max(sum(paying_by_plan[t] for t in ("lite","pro","premium")), 1)),
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
