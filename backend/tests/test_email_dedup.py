"""Дедуп отправки писем: повторный вызов с тем же ключом — одно письмо.

23.09.2026 письмо «Ваши тарифы на Aristea Timeline» (retention day14) пришло
~10 раз в одну минуту: отложенная задача Celery (countdown 14 суток) дольше
visibility timeout Redis-брокера выдавалась воркеру заново каждый час, и все
копии сработали в свой общий ETA. Причина закрыта в celery_app.py
(VISIBILITY_TIMEOUT_SEC), здесь — второй слой: сколько бы копий ни сработало,
письмо уходит одно.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from backend import beat_watchdog, email_service


@pytest.fixture
def sent(monkeypatch):
    """Счётчик реальных обращений к Resend + fakeredis вместо Redis."""
    calls: list[str] = []

    async def fake_post(to, subject, html):
        calls.append(to)
        return True

    monkeypatch.setattr(email_service, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_service, "_post_resend", fake_post)
    with patch.object(beat_watchdog, "_sync_redis", return_value=_Redis()):
        yield calls


class _Redis:
    """SET NX / DELETE — всё, что нужно дедупу. Не fakeredis: локально связка
    fakeredis + redis-py лезет в getaddrinfo и ловится сетевым предохранителем
    (CLAUDE.md, про test_beat_watchdog.py) — тест падал бы от окружения."""

    def __init__(self):
        self.keys: dict[str, str] = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    def delete(self, key):
        self.keys.pop(key, None)


def test_double_call_sends_once(sent):
    asyncio.run(email_service.send_retention_day14("a@example.com", user_id=1))
    asyncio.run(email_service.send_retention_day14("a@example.com", user_id=1))
    assert sent == ["a@example.com"]


def test_simultaneous_copies_send_once(sent):
    """Ровно сценарий 23.09: десять копий в одну секунду."""
    async def burst():
        return await asyncio.gather(*[
            email_service.send_retention_day14("a@example.com", user_id=1)
            for _ in range(10)
        ])

    results = asyncio.run(burst())
    assert sent == ["a@example.com"]
    assert results.count(True) == 1


def test_other_user_and_other_kind_not_blocked(sent):
    asyncio.run(email_service.send_retention_day14("a@example.com", user_id=1))
    asyncio.run(email_service.send_retention_day14("b@example.com", user_id=2))
    asyncio.run(email_service.send_retention_day7("a@example.com", 3, user_id=1))
    assert sent == ["a@example.com", "b@example.com", "a@example.com"]


def test_failed_send_releases_key(sent, monkeypatch):
    """Не ушло — ключ снят, иначе сбой Resend запрещал бы письмо навсегда."""
    async def failing_post(to, subject, html):
        return False

    monkeypatch.setattr(email_service, "_post_resend", failing_post)
    assert asyncio.run(email_service.send_retention_day14("a@example.com", user_id=1)) is False

    async def ok_post(to, subject, html):
        sent.append(to)
        return True

    monkeypatch.setattr(email_service, "_post_resend", ok_post)
    assert asyncio.run(email_service.send_retention_day14("a@example.com", user_id=1)) is True
    assert sent == ["a@example.com"]


def test_redis_down_does_not_send(monkeypatch):
    """Маркетинговое письмо без возможности дедупа не отправляется."""
    calls = []

    async def fake_post(to, subject, html):
        calls.append(to)
        return True

    class Dead:
        def set(self, *a, **k):
            raise ConnectionError("redis down")

    monkeypatch.setattr(email_service, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_service, "_post_resend", fake_post)
    with patch.object(beat_watchdog, "_sync_redis", return_value=Dead()):
        asyncio.run(email_service.send_retention_day14("a@example.com", user_id=1))
    assert calls == []


def test_task_called_twice_sends_once(sent, db, user_free, monkeypatch):
    """Уровень Celery-задачи: tasks.py обязан передавать user_id в письмо."""
    from backend import tasks

    class _NoClose:
        def __init__(self, s):
            self._s = s

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    monkeypatch.setattr(tasks, "SessionLocal", lambda: _NoClose(db))
    tasks.send_retention_day14_task(user_free.id)
    tasks.send_retention_day14_task(user_free.id)
    assert sent == [user_free.email]


def test_visibility_timeout_exceeds_longest_countdown():
    """Причина пачки: visibility timeout короче countdown → петля повторов."""
    import math
    import re
    from pathlib import Path

    from backend import tasks
    from backend.celery_app import VISIBILITY_TIMEOUT_SEC, celery_app

    src = Path(tasks.__file__).read_text(encoding="utf-8")
    countdowns = [
        math.prod(int(n) for n in expr.split("*"))
        for expr in re.findall(r"countdown=([\d\s\*]+)\)", src)
    ]
    # Без этой проверки регулярка, переставшая что-либо находить, сделала бы
    # тест зелёным на пустом списке.
    assert len(countdowns) >= 5, countdowns
    assert VISIBILITY_TIMEOUT_SEC > max(countdowns)
    assert celery_app.conf.broker_transport_options["visibility_timeout"] == VISIBILITY_TIMEOUT_SEC
