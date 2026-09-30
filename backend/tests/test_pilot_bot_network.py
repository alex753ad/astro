"""Бот (контейнер `bot`) ходит в Telegram по IPv6 и повторяет запрос, если
соединение не установилось. Причина — bot/pilot_bot.py, `_session`.
"""
import asyncio
import importlib
import socket
import sys
from pathlib import Path

import aiohttp
import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe


@pytest.fixture
def pilot_bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST-token")
    # CI запускает pytest из backend/ — пакет `bot` лежит в корне репозитория.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    sys.modules.pop("bot.pilot_bot", None)
    mod = importlib.import_module("bot.pilot_bot")
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    yield mod, sleeps
    sys.modules.pop("bot.pilot_bot", None)


def _net_error(cause):
    e = TelegramNetworkError(method=GetMe(), message="x")
    e.__cause__ = cause
    return e


def _connect_error():
    return aiohttp.ClientConnectorError(None, OSError(101, "Network is unreachable"))


def _run(mod, errors):
    calls = []

    async def make_request(bot, method):
        calls.append(method)
        if errors:
            raise errors.pop(0)
        return "ok"

    mw = mod._RetryOnConnect()
    return asyncio.run(mw(make_request, mod.bot, GetMe())), calls


def test_session_is_ipv6_only(pilot_bot):
    mod, _ = pilot_bot
    assert mod.bot.session._connector_init["family"] == socket.AF_INET6


def test_retries_on_connect_error_then_succeeds(pilot_bot):
    mod, sleeps = pilot_bot
    result, calls = _run(mod, [_net_error(_connect_error()),
                               _net_error(aiohttp.ConnectionTimeoutError())])
    assert result == "ok" and len(calls) == 3 and sleeps == [5, 30]


def test_gives_up_after_last_pause(pilot_bot):
    mod, sleeps = pilot_bot
    with pytest.raises(TelegramNetworkError):
        _run(mod, [_net_error(_connect_error()) for _ in range(3)])
    assert sleeps == [5, 30]


def test_read_timeout_not_retried(pilot_bot):
    # Запрос мог уже дойти — повтор дал бы дубль ответа человеку.
    mod, sleeps = pilot_bot
    with pytest.raises(TelegramNetworkError):
        _run(mod, [_net_error(asyncio.TimeoutError())])
    assert sleeps == []
