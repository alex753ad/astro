"""Authentication API router.

Endpoints:
  POST /api/v1/auth/register         — email + password registration
  POST /api/v1/auth/login            — email + password login
  POST /api/v1/auth/refresh           — refresh access token
  POST /api/v1/auth/google            — Google OAuth code exchange
  GET  /api/v1/auth/confirm-email     — email confirmation via token
  GET  /api/v1/auth/me                — current user profile
  DELETE /api/v1/auth/me              — delete account (GDPR)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from jose import JWTError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.schemas import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    GoogleOAuthRequest,
    TokenResponse,
    UserProfileResponse,
    MessageResponse,
)
from backend.auth.jwt import (
    create_token_pair,
    decode_token,
    create_email_confirmation_token,
    decode_email_confirmation_token,
)
from backend.auth.passwords import hash_password, verify_password
from backend.auth.dependencies import get_current_user

logger = logging.getLogger("astro.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ═══════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register with email + password",
)
async def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account.

    Returns JWT token pair immediately.
    Sends email confirmation token (in production — via email service).
    """
    # Check if email already taken
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Create user
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        is_active=True,
        is_email_confirmed=False,
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate email confirmation token
    confirm_token = create_email_confirmation_token(user.id, user.email)
    logger.info(
        "User registered: %s — confirmation token: %s",
        user.email,
        confirm_token[:20] + "...",
    )
    # TODO: Send confirmation email via email service (SendGrid / SES / etc.)

    tokens = create_token_pair(user.id, user.email, user.tier)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=user.id,
        email=user.email,
        tier=user.tier,
    )


# ═══════════════════════════════════════════════════════════
# LOGIN
# ═══════════════════════════════════════════════════════════

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email + password",
)
async def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return JWT token pair."""
    user = db.query(User).filter(User.email == data.email).first()

    if user is None or user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    tokens = create_token_pair(user.id, user.email, user.tier)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=user.id,
        email=user.email,
        tier=user.tier,
    )


# ═══════════════════════════════════════════════════════════
# TOKEN REFRESH
# ═══════════════════════════════════════════════════════════

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new token pair."""
    try:
        token_data = decode_token(data.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    if token_data.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected a refresh token.",
        )

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    tokens = create_token_pair(user.id, user.email, user.tier)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=user.id,
        email=user.email,
        tier=user.tier,
    )


# ═══════════════════════════════════════════════════════════
# GOOGLE OAUTH
# ═══════════════════════════════════════════════════════════

@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Google OAuth login / register",
)
async def google_oauth(data: GoogleOAuthRequest, db: Session = Depends(get_db)):
    """Exchange a Google authorization code for JWT tokens.

    Creates a new account if the email doesn't exist yet.
    """
    from backend.auth.oauth import exchange_google_code, OAuthError

    try:
        google_user = await exchange_google_code(
            code=data.code,
            redirect_uri=data.redirect_uri,
        )
    except OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth failed: {e}",
        )

    # Find or create user
    user = db.query(User).filter(User.email == google_user.email).first()

    if user is None:
        user = User(
            email=google_user.email,
            hashed_password=None,  # OAuth users have no password
            is_active=True,
            is_email_confirmed=google_user.email_verified,
            google_sub=google_user.sub,
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("New OAuth user: %s", user.email)
    else:
        # Link Google sub if not yet linked
        if user.google_sub is None:
            user.google_sub = google_user.sub
            db.commit()

    tokens = create_token_pair(user.id, user.email, user.tier)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=user.id,
        email=user.email,
        tier=user.tier,
    )


# ═══════════════════════════════════════════════════════════
# EMAIL CONFIRMATION
# ═══════════════════════════════════════════════════════════

@router.get(
    "/confirm-email",
    response_model=MessageResponse,
    summary="Confirm email address",
)
async def confirm_email(
    token: str = Query(..., description="Email confirmation token"),
    db: Session = Depends(get_db),
):
    """Confirm a user's email address via token from the confirmation link."""
    try:
        token_data = decode_email_confirmation_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired confirmation token.",
        )

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_email_confirmed = True
    db.commit()

    return MessageResponse(message="Email confirmed successfully.")


# ═══════════════════════════════════════════════════════════
# USER PROFILE
# ═══════════════════════════════════════════════════════════

@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get current user profile",
)
async def get_me(user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        tier=user.tier,
        is_email_confirmed=user.is_email_confirmed,
        stripe_customer_id=user.stripe_customer_id,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.delete(
    "/me",
    response_model=MessageResponse,
    summary="Delete account (GDPR)",
)
async def delete_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the user account and all associated data."""
    # Cascade delete handles charts + interpretations
    db.delete(user)
    db.commit()
    logger.info("User deleted: %s (%s)", user.email, user.id)
    return MessageResponse(message="Account deleted successfully.")
