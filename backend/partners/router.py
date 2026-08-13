"""backend/partners/router.py — счётчик переходов и кабинет партнёра.

Endpoints:
  POST /api/v1/partners/track-visit  — публичный, обезличенный клик по ссылке
  GET  /api/v1/partners/dashboard    — агрегаты для залогиненного партнёра

Персональные данные приглашённых наружу не идут ни в каком виде — только
агрегаты (счётчики, суммы). Источник сумм — payment_events через commissions,
не MRR-прикидка из backend/admin/stats_router.py.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models import User, Partner, Commission, PartnerPayout, PartnerVisit, PaymentEvent

router = APIRouter(prefix="/api/v1/partners", tags=["partners"])


# ── Публичный: счётчик переходов ──

class TrackVisitRequest(BaseModel):
    ref_code: str


@router.post("/track-visit", include_in_schema=False)
def track_visit(payload: TrackVisitRequest, db: Session = Depends(get_db)):
    """Всегда отвечает ok — не раскрывает, существует ли ref_code/партнёр
    (защита от перебора), и фронту не нужно обрабатывать ошибку отдельно.
    """
    ref_code = (payload.ref_code or "").strip()
    if ref_code:
        referrer = db.query(User.id).filter(User.referral_code == ref_code).first()
        if referrer:
            partner = db.query(Partner.id).filter(
                Partner.user_id == referrer[0], Partner.status == "active",
            ).first()
            if partner:
                db.add(PartnerVisit(partner_id=partner[0]))
                db.commit()
    return {"ok": True}


# ── Кабинет партнёра ──

def _month_key(dt) -> str:
    return dt.strftime("%Y-%m") if dt else "unknown"


class PartnerTotals(BaseModel):
    visits: int
    registered: int
    paid: int
    by_tier: dict[str, int]
    revenue: float
    commission_earned: float
    paid_out: float
    owed: float
    rate: float


class PartnerMonth(BaseModel):
    month: str
    visits: int
    registered: int
    paid: int
    revenue: float
    commission: float


class PartnerDashboardResponse(BaseModel):
    totals: PartnerTotals
    monthly: list[PartnerMonth]


@router.get("/dashboard", response_model=PartnerDashboardResponse)
def get_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PartnerDashboardResponse:
    partner = db.query(Partner).filter(Partner.user_id == user.id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="not_a_partner")

    visits = db.query(PartnerVisit).filter(PartnerVisit.partner_id == partner.id).all()
    referred_users = db.query(User).filter(User.referred_by == user.id).all()

    # Платежи и комиссии — только через commissions (earned), не все платежи
    # приглашённых: так "их платежи" и "начислено" всегда согласованы между
    # собой и с окном атрибуции (backend/partners/commission.py).
    earned_rows = (
        db.query(Commission, PaymentEvent)
        .join(PaymentEvent, Commission.payment_event_id == PaymentEvent.id)
        .filter(Commission.partner_id == partner.id, Commission.kind == "earned")
        .all()
    )
    all_commissions = db.query(Commission).filter(Commission.partner_id == partner.id).all()
    payouts = db.query(PartnerPayout).filter(PartnerPayout.partner_id == partner.id).all()

    by_tier: dict[str, int] = defaultdict(int)
    paid_user_ids: set[str] = set()
    monthly = defaultdict(lambda: {"visits": 0, "registered": 0, "paid": set(), "revenue": 0.0, "commission": 0.0})

    for v in visits:
        monthly[_month_key(v.created_at)]["visits"] += 1

    for u in referred_users:
        monthly[_month_key(u.created_at)]["registered"] += 1

    for commission, payment in earned_rows:
        by_tier[payment.tier or "unknown"] += 1
        paid_user_ids.add(payment.user_id)
        m = _month_key(payment.created_at)
        monthly[m]["paid"].add(payment.user_id)
        monthly[m]["revenue"] += payment.amount or 0

    for c in all_commissions:
        monthly[_month_key(c.created_at)]["commission"] += c.amount

    commission_earned = sum(c.amount for c in all_commissions)
    paid_out = sum(p.amount for p in payouts)
    revenue_total = sum((payment.amount or 0) for _, payment in earned_rows)

    monthly_list = [
        PartnerMonth(
            month=month,
            visits=data["visits"],
            registered=data["registered"],
            paid=len(data["paid"]),
            revenue=data["revenue"],
            commission=data["commission"],
        )
        for month, data in sorted(monthly.items())
    ]

    return PartnerDashboardResponse(
        totals=PartnerTotals(
            visits=len(visits),
            registered=len(referred_users),
            paid=len(paid_user_ids),
            by_tier=dict(by_tier),
            revenue=revenue_total,
            commission_earned=commission_earned,
            paid_out=paid_out,
            owed=commission_earned - paid_out,
            rate=partner.rate,
        ),
        monthly=monthly_list,
    )
