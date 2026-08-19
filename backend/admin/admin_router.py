from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.limiter import client_ip
from backend.models import AdminAuditLog, User, PaymentEvent
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
