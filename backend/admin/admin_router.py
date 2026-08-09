from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.limiter import client_ip
from backend.models import AdminAuditLog, User

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
