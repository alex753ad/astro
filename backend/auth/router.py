"""Authentication API router.

Endpoints:
  POST /api/v1/auth/register/email/send-code  — шаг 1: отправить OTP на email
  POST /api/v1/auth/register/email/verify     — шаг 2: подтвердить OTP, создать аккаунт
  POST /api/v1/auth/login                     — вход по email + пароль
  POST /api/v1/auth/refresh                   — обновить access token
  POST /api/v1/auth/google                    — Google OAuth
  GET  /api/v1/auth/confirm-email             — подтверждение email по токену (legacy)
  GET  /api/v1/auth/me                        — профиль текущего пользователя
  DELETE /api/v1/auth/me                      — удалить аккаунт
  POST /api/v1/auth/forgot-password           — запросить сброс пароля
  POST /api/v1/auth/reset-password            — сброс пароля по токену
"""

from __future__ import annotations

import json
import logging
import os
import random
import string

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from jose import JWTError
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.auth.jwt import (
    create_email_confirmation_token,
    create_password_reset_token,
    create_token_pair,
    decode_email_confirmation_token,
    decode_password_reset_token,
    decode_token,
)
from backend.auth.oauth import OAuthError, exchange_google_code
from backend.auth.passwords import hash_password, verify_password
from backend.config import get_settings
from backend.database import get_db
from backend.models import User
from backend.schemas import (
    GoogleOAuthRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    SendEmailOTPRequest,
    TokenResponse,
    UserProfileResponse,
    VerifyEmailOTPRequest,
)

ADMIN_EMAILS: set[str] = set(
    e.strip() for e in os.getenv("ADMIN_EMAIL", "").split(",") if e.strip()
)

logger = logging.getLogger("astro.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ═══════════════════════════════════════════════════════════
# OTP — вспомогательные функции
# ═══════════════════════════════════════════════════════════

OTP_TTL = 600        # 10 минут
OTP_RESEND_TTL = 60  # 1 минута между отправками
MAX_OTP_ATTEMPTS = 5

_redis_client: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _redis_client


def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _otp_key(identifier: str) -> str:
    return f"reg_otp:{identifier}"


def _resend_key(identifier: str) -> str:
    return f"reg_otp_resend:{identifier}"


async def _store_otp(
    r: aioredis.Redis,
    identifier: str,
    code: str,
    hashed_pw: str,
    ref_code: str,
) -> None:
    payload = json.dumps({"code": code, "pw": hashed_pw, "ref": ref_code, "attempts": 0})
    await r.setex(_otp_key(identifier), OTP_TTL, payload)
    await r.setex(_resend_key(identifier), OTP_RESEND_TTL, "1")


async def _consume_otp(r: aioredis.Redis, identifier: str, code: str) -> dict:
    """Проверяет OTP: при успехе удаляет из Redis и возвращает данные."""
    raw = await r.get(_otp_key(identifier))
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код устарел. Запросите новый.")

    data = json.loads(raw)

    if data["attempts"] >= MAX_OTP_ATTEMPTS:
        await r.delete(_otp_key(identifier))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Превышено число попыток. Запросите новый код.",
        )

    if data["code"] != code:
        data["attempts"] += 1
        remaining = MAX_OTP_ATTEMPTS - data["attempts"]
        ttl = max(await r.ttl(_otp_key(identifier)), 1)
        await r.setex(_otp_key(identifier), ttl, json.dumps(data))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Неверный код. Осталось попыток: {remaining}.",
        )

    await r.delete(_otp_key(identifier))
    return data


def _build_token_response(user: User, email: str) -> TokenResponse:
    tokens = create_token_pair(user.id, email, user.tier)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=user.id,
        email=email,
        tier=user.tier,
        is_admin=(user.email or "") in ADMIN_EMAILS,
    )


def _create_user(
    db: Session,
    *,
    email: str,
    hashed_pw: str,
    ref_code: str,
) -> User:
    referred_by: str | None = None
    if ref_code:
        referrer = db.query(User).filter(User.referral_code == ref_code).first()
        if referrer:
            referred_by = referrer.id

    user = User(
        email=email,
        hashed_password=hashed_pw,
        is_active=True,
        is_email_confirmed=True,  # подтверждён через OTP
        tier="free",
        referred_by=referred_by,
    )
    db.add(user)
    db.flush()

    try:
        from backend.payments.robokassa_service import _generate_referral_code
        user.referral_code = _generate_referral_code(db)
    except Exception as exc:
        logger.warning("referral_code generation failed: %s", exc)

    db.commit()
    db.refresh(user)
    return user


# ═══════════════════════════════════════════════════════════
# РЕГИСТРАЦИЯ — EMAIL OTP
# ═══════════════════════════════════════════════════════════

