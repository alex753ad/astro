# backend/admin/promo_router.py
#
# Подключить в main.py:
#   from admin.promo_router import router as promo_router
#   app.include_router(promo_router)
#
# Миграция — добавить в Alembic (015_promo_codes):
#
#   op.create_table("promo_codes",
#     sa.Column("id",               sa.Integer, primary_key=True),
#     sa.Column("code",             sa.String(32), unique=True, nullable=False),
#     sa.Column("discount_type",    sa.String(10), nullable=False),   # "percent" | "amount"
#     sa.Column("discount_value",   sa.Integer, nullable=False),      # % или ₽
#     sa.Column("duration",         sa.String(20), nullable=False),   # "once"|"repeating"|"forever"
#     sa.Column("duration_months",  sa.Integer, nullable=True),
#     sa.Column("applies_to_plans", sa.ARRAY(sa.String), nullable=True),  # null = все тарифы
#     sa.Column("max_redemptions",  sa.Integer, nullable=True),
#     sa.Column("times_redeemed",   sa.Integer, default=0),
#     sa.Column("active",           sa.Boolean, default=True),
#     sa.Column("expires_at",       sa.DateTime, nullable=True),
#     sa.Column("created_at",       sa.DateTime, default=datetime.utcnow),
#   )
#   op.create_table("promo_usages",
#     sa.Column("id",           sa.Integer, primary_key=True),
#     sa.Column("promo_code",   sa.String(32), nullable=False),
#     sa.Column("user_id",      sa.Integer, sa.ForeignKey("users.id"), nullable=False),
#     sa.Column("plan",         sa.String(20), nullable=False),
#     sa.Column("used_at",      sa.DateTime, default=datetime.utcnow),
#   )

import random
import string
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.auth.dependencies import get_current_user
from backend.models import User, GiftCode
from backend.admin.admin_router import require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ── Схемы ──────────────────────────────────────────────────────────────────────

class CreatePromoRequest(BaseModel):
    code: str | None = None              # если пусто — генерируем автоматически
    discount_type: str                   # "percent" | "amount"
    discount_value: int                  # % или ₽
    duration: str                        # "once" | "repeating" | "forever"
    duration_months: int | None = None   # только для repeating
    applies_to_plans: list[str] = []     # [] = все тарифы
    max_redemptions: int | None = None
    expires_at: str | None = None        # ISO date "2026-12-31"


# ── Утилиты ────────────────────────────────────────────────────────────────────

