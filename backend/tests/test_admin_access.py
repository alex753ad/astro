"""Регрессия: админ-доступ определяется ролью в БД, а не окружением."""

import pytest

from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import User


ADMIN_ROUTES = [
    ("get", "/api/v1/admin/stats"),
    ("get", "/api/v1/admin/export"),
    ("get", "/api/v1/admin/coupons"),
    ("delete", "/api/v1/admin/users/some-user-id"),
]


@pytest.fixture
def admin_user(db):
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("Password123!"),
        name="Admin",
        tier="premium",
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token(
        user_id=admin_user.id, email=admin_user.email, tier=admin_user.tier
    )
    return {"Authorization": f"Bearer {token}"}


class TestNonAdminRejected:

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    def test_valid_jwt_without_role_gets_403(self, client, user_free, auth_headers_free,
                                             method, path):
        """Обычный пользователь с валидным JWT не проходит на admin-роуты."""
        resp = getattr(client, method)(path, headers=auth_headers_free)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    def test_anonymous_rejected(self, client, method, path):
        resp = getattr(client, method)(path)
        assert resp.status_code in (401, 403)


class TestAdminAccepted:

    def test_admin_reaches_stats(self, client, admin_headers):
        assert client.get("/api/v1/admin/stats", headers=admin_headers).status_code == 200

    def test_admin_can_delete_user(self, client, db, admin_headers, user_free):
        resp = client.delete(f"/api/v1/admin/users/{user_free.id}", headers=admin_headers)
        assert resp.status_code == 200
        assert db.query(User).filter(User.id == user_free.id).first() is None

    def test_role_change_takes_effect_without_restart(self, client, db, user_free,
                                                      auth_headers_free):
        """Роль читается из БД на каждом запросе — передеплой не нужен."""
        assert client.get("/api/v1/admin/stats", headers=auth_headers_free).status_code == 403

        user_free.is_admin = True
        db.commit()

        assert client.get("/api/v1/admin/stats", headers=auth_headers_free).status_code == 200


class TestPasswordLoginRemoved:

    def test_admin_login_endpoint_gone(self, client):
        """Вход по паролю с токенами в памяти процесса удалён."""
        resp = client.post("/api/v1/admin/login", json={"password": "whatever"})
        assert resp.status_code == 404


class TestIsAdminExposed:

    def test_me_reports_admin_flag(self, client, admin_headers):
        resp = client.get("/api/v1/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    def test_me_reports_false_for_regular_user(self, client, auth_headers_free):
        resp = client.get("/api/v1/auth/me", headers=auth_headers_free)
        assert resp.json()["is_admin"] is False

    def test_login_response_carries_flag(self, client, admin_user):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": admin_user.email, "password": "Password123!"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True