@router.post(
    "/register/email/send-code",
    response_model=MessageResponse,
    summary="Регистрация — отправить OTP на email",
)
async def register_email_send(
    data: SendEmailOTPRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с таким email уже существует.")

    r = await _get_redis()
    if await r.exists(_resend_key(data.email)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Подождите минуту перед повторной отправкой.",
        )

    code = _gen_otp()
    await _store_otp(r, data.email, code, hash_password(data.password), data.ref_code or "")

    from backend.email_service import send_otp_email
    await send_otp_email(data.email, code)

    logger.info("Email OTP sent → %s", data.email)
    return MessageResponse(message="Код подтверждения отправлен на почту.")


@router.post(
    "/register/email/verify",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация — подтвердить OTP",
)
async def register_email_verify(
    data: VerifyEmailOTPRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    r = await _get_redis()
    otp_data = await _consume_otp(r, data.email, data.code)

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с таким email уже существует.")

    user = _create_user(
        db,
        email=data.email,
        hashed_pw=otp_data["pw"],
        ref_code=otp_data.get("ref", ""),
    )
    logger.info("New user via email OTP: %s (%s)", data.email, user.id)
    return _build_token_response(user, data.email)


# ═══════════════════════════════════════════════════════════
# ВХОД
# ═══════════════════════════════════════════════════════════

@router.post("/login", response_model=TokenResponse, summary="Вход по email + пароль")
async def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == data.email).first()
    if user is None or user.hashed_password is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль.")
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован.")
    return _build_token_response(user, user.email)


# ═══════════════════════════════════════════════════════════
# REFRESH TOKEN
# ═══════════════════════════════════════════════════════════

@router.post("/refresh", response_model=TokenResponse, summary="Обновить access token")
async def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        token_data = decode_token(data.refresh_token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный refresh token.")

    if token_data.token_type != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ожидается refresh token.")

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден или заблокирован.")

    return _build_token_response(user, user.email or token_data.email)


# ═══════════════════════════════════════════════════════════
# GOOGLE OAUTH
# ═══════════════════════════════════════════════════════════

@router.post("/google", response_model=TokenResponse, summary="Вход через Google")
async def google_oauth(data: GoogleOAuthRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        google_user = await exchange_google_code(code=data.code, redirect_uri=data.redirect_uri)
    except OAuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Google OAuth: {exc}")

    user = db.query(User).filter(User.email == google_user.email).first()
    if user is None:
        user = User(
            email=google_user.email,
            hashed_password=None,
            is_active=True,
            is_email_confirmed=google_user.email_verified,
            google_sub=google_user.sub,
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("New OAuth user: %s", google_user.email)
    elif user.google_sub is None:
        user.google_sub = google_user.sub
        db.commit()

    return _build_token_response(user, user.email)


# ═══════════════════════════════════════════════════════════
# EMAIL CONFIRMATION (legacy — для старых ссылок)
# ═══════════════════════════════════════════════════════════

@router.get("/confirm-email", response_model=MessageResponse, summary="Подтвердить email по токену")
async def confirm_email(
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        token_data = decode_email_confirmation_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недействительная или истёкшая ссылка.")

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден.")

    user.is_email_confirmed = True
    db.commit()
    return MessageResponse(message="Email подтверждён.")


# ═══════════════════════════════════════════════════════════
# ПРОФИЛЬ
# ═══════════════════════════════════════════════════════════

@router.get("/me", response_model=UserProfileResponse, summary="Профиль текущего пользователя")
async def get_me(user: User = Depends(get_current_user)) -> UserProfileResponse:
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        tier=user.tier,
        is_email_confirmed=user.is_email_confirmed,
        stripe_customer_id=user.stripe_customer_id,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.delete("/me", response_model=MessageResponse, summary="Удалить аккаунт")
async def delete_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    db.delete(user)
    db.commit()
    logger.info("User deleted: %s (%s)", user.email, user.id)
    return MessageResponse(message="Аккаунт удалён.")


# ═══════════════════════════════════════════════════════════
# СБРОС ПАРОЛЯ
# ═══════════════════════════════════════════════════════════

from pydantic import BaseModel as _BM


class ForgotPasswordRequest(_BM):
    email: str


class ResetPasswordRequest(_BM):
    token: str
    new_password: str


@router.post("/forgot-password", response_model=MessageResponse, summary="Запросить сброс пароля")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = db.query(User).filter(User.email == data.email).first()
    if user and user.hashed_password:
        token = create_password_reset_token(user.id, user.email)
        reset_url = f"{get_settings().frontend_url}/reset-password?token={token}"
        try:
            from backend.email_service import _send, _base, _h2, _p, _btn
            body = (
                _h2("Сброс пароля")
                + _p("Вы запросили сброс пароля для аккаунта <strong>Astrea Timeline</strong>.")
                + _p("Ссылка действительна <strong>1 час</strong>. Если не запрашивали — проигнорируйте.")
                + _btn("Сбросить пароль →", reset_url)
            )
            await _send(
                data.email,
                "Сброс пароля — Astrea Timeline",
                _base("Сброс пароля", "Ссылка для сброса", body),
            )
        except Exception as exc:
            logger.error("Password reset email failed for %s: %s", data.email, exc)
        logger.info("Password reset requested: %s", data.email)
    return MessageResponse(message="Если аккаунт существует, письмо отправлено.")


@router.post("/reset-password", response_model=MessageResponse, summary="Сбросить пароль")
async def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        token_data = decode_password_reset_token(data.token)
    except JWTError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна или истёкла.")

    if len(data.new_password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пароль минимум 8 символов.")
    if data.new_password.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пароль не может состоять только из цифр.")

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден.")

    user.hashed_password = hash_password(data.new_password)
    db.commit()
    logger.info("Password reset completed: %s", user.email)
    return MessageResponse(message="Пароль успешно изменён.")
