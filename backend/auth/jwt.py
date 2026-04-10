"""JWT token management.

Access token  — short-lived (15 min), used for API requests.
Refresh token — longer-lived (7 days), used to obtain new access tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel

from backend.config import get_settings

settings = get_settings()


# ── Token payload schemas ──────────────────────────────────

class TokenData(BaseModel):
    """Decoded token payload."""
    user_id: str
    email: str
    tier: str = "free"
    token_type: str = "access"  # "access" | "refresh"


class TokenPair(BaseModel):
    """Pair of access + refresh tokens returned to the client."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


# ── Token creation ─────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    tier: str = "free",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a short-lived access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "tier": tier,
        "type": "access",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    email: str,
    tier: str = "free",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a longer-lived refresh token."""
    if expires_delta is None:
        expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "tier": tier,
        "type": "refresh",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_token_pair(user_id: str, email: str, tier: str = "free") -> TokenPair:
    """Create both access and refresh tokens."""
    return TokenPair(
        access_token=create_access_token(user_id, email, tier),
        refresh_token=create_refresh_token(user_id, email, tier),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ── Token verification ─────────────────────────────────────

def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token.

    Raises:
        JWTError: if token is invalid, expired, or malformed.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    user_id = payload.get("sub")
    email = payload.get("email")
    token_type = payload.get("type", "access")
    tier = payload.get("tier", "free")

    if user_id is None or email is None:
        raise JWTError("Token payload missing required fields")

    return TokenData(
        user_id=user_id,
        email=email,
        tier=tier,
        token_type=token_type,
    )


# ── Email confirmation token ───────────────────────────────

def create_email_confirmation_token(user_id: str, email: str) -> str:
    """Create a token for email verification (valid 24 hours)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "email_confirm",
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_email_confirmation_token(token: str) -> TokenData:
    """Decode an email confirmation token.

    Raises:
        JWTError: if token is invalid or expired.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "email_confirm":
        raise JWTError("Invalid token type for email confirmation")

    return TokenData(
        user_id=payload["sub"],
        email=payload["email"],
        token_type="email_confirm",
    )
