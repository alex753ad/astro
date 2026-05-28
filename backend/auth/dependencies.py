"""FastAPI authentication dependencies.

Usage in endpoints:

    # Required auth
    @app.get("/protected")
    async def protected(user: User = Depends(get_current_user)):
        ...

    # Optional auth (anonymous allowed)
    @app.get("/public")
    async def public(user: User | None = Depends(get_current_user_optional)):
        ...

    # Tier-gated
    @app.get("/pro-only")
    async def pro_only(user: User = Depends(require_tier("pro", "premium"))):
        ...
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.auth.jwt import decode_token, TokenData
from backend.database import get_db
from backend.models import User

# HTTPBearer extracts "Authorization: Bearer <token>" header
_bearer_scheme = HTTPBearer(auto_error=True)
_bearer_scheme_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode JWT and return the corresponding User.

    Raises 401 if token is missing, invalid, or user is inactive.
    """
    try:
        token_data: TokenData = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected an access token",
        )

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        _bearer_scheme_optional
    ),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the current user if a valid token is provided, else None.

    Does NOT raise on missing / invalid token — useful for endpoints
    that work for both anonymous and authenticated users.
    """
    if credentials is None:
        return None

    try:
        token_data = decode_token(credentials.credentials)
    except JWTError:
        return None

    if token_data.token_type != "access":
        return None

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        return None
    return user


def require_tier(*allowed_tiers: str):
    """Dependency factory that enforces subscription tier.

    Usage:
        @app.get("/pro")
        async def pro_endpoint(user: User = Depends(require_tier("pro", "premium"))):
            ...
    """

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.tier not in allowed_tiers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires one of: {', '.join(allowed_tiers)}. "
                       f"Your current plan: {user.tier}.",
            )
        return user

    return _dependency


def require_paid_tier():
    """Любой платный тариф (lite, pro, premium)."""
    return require_tier("lite", "pro", "premium")
