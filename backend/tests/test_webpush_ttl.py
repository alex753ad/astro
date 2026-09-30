"""TTL веб-пуша: без него pywebpush шлёт TTL=0, и пуш на устройство не на
связи (выключенный iPhone, телефон в Doze) теряется. Тик кладёт утреннему
прогнозу срок до местной полуночи — тест на это в test_push_upcoming.py.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime

import pytest
import pytz

from backend.models import PushSubscription
from backend.push.cron import seconds_to_midnight
from backend.push.sender import DEFAULT_TTL, send_web_push


@pytest.fixture
def webpush_calls(monkeypatch):
    """Подменяет pywebpush целиком: локально его может не быть, в сеть не ходим."""
    calls = []
    fake = types.ModuleType("pywebpush")
    fake.webpush = lambda **kw: calls.append(kw)
    fake.WebPushException = type("WebPushException", (Exception,), {})
    monkeypatch.setitem(sys.modules, "pywebpush", fake)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-key")
    return calls


def _sub():
    return PushSubscription(user_id="u", endpoint="https://web.push.apple.com/x", p256dh="p", auth="a")


def test_default_ttl_is_not_zero(webpush_calls):
    assert send_web_push(_sub(), {"title": "t", "body": "b"}) is True
    assert webpush_calls[0]["ttl"] == DEFAULT_TTL > 0


def test_payload_ttl_is_used_and_not_sent_to_device(webpush_calls):
    send_web_push(_sub(), {"title": "t", "ttl": 3600})
    assert webpush_calls[0]["ttl"] == 3600
    assert "ttl" not in webpush_calls[0]["data"]


class TestSecondsToMidnight:
    tz = pytz.timezone("Europe/Moscow")

    def test_morning(self):
        now = self.tz.localize(datetime(2026, 9, 10, 8, 30))
        assert seconds_to_midnight(now, self.tz) == (15 * 60 + 30) * 60

    def test_never_below_a_minute(self):
        now = self.tz.localize(datetime(2026, 9, 10, 23, 59, 50))
        assert seconds_to_midnight(now, self.tz) == 60

    def test_dst_day_is_not_24h(self):
        # Берлин, 25.10.2026 — сутки в 25 часов: 00:30 → полночь через 24.5 ч.
        tz = pytz.timezone("Europe/Berlin")
        now = tz.localize(datetime(2026, 10, 25, 0, 30))
        assert seconds_to_midnight(now, tz) == int(24.5 * 3600)
