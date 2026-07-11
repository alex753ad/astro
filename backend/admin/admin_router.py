import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models import User

# ── Admin password (hashed at module load) ──────────────────
_ADMIN_PASSWORD_HASH = hashlib.sha256(b"24!28B91Gm").hexdigest()

# ── Simple in-process token store (survives until restart) ──
# { token: True }  — stateless enough for single-instance deploy
_ADMIN_TOKENS: set[str] = set()

ADMIN_EMAILS: set[str] = set(
    e.strip() for e in os.getenv("ADMIN_EMAIL", "").split(",") if e.strip()
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _check_admin_token(token: str) -> bool:
    return token in _ADMIN_TOKENS


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Существующая зависимость — доступ по email из env."""
    if not ADMIN_EMAILS or current_user.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ═══════════════════════════════════════════════════════════
# ADMIN LOGIN BY PASSWORD
# ═══════════════════════════════════════════════════════════

class AdminLoginRequest(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    admin_token: str


@router.post("/login", response_model=AdminLoginResponse, summary="Вход в панель по паролю")
def admin_login(data: AdminLoginRequest) -> AdminLoginResponse:
    candidate_hash = hashlib.sha256(data.password.encode()).hexdigest()
    if not hmac.compare_digest(candidate_hash, _ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный пароль.")
    token = secrets.token_hex(32)
    _ADMIN_TOKENS.add(token)
    return AdminLoginResponse(admin_token=token)


# ═══════════════════════════════════════════════════════════
# DEPENDENCY — admin token OR email
# ═══════════════════════════════════════════════════════════

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request

_bearer = HTTPBearer(auto_error=False)


def require_admin_any(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> str:
    """Разрешает доступ если токен — admin_token ИЛИ JWT пользователя из ADMIN_EMAILS."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    token = credentials.credentials

    # 1. admin password token
    if _check_admin_token(token):
        return "password_admin"

    # 2. JWT admin user
    try:
        from backend.auth.jwt import decode_token
        payload = decode_token(token)
        user = db.query(User).filter(User.id == payload.user_id).first()
        if user and user.email in ADMIN_EMAILS:
            return user.email
    except Exception:
        pass

    raise HTTPException(status_code=403, detail="Admin access required")


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
    _: str = Depends(require_admin_any),
) -> DeleteUserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    email = user.email
    db.delete(user)
    db.commit()
    return DeleteUserResponse(message="Пользователь удалён.", user_id=user_id, email=email)
