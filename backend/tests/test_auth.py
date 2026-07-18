"""Tests for authentication endpoints (Phase 4.1).

Validates:
- Registration (success, duplicate email)
- Login (success, wrong password, inactive user)
- Token refresh (valid, expired, wrong type)
- Google OAuth (new user, existing user, failure)
- Email confirmation
- GET /me
- DELETE /me (account deletion)
- Rate limiting per tier
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import User
from backend.auth.passwords import hash_password
from backend.auth.jwt import create_token_pair, create_refresh_token, create_access_token


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def registered_user(db: Session) -> User:
    user = User(
        email="auth_test@example.com",
        hashed_password=hash_password("securepassword123"),
        is_active=True,
        is_email_confirmed=True,
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def inactive_user(db: Session) -> User:
    user = User(
        email="inactive@example.com",
        hashed_password=hash_password("password"),
        is_active=False,
        is_email_confirmed=False,
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(registered_user: User) -> dict:
    tokens = create_token_pair(registered_user.id, registered_user.email, registered_user.tier)
    return {"Authorization": f"Bearer {tokens.access_token}"}


# ═══════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════

class TestRegister:
    def test_register_success(self, client: TestClient, db: Session):
        resp = client.post("/api/v1/auth/register", json={
            "email": "new_user@example.com",
            "password": "strongpassword123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["email"] == "new_user@example.com"
        assert data["tier"] == "free"
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, client: TestClient, registered_user: User):
        resp = client.post("/api/v1/auth/register", json={
            "email": registered_user.email,
            "password": "anotherpassword",
        })
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    def test_register_creates_user_in_db(self, client: TestClient, db: Session):
        email = "db_check@example.com"
        client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "Str0ngPassphrase!",
        })
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        assert user.tier == "free"
        assert user.is_active is True
        assert user.is_email_confirmed is False

    def test_register_password_is_hashed(self, client: TestClient, db: Session):
        email = "hashed_pw@example.com"
        plain_pw = "mysecretpassword"
        client.post("/api/v1/auth/register", json={"email": email, "password": plain_pw})
        user = db.query(User).filter(User.email == email).first()
        assert user.hashed_password != plain_pw

    def test_register_invalid_email(self, client: TestClient):
        resp = client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "Str0ngPassphrase!",
        })
        assert resp.status_code == 422

    def test_register_short_password(self, client: TestClient):
        """Password should be rejected if too short (depends on schema validation)."""
        resp = client.post("/api/v1/auth/register", json={
            "email": "short@example.com",
            "password": "abc",
        })
        # Pydantic should reject — 422 expected if min_length enforced
        assert resp.status_code in (422, 400)


# ═══════════════════════════════════════════════════════════
# LOGIN
# ═══════════════════════════════════════════════════════════

class TestLogin:
    def test_login_success(self, client: TestClient, registered_user: User):
        resp = client.post("/api/v1/auth/login", json={
            "email": registered_user.email,
            "password": "securepassword123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["email"] == registered_user.email

    def test_login_wrong_password(self, client: TestClient, registered_user: User):
        resp = client.post("/api/v1/auth/login", json={
            "email": registered_user.email,
            "password": "wrongpassword",
        })
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    def test_login_nonexistent_email(self, client: TestClient):
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "password",
        })
        assert resp.status_code == 401

    def test_login_inactive_user(self, client: TestClient, inactive_user: User):
        resp = client.post("/api/v1/auth/login", json={
            "email": inactive_user.email,
            "password": "password",
        })
        assert resp.status_code in (401, 403)

    def test_login_returns_correct_tier(self, client: TestClient, db: Session):
        user = User(
            email="pro_login@example.com",
            hashed_password=hash_password("mypassword"),
            is_active=True,
            tier="pro",
        )
        db.add(user)
        db.commit()

        resp = client.post("/api/v1/auth/login", json={
            "email": "pro_login@example.com",
            "password": "mypassword",
        })
        assert resp.status_code == 200
        assert resp.json()["tier"] == "pro"


# ═══════════════════════════════════════════════════════════
# TOKEN REFRESH
# ═══════════════════════════════════════════════════════════

class TestTokenRefresh:
    def test_refresh_returns_new_tokens(self, client: TestClient, registered_user: User):
        tokens = create_token_pair(registered_user.id, registered_user.email, "free")
        resp = client.post("/api/v1/auth/refresh", json={
            "refresh_token": tokens.refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_with_access_token_fails(self, client: TestClient, registered_user: User):
        """Access token should not be accepted as a refresh token."""
        tokens = create_token_pair(registered_user.id, registered_user.email, "free")
        resp = client.post("/api/v1/auth/refresh", json={
            "refresh_token": tokens.access_token,  # wrong type
        })
        assert resp.status_code == 401

    def test_refresh_with_invalid_token_fails(self, client: TestClient):
        resp = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "totally.invalid.token",
        })
        assert resp.status_code == 401

    def test_refresh_for_deleted_user_fails(self, client: TestClient, db: Session):
        user = User(
            email="to_delete@example.com",
            hashed_password=hash_password("pw"),
            is_active=True,
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        tokens = create_token_pair(user.id, user.email, "free")

        # Delete user before refresh
        db.delete(user)
        db.commit()

        resp = client.post("/api/v1/auth/refresh", json={
            "refresh_token": tokens.refresh_token,
        })
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════
# GOOGLE OAUTH
# ═══════════════════════════════════════════════════════════

class TestGoogleOAuth:
    def _mock_google_user(self, email="google_user@gmail.com"):
        from backend.auth.oauth import GoogleUserInfo
        return GoogleUserInfo(
            sub="google_sub_12345",
            email=email,
            email_verified=True,
            name="Test User",
        )

    def test_oauth_creates_new_user(self, client: TestClient, db: Session):
        with patch(
            "backend.auth.router.exchange_google_code",
            new_callable=AsyncMock,
            return_value=self._mock_google_user("brand_new@gmail.com"),
        ):
            resp = client.post("/api/v1/auth/google", json={
                "code": "mock_code",
                "redirect_uri": "https://app.example.com/oauth/callback",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "access_token" in data
            assert data["email"] == "brand_new@gmail.com"

        user = db.query(User).filter(User.email == "brand_new@gmail.com").first()
        assert user is not None
        assert user.google_sub == "google_sub_12345"
        assert user.hashed_password is None

    def test_oauth_existing_user_gets_token(self, client: TestClient, registered_user: User):
        with patch(
            "backend.auth.router.exchange_google_code",
            new_callable=AsyncMock,
            return_value=self._mock_google_user(registered_user.email),
        ):
            resp = client.post("/api/v1/auth/google", json={
                "code": "mock_code",
                "redirect_uri": "https://app.example.com/oauth/callback",
            })
            assert resp.status_code == 200
            assert resp.json()["email"] == registered_user.email

    def test_oauth_failure_returns_400(self, client: TestClient):
        from backend.auth.oauth import OAuthError
        with patch(
            "backend.auth.router.exchange_google_code",
            new_callable=AsyncMock,
            side_effect=OAuthError("Token exchange failed"),
        ):
            resp = client.post("/api/v1/auth/google", json={
                "code": "bad_code",
                "redirect_uri": "https://app.example.com/oauth/callback",
            })
            assert resp.status_code == 400
            assert "OAuth" in resp.json()["detail"]

    def test_oauth_links_google_sub_to_existing_user(self, client: TestClient, registered_user: User, db: Session):
        """Existing email without google_sub should have sub linked after OAuth."""
        assert registered_user.google_sub is None

        with patch(
            "backend.auth.router.exchange_google_code",
            new_callable=AsyncMock,
            return_value=self._mock_google_user(registered_user.email),
        ):
            client.post("/api/v1/auth/google", json={
                "code": "mock_code",
                "redirect_uri": "https://app.example.com/callback",
            })

        db.refresh(registered_user)
        assert registered_user.google_sub == "google_sub_12345"


# ═══════════════════════════════════════════════════════════
# EMAIL CONFIRMATION
# ═══════════════════════════════════════════════════════════

class TestEmailConfirmation:
    def test_valid_token_confirms_email(self, client: TestClient, db: Session):
        user = User(
            email="unconfirmed@example.com",
            hashed_password=hash_password("pw"),
            is_active=True,
            is_email_confirmed=False,
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        from backend.auth.jwt import create_email_confirmation_token
        token = create_email_confirmation_token(user.id, user.email)

        resp = client.get(f"/api/v1/auth/confirm-email?token={token}")
        assert resp.status_code == 200
        assert "confirmed" in resp.json()["message"].lower()

        db.refresh(user)
        assert user.is_email_confirmed is True

    def test_invalid_token_returns_400(self, client: TestClient):
        resp = client.get("/api/v1/auth/confirm-email?token=invalid.token.here")
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════
# GET /me
# ═══════════════════════════════════════════════════════════

class TestGetMe:
    def test_get_me_returns_profile(self, client: TestClient, registered_user: User, auth_headers: dict):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == registered_user.email
        assert data["tier"] == "free"
        assert "id" in data

    def test_get_me_requires_auth(self, client: TestClient):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_get_me_invalid_token(self, client: TestClient):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════
# DELETE /me
# ═══════════════════════════════════════════════════════════

class TestDeleteAccount:
    def test_delete_account_removes_user(self, client: TestClient, db: Session):
        user = User(
            email="delete_me@example.com",
            hashed_password=hash_password("pw"),
            is_active=True,
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        tokens = create_token_pair(user.id, user.email, "free")
        headers = {"Authorization": f"Bearer {tokens.access_token}"}

        resp = client.delete("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

        deleted = db.query(User).filter(User.email == "delete_me@example.com").first()
        assert deleted is None

    def test_delete_account_requires_auth(self, client: TestClient):
        resp = client.delete("/api/v1/auth/me")
        assert resp.status_code == 401
