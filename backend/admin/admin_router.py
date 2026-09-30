from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.limiter import client_ip
from backend import flags
from backend.auth.emails import find_user_by_email
from backend.models import AdminAuditLog, FeatureFlag, User, PaymentEvent
from backend.partners.commission import refund_commission

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ═══════════════════════════════════════════════════════════
# DEPENDENCY
# ═══════════════════════════════════════════════════════════

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Единственная точка проверки админ-доступа.

    Роль хранится в БД (users.is_admin), проверяется обычным JWT-флоу:
    доступ переживает рестарт, выдаётся и отзывается без передеплоя.

    Раньше здесь было два пути — список email из ADMIN_EMAIL и отдельные
    admin-токены в памяти процесса (dict). Токены терялись при каждом
    рестарте и не разделялись между воркерами, а вход по паролю обходил
    JWT целиком.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ═══════════════════════════════════════════════════════════
# DELETE USER
# ═══════════════════════════════════════════════════════════

class DeleteUserResponse(BaseModel):
    message: str
    user_id: str
    email: str | None


@router.delete("/users/{user_id}", response_model=DeleteUserResponse, summary="Удалить пользователя")
def delete_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DeleteUserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    email = user.email
    # Запись аудита ДО удаления: у AdminAuditLog.admin_id стоит ON DELETE SET NULL,
    # а вот сам факт удаления нужно зафиксировать, пока данные ещё есть.
    # target_user_id — обычная строка без внешнего ключа именно поэтому: запись
    # обязана пережить пользователя, к которому относится.
    db.add(AdminAuditLog(
        admin_id=admin.id,
        admin_email=admin.email,
        action="delete_user",
        target_user_id=user_id,
        details={"email": email, "tier": user.tier},
        ip=client_ip(request),
    ))
    db.delete(user)
    db.commit()
    return DeleteUserResponse(message="Пользователь удалён.", user_id=user_id, email=email)


# ═══════════════════════════════════════════════════════════
# REVENUE-EXCLUDED FLAG
# ═══════════════════════════════════════════════════════════

class UpdateRevenueExcludedRequest(BaseModel):
    revenue_excluded: bool


class UpdateRevenueExcludedResponse(BaseModel):
    user_id: str
    email: str | None
    revenue_excluded: bool


@router.patch(
    "/users/{user_id}/revenue-excluded",
    response_model=UpdateRevenueExcludedResponse,
    summary="Исключить/включить пользователя в расчёт MRR (друзья, тест, промо)",
)
def update_revenue_excluded(
    user_id: str,
    body: UpdateRevenueExcludedRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UpdateRevenueExcludedResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    user.revenue_excluded = body.revenue_excluded
    db.add(AdminAuditLog(
        admin_id=admin.id,
        admin_email=admin.email,
        action="set_revenue_excluded",
        target_user_id=user_id,
        details={"email": user.email, "revenue_excluded": body.revenue_excluded},
        ip=client_ip(request),
    ))
    db.commit()
    return UpdateRevenueExcludedResponse(
        user_id=user.id, email=user.email, revenue_excluded=user.revenue_excluded,
    )


# ═══════════════════════════════════════════════════════════
# ВОЗВРАТ ПЛАТЕЖА — отменяет партнёрскую комиссию
# ═══════════════════════════════════════════════════════════
# Платёжный провайдер не шлёт вебхук на возврат — эндпоинт вызывается вручную,
# когда возврат оформлен (в кабинете провайдера или банком) и это нужно
# отразить в начислениях партнёру.

class RefundPaymentRequest(BaseModel):
    note: str | None = None


class RefundPaymentResponse(BaseModel):
    payment_event_id: int
    adjustment_created: bool
    adjustment_amount: float | None = None


@router.post(
    "/payments/{payment_event_id}/refund",
    response_model=RefundPaymentResponse,
    summary="Отметить платёж возвращённым — отменяет комиссию партнёра",
)
def refund_payment(
    payment_event_id: int,
    body: RefundPaymentRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RefundPaymentResponse:
    payment_event = db.query(PaymentEvent).filter(PaymentEvent.id == payment_event_id).first()
    if not payment_event:
        raise HTTPException(status_code=404, detail="Платёж не найден.")

    adjustment = refund_commission(db, payment_event, note=body.note)

    db.add(AdminAuditLog(
        admin_id=admin.id,
        admin_email=admin.email,
        action="refund_payment_commission",
        target_user_id=payment_event.user_id,
        details={
            "payment_event_id": payment_event_id,
            "inv_id": payment_event.inv_id,
            "adjustment_created": adjustment is not None,
            "note": body.note,
        },
        ip=client_ip(request),
    ))
    db.commit()

    return RefundPaymentResponse(
        payment_event_id=payment_event_id,
        adjustment_created=adjustment is not None,
        adjustment_amount=(adjustment.amount if adjustment else None),
    )


# ═══════════════════════════════════════════════════════════
# ФЛАГИ ФУНКЦИЙ — backend/flags.py, docs/flags.md
# ═══════════════════════════════════════════════════════════
# Список ключей — в коде (flags.FLAGS), здесь только режим. Почты хранятся
# как users.id: смена почты не выключает флаг у человека.

class FlagUpdate(BaseModel):
    mode: str
    emails: list[str] = []


def _flag_view(db: Session, key: str) -> dict:
    row = db.get(FeatureFlag, key)
    ids = list(row.user_ids or []) if row else []
    emails = [u.email for u in db.query(User).filter(User.id.in_(ids)).all()] if ids else []
    return {"key": key, "description": flags.FLAGS[key],
            "mode": row.mode if row else "off", "emails": sorted(emails)}


@router.get("/flags", summary="Флаги функций и их режим")
def list_flags(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return {"items": [_flag_view(db, k) for k in flags.FLAGS]}


@router.put("/flags/{key}", summary="Включить/выключить флаг функции")
def set_flag(
    key: str,
    body: FlagUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if key not in flags.FLAGS:
        raise HTTPException(status_code=404, detail="Нет такого флага.")
    if body.mode not in flags.MODES:
        raise HTTPException(status_code=422, detail="Режим: off, all или users.")
    emails = [e.strip() for e in body.emails if e.strip()]
    users = [(e, find_user_by_email(db, e)) for e in emails]
    missing = [e for e, u in users if u is None]
    if missing:
        raise HTTPException(status_code=422, detail="Нет аккаунтов: " + ", ".join(missing))
    if body.mode == "users" and not users:
        raise HTTPException(status_code=422, detail="Для режима users укажи хотя бы одну почту.")
    row = db.get(FeatureFlag, key) or FeatureFlag(key=key)
    row.mode = body.mode
    row.user_ids = sorted({u.id for _, u in users})
    db.add(row)
    db.add(AdminAuditLog(
        admin_id=admin.id,
        admin_email=admin.email,
        action="set_flag",
        details={"key": key, "mode": body.mode, "emails": emails},
        ip=client_ip(request),
    ))
    db.commit()
    flags.reset_cache()
    return _flag_view(db, key)
