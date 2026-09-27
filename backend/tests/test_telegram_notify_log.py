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
    monkeypatch.setattr(tg.httpx, "AsyncClient",
                        lambda **kw: _RealClient(transport=httpx.MockTransport(handler), **kw))


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
