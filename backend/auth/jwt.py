"""JWT token management.

Access token  — short-lived (15 min), used for API requests.
Refresh token — longer-lived (7 days), used to obtain new access tokens.

Ротация секрета без даунтайма:
  1. Добавь JWT_SECRET_PREV=<старый секрет> в .env
  2. Смени JWT_SECRET=<новый секрет>
  3. Выкатывай деплой — старые токены ещё работают через jwt_secret_prev
  4. После истечения самого долгого refresh-токена (7д) убери JWT_SECRET_PREV
"""

from __future__ import annotations

import uuid
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
    jti: str = ""
    exp: int = 0  # unix timestamp окончания действия
    iat: int = 0  # unix timestamp выпуска
    token_version: int = 0  # версия сессии — см. User.token_version


class TokenPair(BaseModel):
    """Pair of access + refresh tokens returned to the client."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


# ── Internal helpers ───────────────────────────────────────

def _secrets() -> list[str]:
    """Return [current_secret] or [current, prev] for rotation window."""
    secrets = [settings.jwt_secret]
    if settings.jwt_secret_prev:
        secrets.append(settings.jwt_secret_prev)
    return secrets


def _decode_with_fallback(token: str) -> dict:
    """Try decoding with current secret first, then previous (if set).

    Raises JWTError if all secrets fail.
    """
    last_error: Exception = JWTError("No secrets configured")
    for secret in _secrets():
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError as e:
            last_error = e
    raise last_error


# ── Token creation ─────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    tier: str = "free",
    expires_delta: Optional[timedelta] = None,
    token_version: int = 0,
) -> str:
    """Create a short-lived access token (always signed with current secret)."""
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
        "jti": uuid.uuid4().hex,
        "tv": token_version,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    email: str,
    tier: str = "free",
    expires_delta: Optional[timedelta] = None,
    token_version: int = 0,
) -> str:
    """Create a longer-lived refresh token (always signed with current secret)."""
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
        "jti": uuid.uuid4().hex,
        "tv": token_version,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_token_pair(
    user_id: str, email: str, tier: str = "free", token_version: int = 0
) -> TokenPair:
    """Create both access and refresh tokens."""
    return TokenPair(
        access_token=create_access_token(user_id, email, tier, token_version=token_version),
        refresh_token=create_refresh_token(user_id, email, tier, token_version=token_version),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ── Token verification ─────────────────────────────────────

def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token.

    During a secret rotation window, falls back to jwt_secret_prev
    so tokens issued before the rotation remain valid.

    Raises:
        JWTError: if token is invalid, expired, or malformed by all secrets.
    """
    payload = _decode_with_fallback(token)

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
        jti=payload.get("jti", ""),
        exp=int(payload.get("exp", 0)),
        iat=int(payload.get("iat", 0)),
        token_version=int(payload.get("tv", 0)),
    )


def remaining_ttl(exp: int) -> int:
    """Сколько секунд осталось до истечения токена (>= 1)."""
    now = int(datetime.now(timezone.utc).timestamp())
    return max(exp - now, 1)


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


def create_password_reset_token(user_id: str, email: str) -> str:
    """Create a password reset token (valid 1 hour).

    jti нужен, чтобы погасить ссылку после использования: без него одна и та же
    ссылка из письма работала бы весь час сколько угодно раз.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "password_reset",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_password_reset_token(token: str) -> TokenData:
    """Decode a password reset token."""
    payload = _decode_with_fallback(token)
    if payload.get("type") != "password_reset":
        raise JWTError("Invalid token type for password reset")
    return TokenData(
        user_id=payload["sub"],
        email=payload["email"],
        token_type="password_reset",
        jti=payload.get("jti", ""),
        exp=int(payload.get("exp", 0)),
        iat=int(payload.get("iat", 0)),
    )


def decode_email_confirmation_token(token: str) -> TokenData:
    """Decode an email confirmation token.

    Raises:
        JWTError: if token is invalid or expired.
    """
    payload = _decode_with_fallback(token)
    if payload.get("type") != "email_confirm":
        raise JWTError("Invalid token type for email confirmation")

    return TokenData(
        user_id=payload["sub"],
        email=payload["email"],
        token_type="email_confirm",
    )
