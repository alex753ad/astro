"""Сбой отправки в Telegram обязан объяснять себя в логе — и не выдавать токен.

27.09.2026 обращение из приложения не дошло до чата поддержки, а в логе было
только «Telegram support notify failed:» с пустотой после двоеточия: у сетевых
исключений httpx str() пустой. Заодно выяснилось, что на ответе 4xx прежняя
строка писала в лог URL запроса вместе с /bot<токен>/.
"""
import logging

import httpx
import pytest

from backend.notifications import telegram as tg

TOKEN = "123456:SECRET-token-value"
_RealClient = httpx.AsyncClient


@pytest.fixture
def telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_SUPPORT_CHAT_ID", "-100123")


def _route(monkeypatch, handler):
    # transport подменяется поверх того, что ставит _client() (IPv6).
    monkeypatch.setattr(tg.httpx, "AsyncClient",
                        lambda **kw: _RealClient(**{**kw, "transport": httpx.MockTransport(handler)}))


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    """Паузы повторов (5 и 30 с) — в список, а не в ожидание."""
    slept = []

    async def fake_sleep(s):
        slept.append(s)
    monkeypatch.setattr(tg.asyncio, "sleep", fake_sleep)
    return slept


async def test_network_error_names_its_type(telegram_env, monkeypatch, caplog):
    def handler(request):
        raise httpx.ConnectTimeout("")
    _route(monkeypatch, handler)
    with caplog.at_level(logging.WARNING, logger="astro.notifications.telegram"):
        assert await tg.send_support_message("x") is False
    assert "ConnectTimeout" in caplog.text


async def test_rejection_logs_reason_without_token(telegram_env, monkeypatch, caplog):
    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})
    _route(monkeypatch, handler)
    with caplog.at_level(logging.WARNING, logger="astro.notifications.telegram"):
        assert await tg.send_support_message("x") is False
    assert "chat not found" in caplog.text
    assert "HTTPStatusError" in caplog.text
    assert TOKEN not in caplog.text and "SECRET" not in caplog.text


async def test_success_returns_true(telegram_env, monkeypatch):
    _route(monkeypatch, lambda request: httpx.Response(200, json={"ok": True}))
    assert await tg.send_support_message("x") is True


# ── IPv6 и повтор при сбое соединения (30.09.2026) ─────────────────────────

def test_client_goes_ipv6_only():
    """IPv4 до Telegram с сервера закрыт — клиент не должен его пробовать."""
    client = tg._client()
    assert client._transport._pool._local_address == "::"


async def test_connect_failure_retried_with_pauses(telegram_env, monkeypatch, no_pauses):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("")
        return httpx.Response(200, json={"ok": True})
    _route(monkeypatch, handler)
    assert await tg.send_support_message("x") is True
    assert len(calls) == 3 and no_pauses == [5, 30]


async def test_gives_up_after_three_connect_timeouts(telegram_env, monkeypatch, no_pauses):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectTimeout("")
    _route(monkeypatch, handler)
    assert await tg.send_support_message("x") is False
    assert len(calls) == 3 and no_pauses == [5, 30]


async def test_read_timeout_not_retried(telegram_env, monkeypatch, no_pauses):
    """Запрос мог уже дойти — повтор дал бы дубль в чате."""
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("")
    _route(monkeypatch, handler)
    assert await tg.send_support_message("x") is False
    assert len(calls) == 1 and no_pauses == []
