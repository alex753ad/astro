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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.admin.admin_router import require_admin
from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.limiter import client_ip
from backend.models import User, Partner, Commission, PartnerPayout, PartnerVisit, PaymentEvent, AdminAuditLog
from backend.time_utils import utcnow

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


def compute_partner_dashboard(db: Session, partner: Partner) -> PartnerDashboardResponse:
    """Общая агрегация для собственного кабинета партнёра (/dashboard) и
    админского списка партнёров (backend/admin: та же арифметика — иначе
    цифры у партнёра и у админа могли бы разойтись при разговоре с ним).
    """
    visits = db.query(PartnerVisit).filter(PartnerVisit.partner_id == partner.id).all()
    referred_users = db.query(User).filter(User.referred_by == partner.user_id).all()

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


@router.get("/dashboard", response_model=PartnerDashboardResponse)
def get_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PartnerDashboardResponse:
    partner = db.query(Partner).filter(Partner.user_id == user.id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="not_a_partner")
    return compute_partner_dashboard(db, partner)


# ═══════════════════════════════════════════════════════════
# АДМИН: список партнёров, создание, ставка/статус, выплаты
# ═══════════════════════════════════════════════════════════
# Отдельный роутер — другой префикс (/api/v1/admin/partners), тот же файл:
# партнёрский домен держим вместе, а не размазываем по backend/admin/.
# Цифры по каждому партнёру — та же compute_partner_dashboard(), что видит
# сам партнёр в своём кабинете: не должны расходиться при разговоре с ним.

admin_router = APIRouter(prefix="/api/v1/admin/partners", tags=["admin", "partners"])


class AdminPartnerSummary(BaseModel):
    id: str
    user_id: str
    email: str
    rate: float
    status: str
    started_at: str
    payout_details: str | None = None
    note: str | None = None
    totals: PartnerTotals


class AdminPartnerListResponse(BaseModel):
    partners: list[AdminPartnerSummary]


def _to_admin_summary(db: Session, partner: Partner, user: User) -> AdminPartnerSummary:
    dashboard = compute_partner_dashboard(db, partner)
    return AdminPartnerSummary(
        id=partner.id, user_id=partner.user_id, email=user.email,
        rate=partner.rate, status=partner.status,
        started_at=partner.started_at.isoformat() if partner.started_at else "",
        payout_details=partner.payout_details, note=partner.note,
        totals=dashboard.totals,
    )


@admin_router.get("", response_model=AdminPartnerListResponse)
def list_partners(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminPartnerListResponse:
    rows = (
        db.query(Partner, User)
        .join(User, Partner.user_id == User.id)
        .order_by(Partner.created_at.desc())
        .all()
    )
    return AdminPartnerListResponse(
        partners=[_to_admin_summary(db, partner, user) for partner, user in rows]
    )


class CreatePartnerRequest(BaseModel):
    email: str
    rate: float = 0.10
    payout_details: str | None = None
    note: str | None = None


@admin_router.post("", response_model=AdminPartnerSummary, status_code=201)
def create_partner(
    body: CreatePartnerRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminPartnerSummary:
    target = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь с таким email не найден.")

    if db.query(Partner.id).filter(Partner.user_id == target.id).first():
        raise HTTPException(status_code=409, detail="Этот пользователь уже партнёр.")

    partner = Partner(
        user_id=target.id, rate=body.rate, started_at=utcnow(), status="active",
        payout_details=body.payout_details, note=body.note,
    )
    db.add(partner)
    db.flush()

    db.add(AdminAuditLog(
        admin_id=admin.id, admin_email=admin.email, action="create_partner",
        target_user_id=target.id,
        details={"partner_id": partner.id, "email": target.email, "rate": body.rate},
        ip=client_ip(request),
    ))
    db.commit()
    db.refresh(partner)
    return _to_admin_summary(db, partner, target)


class UpdatePartnerRequest(BaseModel):
    rate: float | None = None
    status: str | None = None  # active | paused
    payout_details: str | None = None
    note: str | None = None


@admin_router.patch("/{partner_id}", response_model=AdminPartnerSummary)
def update_partner(
    partner_id: str,
    body: UpdatePartnerRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminPartnerSummary:
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден.")
    if body.status is not None and body.status not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="status must be 'active' or 'paused'")

    # Меняем ставку/статус только через это поле, а не текущую из профиля —
    # commissions уже хранят снимок ставки на момент начисления, изменение
    # здесь прошлые записи не трогает.
    changes: dict = {}
    if body.rate is not None and body.rate != partner.rate:
        changes["rate"] = {"was": partner.rate, "now": body.rate}
        partner.rate = body.rate
    if body.status is not None and body.status != partner.status:
        changes["status"] = {"was": partner.status, "now": body.status}
        partner.status = body.status
    if body.payout_details is not None:
        partner.payout_details = body.payout_details
    if body.note is not None:
        partner.note = body.note

    if changes:
        db.add(AdminAuditLog(
            admin_id=admin.id, admin_email=admin.email, action="update_partner",
            target_user_id=partner.user_id,
            details={"partner_id": partner.id, **changes},
            ip=client_ip(request),
        ))
    db.commit()
    db.refresh(partner)
    user = db.query(User).filter(User.id == partner.user_id).first()
    return _to_admin_summary(db, partner, user)


class PartnerPayoutIn(BaseModel):
    amount: float
    note: str | None = None


class PartnerPayoutOut(BaseModel):
    id: int
    amount: float
    paid_at: str
    note: str | None = None


@admin_router.get("/{partner_id}/payouts", response_model=list[PartnerPayoutOut])
def list_payouts(
    partner_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[PartnerPayoutOut]:
    if not db.query(Partner.id).filter(Partner.id == partner_id).first():
        raise HTTPException(status_code=404, detail="Партнёр не найден.")
    payouts = (
        db.query(PartnerPayout)
        .filter(PartnerPayout.partner_id == partner_id)
        .order_by(PartnerPayout.paid_at.desc())
        .all()
    )
    return [
        PartnerPayoutOut(id=p.id, amount=p.amount, paid_at=p.paid_at.isoformat(), note=p.note)
        for p in payouts
    ]


@admin_router.post("/{partner_id}/payouts", response_model=PartnerPayoutOut, status_code=201)
def mark_payout(
    partner_id: str,
    body: PartnerPayoutIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> PartnerPayoutOut:
    """Действие обратимое (выплату можно скорректировать следующей записью
    или руками поправить в БД), подтверждения не требует — как и просили.
    """
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Партнёр не найден.")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма выплаты должна быть положительной.")

    payout = PartnerPayout(
        partner_id=partner.id, admin_id=admin.id, amount=body.amount,
        paid_at=utcnow(), note=body.note,
    )
    db.add(payout)
    db.flush()

    db.add(AdminAuditLog(
        admin_id=admin.id, admin_email=admin.email, action="mark_partner_payout",
        target_user_id=partner.user_id,
        details={"partner_id": partner.id, "amount": body.amount, "note": body.note},
        ip=client_ip(request),
    ))
    db.commit()
    db.refresh(payout)
    return PartnerPayoutOut(id=payout.id, amount=payout.amount, paid_at=payout.paid_at.isoformat(), note=payout.note)
