from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models import User

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
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DeleteUserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    email = user.email
    db.delete(user)
    db.commit()
    return DeleteUserResponse(message="Пользователь удалён.", user_id=user_id, email=email)