def _gen_code(length=8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ── Создать промокод ────────────────────────────────────────────────────────────

@router.post("/coupons")
def create_promo(req: CreatePromoRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    code = (req.code or _gen_code()).upper().strip()

    existing = db.execute(text("SELECT id FROM promo_codes WHERE code = :c"), {"c": code}).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail=f"Промокод {code} уже существует")

    expires_at = datetime.fromisoformat(req.expires_at) if req.expires_at else None

    db.execute(text("""
        INSERT INTO promo_codes
          (code, discount_type, discount_value, duration, duration_months,
           applies_to_plans, max_redemptions, expires_at, active, times_redeemed, created_at)
        VALUES
          (:code, :dtype, :dval, :dur, :dur_months,
           :plans, :max_red, :expires, true, 0, NOW())
    """), {
        "code":       code,
        "dtype":      req.discount_type,
        "dval":       req.discount_value,
        "dur":        req.duration,
        "dur_months": req.duration_months,
        "plans":      req.applies_to_plans or None,
        "max_red":    req.max_redemptions,
        "expires":    expires_at,
    })
    db.commit()
    return {"code": code, "ok": True}


# ── Список промокодов ───────────────────────────────────────────────────────────

@router.get("/coupons")
def list_promos(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.execute(text("""
        SELECT code, discount_type, discount_value, duration, duration_months,
               applies_to_plans, max_redemptions, times_redeemed, active,
               expires_at, created_at
        FROM promo_codes
        ORDER BY created_at DESC
    """)).fetchall()

    return [
        {
            "code":            r.code,
            "discount_type":   r.discount_type,
            "discount_value":  r.discount_value,
            "discount":        (str(r.discount_value) + "%") if r.discount_type == "percent" else ("₽" + str(r.discount_value)),
            "duration":        r.duration,
            "duration_months": r.duration_months,
            "applies_to_plans": r.applies_to_plans,
            "max_redemptions": r.max_redemptions,
            "times_redeemed":  r.times_redeemed,
            "active":          r.active,
            "expires_at":      r.expires_at.isoformat()[:10] if r.expires_at else None,
            "created_at":      r.created_at.isoformat(),
        }
        for r in rows
    ]


# ── Деактивировать промокод ─────────────────────────────────────────────────────

@router.delete("/coupons/{code}")
def deactivate_promo(code: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db.execute(text("UPDATE promo_codes SET active = false WHERE code = :c"), {"c": code.upper()})
    db.commit()
    return {"ok": True}


# ── Применить промокод (вызывается из payments router при оплате) ───────────────

@router.post("/coupons/apply")
def apply_promo(
    code: str,
    plan: str,
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    Возвращает итоговую цену после скидки.
    Вызывать до создания заказа в Robokassa.
    """
    PLAN_PRICES = {"lite": 790, "pro": 1990, "premium": 7990}
    base_price = PLAN_PRICES.get(plan)
    if not base_price:
        raise HTTPException(400, "Неизвестный тариф")

    row = db.execute(text("""
        SELECT id, discount_type, discount_value, duration, max_redemptions,
               times_redeemed, active, expires_at, applies_to_plans
        FROM promo_codes WHERE code = :c
    """), {"c": code.upper()}).fetchone()

    if not row:
        raise HTTPException(400, "Промокод не найден")
    if not row.active:
        raise HTTPException(400, "Промокод неактивен")
    if row.expires_at and row.expires_at < datetime.utcnow():
        raise HTTPException(400, "Промокод истёк")
    if row.max_redemptions and row.times_redeemed >= row.max_redemptions:
        raise HTTPException(400, "Промокод исчерпан")
    if row.applies_to_plans and plan not in row.applies_to_plans:
        raise HTTPException(400, f"Промокод не действует на тариф {plan}")

    # Проверка: "once" — один раз на пользователя
    if row.duration == "once":
        already = db.execute(text("""
            SELECT id FROM promo_usages WHERE promo_code = :c AND user_id = :u
        """), {"c": code.upper(), "u": user_id}).fetchone()
        if already:
            raise HTTPException(400, "Промокод уже использован")

    if row.discount_type == "percent":
        discount_amount = round(base_price * row.discount_value / 100)
    else:
        discount_amount = min(row.discount_value, base_price)

    final_price = base_price - discount_amount

    return {
        "code":            code.upper(),
        "base_price":      base_price,
        "discount_amount": discount_amount,
        "final_price":     final_price,
        "duration":        row.duration,
        "duration_months": None,  # для UI
    }


def record_promo_usage(code: str, user_id: int, plan: str, db: Session):
    """Вызвать после успешной оплаты Robokassa."""
    db.execute(text("""
        INSERT INTO promo_usages (promo_code, user_id, plan, used_at)
        VALUES (:c, :u, :p, NOW())
    """), {"c": code.upper(), "u": user_id, "p": plan})
    db.execute(text("""
        UPDATE promo_codes SET times_redeemed = times_redeemed + 1 WHERE code = :c
    """), {"c": code.upper()})
    db.commit()


# ── Статистика промокодов и gift-кодов по тарифам ──────────────────────────────

@router.get("/coupons/stats")
def coupon_stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    promos = list_promos(db, _)

    # Применение промокодов по тарифам
    by_plan_rows = db.execute(text("""
        SELECT plan, COUNT(*) FROM promo_usages GROUP BY plan
    """)).fetchall()
    promo_by_plan = {r.plan: r[1] for r in by_plan_rows}

    # Gift-коды по тарифам
    gift_by_plan_rows = (
        db.query(GiftCode.plan, func.count())
        .filter(GiftCode.activated_at.isnot(None))
        .group_by(GiftCode.plan)
        .all()
    )
    gift_by_plan = {plan: count for plan, count in gift_by_plan_rows}

    return {
        "list":          promos,
        "promo_by_plan": promo_by_plan,
        "gift_by_plan":  gift_by_plan,
    }


# ── Экспорт всей аналитики ──────────────────────────────────────────────────────

@router.get("/export")
def export_stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from admin.admin_router import get_admin_stats

    users_rows = db.execute(text("""
        SELECT id, email, subscription_tier, created_at,
               stripe_customer_id, google_sub
        FROM users ORDER BY created_at DESC
    """)).fetchall()

    gift_rows = db.query(GiftCode).all()

    promo_rows = db.execute(text("""
        SELECT p.code, p.discount_type, p.discount_value, p.times_redeemed,
               p.active, p.expires_at, p.created_at,
               COUNT(u.id) as usage_count
        FROM promo_codes p
        LEFT JOIN promo_usages u ON u.promo_code = p.code
        GROUP BY p.id
        ORDER BY p.created_at DESC
    """)).fetchall()

    promo_usage_by_plan = db.execute(text("""
        SELECT promo_code, plan, COUNT(*) FROM promo_usages GROUP BY promo_code, plan
    """)).fetchall()

    payload = {
        "exported_at": datetime.utcnow().isoformat(),
        "users": [
            {
                "id":           r.id,
                "email":        r.email,
                "plan":         r.subscription_tier,
                "created_at":   r.created_at.isoformat(),
                "google_auth":  bool(r.google_sub),
            }
            for r in users_rows
        ],
        "gift_codes": [
            {
                "code":         g.code,
                "plan":         g.plan,
                "activated_at": g.activated_at.isoformat() if g.activated_at else None,
                "created_at":   g.created_at.isoformat(),
            }
            for g in gift_rows
        ],
        "promo_codes": [
            {
                "code":           r.code,
                "discount":       (str(r.discount_value) + "%") if r.discount_type == "percent" else ("₽" + str(r.discount_value)),
                "times_redeemed": r.times_redeemed,
                "active":         r.active,
                "expires_at":     r.expires_at.isoformat()[:10] if r.expires_at else None,
                "created_at":     r.created_at.isoformat(),
            }
            for r in promo_rows
        ],
        "promo_usage_by_plan": [
            {"code": r[0], "plan": r[1], "count": r[2]}
            for r in promo_usage_by_plan
        ],
    }

    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="astrea_stats_{datetime.utcnow().strftime("%Y%m%d")}.json"'
        },
    )
