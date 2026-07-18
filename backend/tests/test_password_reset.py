"""Регрессия: reset-ссылка одноразовая, смена пароля отзывает сессии."""

import pytest

from backend.auth.jwt import create_access_token, create_password_reset_token
from backend.models import User


NEW_PASSWORD = "NewPassword123!"


def _reset(client, token, password=NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": password}
    )


@pytest.fixture
def reset_token(user_free):
    return create_password_reset_token(user_free.id, user_free.email)


class TestResetTokenIsSingleUse:

    def test_first_use_succeeds(self, client, reset_token):
        assert _reset(client, reset_token).status_code == 200

    def test_second_use_rejected(self, client, reset_token):
        """Повторный переход по той же ссылке — 400."""
        assert _reset(client, reset_token).status_code == 200
        second = _reset(client, reset_token, "AnotherPassword123!")
        assert second.status_code == 400

    def test_password_not_changed_by_replay(self, client, db, reset_token, user_free):
        """Повтор не должен молча перезаписать пароль ещё раз."""
        from backend.auth.passwords import verify_password

        _reset(client, reset_token)
        _reset(client, reset_token, "AttackerPassword123!")

        db.refresh(user_free)
        assert verify_password(NEW_PASSWORD, user_free.hashed_password)
        assert not verify_password("AttackerPassword123!", user_free.hashed_password)

    def test_invalid_token_rejected(self, client):
        assert _reset(client, "not-a-token").status_code == 400

    def test_weak_password_does_not_burn_token(self, client, reset_token):
        """Отклонённый слабый пароль не должен гасить ссылку."""
        assert _reset(client, reset_token, "123").status_code == 400
        assert _reset(client, reset_token).status_code == 200


class TestPasswordResetRevokesSessions:

    def test_old_access_token_rejected(self, client, db, user_free, auth_headers_free,
                                       reset_token):
        # До сброса токен работает.
        assert client.get("/api/v1/auth/me", headers=auth_headers_free).status_code == 200

        assert _reset(client, reset_token).status_code == 200

        # После сброса — нет.
        assert client.get("/api/v1/auth/me", headers=auth_headers_free).status_code == 401

    def test_new_token_after_reset_works(self, client, db, user_free, reset_token):
        """Токен, выданный после сброса, действителен."""
        _reset(client, reset_token)
        db.refresh(user_free)

        resp = client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": NEW_PASSWORD},
        )
        assert resp.status_code == 200
        access = resp.json()["access_token"]

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me.status_code == 200

    def test_refresh_token_also_revoked(self, client, db, user_free, reset_token):
        from backend.auth.jwt import create_refresh_token

        refresh = create_refresh_token(
            user_id=user_free.id, email=user_free.email, tier=user_free.tier
        )
        _reset(client, reset_token)

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 401


class TestLogoutAll:

    def test_requires_auth(self, client):
        assert client.post("/api/v1/auth/logout-all").status_code in (401, 403)

    def test_revokes_existing_tokens(self, client, db, user_free, auth_headers_free):
        assert client.post("/api/v1/auth/logout-all", headers=auth_headers_free).status_code == 200
        assert client.get("/api/v1/auth/me", headers=auth_headers_free).status_code == 401

    def test_token_issued_after_logout_all_works(self, client, db, user_free,
                                                 auth_headers_free):
        client.post("/api/v1/auth/logout-all", headers=auth_headers_free)
        db.refresh(user_free)

        fresh = create_access_token(
            user_id=user_free.id, email=user_free.email, tier=user_free.tier,
            token_version=user_free.token_version,
        )
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh}"})
        assert resp.status_code == 200

    def test_other_user_unaffected(self, client, db, user_free, user_pro,
                                   auth_headers_free, auth_headers_pro):
        client.post("/api/v1/auth/logout-all", headers=auth_headers_free)
        assert client.get("/api/v1/auth/me", headers=auth_headers_pro).status_code == 200
