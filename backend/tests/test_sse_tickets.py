"""Регрессия: access-токен не принимается из query; SSE-тикет одноразовый."""

import pytest

from backend.auth.jwt import create_access_token


def _sse_url(chart_id):
    return f"/api/v1/chart/{chart_id}/interpret"


@pytest.fixture
def owned_chart(db, user_free):
    from backend.tests.test_chart_access import _make_chart
    return _make_chart(db, user_id=user_free.id)


class TestJwtNotAcceptedInQuery:

    def test_query_token_does_not_authenticate(self, client, db, user_free, owned_chart):
        """JWT в ?token= больше не аутентифицирует — карта остаётся чужой."""
        token = create_access_token(
            user_id=user_free.id, email=user_free.email, tier=user_free.tier
        )
        resp = client.get(f"/api/v1/chart/{owned_chart.id}?token={token}")
        assert resp.status_code == 404

    def test_header_still_authenticates(self, client, owned_chart, auth_headers_free):
        """Заголовок Authorization продолжает работать."""
        resp = client.get(f"/api/v1/chart/{owned_chart.id}", headers=auth_headers_free)
        assert resp.status_code == 200


class TestSseTicketEndpoint:

    def test_requires_auth(self, client):
        assert client.post("/api/v1/auth/sse-ticket").status_code in (401, 403)

    def test_returns_ticket(self, client, auth_headers_free):
        resp = client.post("/api/v1/auth/sse-ticket", headers=auth_headers_free)
        assert resp.status_code == 200
        assert resp.json()["ticket"]

    def test_tickets_are_unique(self, client, auth_headers_free):
        a = client.post("/api/v1/auth/sse-ticket", headers=auth_headers_free).json()["ticket"]
        b = client.post("/api/v1/auth/sse-ticket", headers=auth_headers_free).json()["ticket"]
        assert a != b


class TestTicketRedemption:

    def _ticket(self, client, headers):
        return client.post("/api/v1/auth/sse-ticket", headers=headers).json()["ticket"]

    def test_valid_ticket_authenticates(self, client, owned_chart, auth_headers_free):
        ticket = self._ticket(client, auth_headers_free)
        resp = client.get(f"{_sse_url(owned_chart.id)}?ticket={ticket}")
        assert resp.status_code == 200

    def test_ticket_is_single_use(self, client, owned_chart, auth_headers_free):
        """Второе подключение с тем же тикетом уже не аутентифицирует.

        Неаутентифицированный запрос к SSE отсекается проверкой лимита тарифа
        (403) раньше, чем проверкой доступа к карте — важно лишь, что это не 200.
        """
        ticket = self._ticket(client, auth_headers_free)
        first = client.get(f"{_sse_url(owned_chart.id)}?ticket={ticket}")
        assert first.status_code == 200

        second = client.get(f"{_sse_url(owned_chart.id)}?ticket={ticket}")
        assert second.status_code != 200

    def test_unknown_ticket_rejected(self, client, owned_chart):
        resp = client.get(f"{_sse_url(owned_chart.id)}?ticket=not-a-real-ticket")
        assert resp.status_code != 200

    @pytest.mark.asyncio
    async def test_expired_ticket_rejected(self, client, owned_chart, auth_headers_free,
                                           fake_redis):
        """По истечении TTL тикет не принимается."""
        from backend.auth import sse_tickets

        ticket = self._ticket(client, auth_headers_free)
        await fake_redis.delete(f"sse:ticket:{ticket}")  # эмулируем истечение TTL

        assert await sse_tickets.redeem(ticket) is None
        resp = client.get(f"{_sse_url(owned_chart.id)}?ticket={ticket}")
        assert resp.status_code != 200
