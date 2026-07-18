"""Регрессия: сбой аутентификации отличим от «не найдено».

Прод-инцидент: на chart-эндпоинтах протухший access-токен молча превращал
запрос в анонимный, проверка владельца давала 404 «карта не найдена», и клиент
не понимал, что нужно обновить токен. Теперь предъявленные и непринятые
учётные данные дают 401.
"""

from datetime import timedelta

import pytest

from backend.auth.jwt import create_access_token, create_refresh_token


@pytest.fixture
def owned_chart(db, user_free):
    from backend.tests.test_chart_access import _make_chart
    return _make_chart(db, user_id=user_free.id)


def _expired_token(user):
    return create_access_token(
        user_id=user.id, email=user.email, tier=user.tier,
        expires_delta=timedelta(seconds=-30),
    )


class TestExpiredTokenGives401:

    def test_chart_get(self, client, user_free, owned_chart):
        """Ключевой случай инцидента: свой же chart_id и протухший токен."""
        resp = client.get(
            f"/api/v1/chart/{owned_chart.id}",
            headers={"Authorization": f"Bearer {_expired_token(user_free)}"},
        )
        assert resp.status_code == 401

    def test_planner(self, client, user_free, owned_chart):
        resp = client.get(
            f"/api/v1/chart/{owned_chart.id}/planner/monthly",
            headers={"Authorization": f"Bearer {_expired_token(user_free)}"},
        )
        assert resp.status_code == 401

    def test_transits_positions(self, client, user_free, owned_chart):
        resp = client.get(
            f"/api/v1/chart/{owned_chart.id}/transits/positions?on_date=2026-01-01",
            headers={"Authorization": f"Bearer {_expired_token(user_free)}"},
        )
        assert resp.status_code == 401


class TestOtherRejectedCredentialsGive401:

    def test_malformed_token(self, client, owned_chart):
        resp = client.get(
            f"/api/v1/chart/{owned_chart.id}",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401

    def test_refresh_token_used_as_access(self, client, user_free, owned_chart):
        refresh = create_refresh_token(
            user_id=user_free.id, email=user_free.email, tier=user_free.tier
        )
        resp = client.get(
            f"/api/v1/chart/{owned_chart.id}",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert resp.status_code == 401

    def test_token_after_session_revoked(self, client, db, user_free, owned_chart,
                                         auth_headers_free):
        """После logout-all старый токен даёт 401, а не 404."""
        client.post("/api/v1/auth/logout-all", headers=auth_headers_free)
        resp = client.get(f"/api/v1/chart/{owned_chart.id}", headers=auth_headers_free)
        assert resp.status_code == 401

    def test_invalid_sse_ticket(self, client, owned_chart):
        resp = client.get(f"/api/v1/chart/{owned_chart.id}?ticket=bogus-ticket")
        assert resp.status_code == 401


class TestAnonymousStillWorks:
    """None по-прежнему означает «клиент ничего не предъявил»."""

    def test_no_credentials_is_404_not_401(self, client, owned_chart):
        """Без заголовка — по-прежнему 404: существование карты не раскрываем."""
        resp = client.get(f"/api/v1/chart/{owned_chart.id}")
        assert resp.status_code == 404

    def test_public_endpoint_works_anonymously(self, client):
        """Эндпоинты без владельца остаются доступны анониму."""
        resp = client.get("/api/v1/calendar/lunar?year=2026&month=1")
        assert resp.status_code == 200

    def test_valid_token_still_works(self, client, owned_chart, auth_headers_free):
        resp = client.get(f"/api/v1/chart/{owned_chart.id}", headers=auth_headers_free)
        assert resp.status_code == 200
