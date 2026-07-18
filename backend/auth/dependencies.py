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

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.auth.jwt import decode_token, TokenData
from backend.auth.sse_tickets import redeem as redeem_sse_ticket
from backend.auth.token_store import is_denied
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

    if await is_denied(token_data.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
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
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        _bearer_scheme_optional
    ),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the current user if a valid token is provided, else None.

    Does NOT raise on missing / invalid token — useful for endpoints
    that work for both anonymous and authenticated users.

    Токен берётся только из заголовка Authorization. Для SSE/EventSource,
    который не умеет слать заголовки, предусмотрен одноразовый `?ticket=`
    (см. backend/auth/sse_tickets.py) — сам access-токен в query не принимается.
    """
    token: Optional[str] = None
    if credentials is not None:
        token = credentials.credentials

    if not token:
        ticket = request.query_params.get("ticket")
        if ticket:
            user_id = await redeem_sse_ticket(ticket)
            if user_id is None:
                return None
            user = db.query(User).filter(User.id == user_id).first()
            if user is None or not user.is_active:
                return None
            return user
        return None

    try:
        token_data = decode_token(token)
    except JWTError:
        return None

    if token_data.token_type != "access":
        return None

    if await is_denied(token_data.jti):
        return None

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        return None
    return user


TIER_HIERARCHY = ["free", "lite", "pro", "premium"]


def require_tier(*allowed_tiers: str):
    """Dependency factory that enforces subscription tier.

    Usage:
        @app.get("/pro")
        async def pro_endpoint(user: User = Depends(require_tier("pro", "premium"))):
            ...

    Also supports hierarchical check with a single tier:
        require_tier("pro")  →  allows pro and premium
    """

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        user_tier = user.tier or "free"

        # Hierarchical: if single tier passed, allow that tier and above
        if len(allowed_tiers) == 1:
            required_index = TIER_HIERARCHY.index(allowed_tiers[0])
            user_index = TIER_HIERARCHY.index(user_tier) if user_tier in TIER_HIERARCHY else 0
            if user_index < required_index:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "tier_required",
                        "required": allowed_tiers[0],
                        "current": user_tier,
                    },
                )
        else:
            if user_tier not in allowed_tiers:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "tier_required",
                        "required": allowed_tiers[0],
                        "current": user_tier,
                    },
                )
        return user

    return _dependency


def require_paid_tier():
    """Любой платный тариф (lite, pro, premium)."""
    return require_tier("lite")


# Алиас для совместимости с задачей 7
get_optional_user = get_current_user_optional
