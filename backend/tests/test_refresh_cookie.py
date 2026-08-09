"""Регрессия H-3: refresh-токен живёт в HttpOnly-куке, а не в localStorage.

Раньше он уезжал клиенту в теле ответа и оседал в localStorage на 7 дней —
любой XSS или испорченная npm-зависимость в бандле забирали недельный доступ
к аккаунту. HttpOnly недостижим для JS по определению, поэтому проверяем и сам
факт установки куки, и её атрибуты: без HttpOnly/SameSite смысл теряется.
"""

import pytest

from backend.auth.router import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH


def _register(client, email="cookie@example.com"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )


def _cookie_header(resp):
    """Сырой Set-Cookie: TestClient раскладывает куку по объекту и теряет флаги."""
    for name, value in resp.headers.raw:
        if name.decode().lower() == "set-cookie" and REFRESH_COOKIE_NAME in value.decode():
            return value.decode()
    return ""


class TestCookieIsSet:

    def test_register_sets_refresh_cookie(self, client):
        resp = _register(client)
        assert resp.status_code == 201
        assert REFRESH_COOKIE_NAME in resp.cookies

    def test_login_sets_refresh_cookie(self, client, user_free):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": "Password123!"},
        )
        assert resp.status_code == 200
        assert REFRESH_COOKIE_NAME in resp.cookies

    def test_cookie_is_httponly_and_scoped(self, client):
        raw = _cookie_header(_register(client, "flags@example.com")).lower()
        assert "httponly" in raw, "без HttpOnly кука снова читается из JS"
        assert "samesite=strict" in raw
        assert f"path={REFRESH_COOKIE_PATH}".lower() in raw

    def test_body_does_not_leak_refresh(self, client):
        """Токен в теле = токен в localStorage у любого клиента."""
        body = _register(client, "nobody@example.com").json()
        assert body.get("refresh_token") is None
        assert body["access_token"]


class TestRefreshFromCookie:

    def test_refresh_works_with_cookie_only(self, client, user_free):
        client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": "Password123!"},
        )
        # Тело пустое — токен берётся только из куки, которую хранит клиент.
        resp = client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    def test_refresh_without_cookie_is_401(self, client):
        resp = client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 401

    def test_rotation_invalidates_previous_cookie(self, client, user_free):
        """Ротация: использованный refresh должен перестать работать."""
        client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": "Password123!"},
        )
        stale = client.cookies.get(REFRESH_COOKIE_NAME)

        assert client.post("/api/v1/auth/refresh", json={}).status_code == 200

        # Подсовываем старое значение в обход того, что клиент уже перезаписал.
        client.cookies.set(REFRESH_COOKIE_NAME, stale)
        assert client.post("/api/v1/auth/refresh", json={}).status_code == 401


class TestLegacyBodyStillAccepted:
    """Совместимость со сборками фронта, кэшированными в браузерах.

    Без этой ветки в момент деплоя разлогинились бы все, у кого открыта вкладка
    со старым бандлом.
    """

    def test_body_token_accepted_and_echoed(self, client, user_free):
        login = client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": "Password123!"},
        )
        token = login.cookies.get(REFRESH_COOKIE_NAME)
        client.cookies.clear()

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert resp.status_code == 200
        # Старый клиент ждёт токен в теле — иначе он его потеряет.
        assert resp.json()["refresh_token"]


class TestLogoutClearsCookie:

    def test_logout_deletes_cookie(self, client, user_free):
        login = client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": "Password123!"},
        )
        access = login.json()["access_token"]

        resp = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access}"},
            json={},
        )
        assert resp.status_code == 200
        # httpx удаляет куку из своего хранилища, получив Set-Cookie с Max-Age=0.
        assert not client.cookies.get(REFRESH_COOKIE_NAME)

    def test_refresh_after_logout_is_401(self, client, user_free):
        login = client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": "Password123!"},
        )
        access = login.json()["access_token"]
        stale = login.cookies.get(REFRESH_COOKIE_NAME)

        client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access}"},
            json={},
        )
        client.cookies.set(REFRESH_COOKIE_NAME, stale)
        assert client.post("/api/v1/auth/refresh", json={}).status_code == 401
