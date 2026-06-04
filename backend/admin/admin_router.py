import os
from fastapi import Depends, HTTPException
from backend.auth.dependencies import get_current_user
from backend.models import User

ADMIN_EMAILS = set(
    e.strip() for e in os.getenv("ADMIN_EMAIL", "").split(",") if e.strip()
)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not ADMIN_EMAILS or current_user.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
