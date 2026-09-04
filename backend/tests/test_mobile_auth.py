"""Мобильный транспорт refresh-токена: тело ответа вместо HttpOnly-куки.

Webview Capacitor открывает страницу с origin https://localhost и ходит на
боевой домен. Кука astro_refresh стоит с SameSite=Strict, то есть на /refresh и
/logout она не отдаётся — без обходного пути пользователя выбрасывало бы из
приложения примерно через час, когда истечёт access.

Проверяется здесь ровно граница между двумя клиентами: с заголовком
X-Client-Platform: mobile refresh приходит в теле, без него — не приходит и
поведение веба не меняется ни в одном сценарии. Всё остальное (ротация,
reuse-detection, глобальная ревокация) у обоих клиентов общее — это тоже
проверяется, потому что общий код легко разойтись не может, а вот обойти его
новой веткой выдачи — запросто.

Веб-сторона живёт в test_refresh_cookie.py и этим файлом не дублируется.
"""

import pytest

from backend.auth.router import (
    MOBILE_CLIENT_HEADER,
    MOBILE_CLIENT_VALUE,
    REFRESH_COOKIE_NAME,
)

MOBILE = {MOBILE_CLIENT_HEADER: MOBILE_CLIENT_VALUE}
PASSWORD = "Password123!"


def _login(client, user, headers=None):
    return client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
        headers=headers or {},
    )


class TestRefreshInBodyOnlyForMobile:

    def test_login_with_header_returns_refresh_in_body(self, client, user_free):
        resp = _login(client, user_free, MOBILE)
        assert resp.status_code == 200
        assert resp.json()["refresh_token"], "мобильному клиенту неоткуда взять refresh"

    def test_login_without_header_keeps_body_empty(self, client, user_free):
        resp = _login(client, user_free)
        assert resp.status_code == 200
        assert resp.json().get("refresh_token") is None

    def test_cookie_is_still_set_for_mobile(self, client, user_free):
        """Кука ставится обоим: убрать её у мобильного значит рискнуть вебом."""
        resp = _login(client, user_free, MOBILE)
        assert REFRESH_COOKIE_NAME in resp.cookies

    def test_header_value_must_match(self, client, user_free):
        """Произвольное значение заголовка тело не открывает."""
        resp = _login(client, user_free, {MOBILE_CLIENT_HEADER: "web"})
        assert resp.json().get("refresh_token") is None

    def test_register_with_header_returns_refresh_in_body(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "mobile-reg@example.com", "password": PASSWORD},
            headers=MOBILE,
        )
        assert resp.status_code == 201
        assert resp.json()["refresh_token"]


class TestMobileRefreshCycle:
    """Обновление токена без куки — то, ради чего всё затевалось."""

    def test_refresh_by_body_token_returns_next_refresh(self, client, user_free):
        token = _login(client, user_free, MOBILE).json()["refresh_token"]
        client.cookies.clear()  # на устройстве куки нет вовсе

        resp = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}, headers=MOBILE,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"]
        assert body["refresh_token"], "без следующего refresh цепочка обрывается"
        assert body["refresh_token"] != token, "refresh обязан ротироваться"

    def test_chain_survives_two_hops(self, client, user_free):
        """Час жизни приложения — это не одно обновление, а цепочка."""
        token = _login(client, user_free, MOBILE).json()["refresh_token"]
        client.cookies.clear()

        for _ in range(2):
            resp = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": token}, headers=MOBILE,
            )
            assert resp.status_code == 200
            token = resp.json()["refresh_token"]
            client.cookies.clear()

    def test_used_refresh_is_rejected(self, client, user_free):
        """Ротация: повторное использование отозванного токена — 401."""
        token = _login(client, user_free, MOBILE).json()["refresh_token"]
        client.cookies.clear()

        first = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}, headers=MOBILE,
        )
        assert first.status_code == 200
        client.cookies.clear()

        again = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}, headers=MOBILE,
        )
        assert again.status_code == 401


class TestMobileLogoutRevokes:
    """Выход обязан гасить токен на сервере, а не только в памяти устройства."""

    def test_logout_invalidates_mobile_refresh(self, client, user_free):
        login = _login(client, user_free, MOBILE).json()
        access, refresh = login["access_token"], login["refresh_token"]
        client.cookies.clear()

        out = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access}", **MOBILE},
            json={"refresh_token": refresh},
        )
        assert out.status_code == 200
        client.cookies.clear()

        resp = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}, headers=MOBILE,
        )
        assert resp.status_code == 401, "после выхода refresh обязан быть мёртв"


class TestGlobalRevocationCoversMobile:

    def test_logout_all_kills_mobile_refresh(self, client, user_free):
        """token_version гасит мобильную сессию так же, как веб-вкладку."""
        login = _login(client, user_free, MOBILE).json()
        access, refresh = login["access_token"], login["refresh_token"]
        client.cookies.clear()

        killed = client.post(
            "/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {access}"},
        )
        assert killed.status_code == 200
        client.cookies.clear()

        resp = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}, headers=MOBILE,
        )
        assert resp.status_code == 401
