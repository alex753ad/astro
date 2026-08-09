"""Регрессия №3 (аудит от 09.08): письма пилота не отправлялись вовсе.

`_process` вызывался синхронно из уже запущенного event loop (`pilot_tick` —
async) через `asyncio.get_event_loop().run_until_complete(...)`. Это гарантированный
`RuntimeError: This event loop is already running`, проглоченный соседним
`except Exception`, — а следом код безусловно писал в `push_sent_log`, что письмо
отправлено. Повторной попытки не было никогда.

Проверяем: `_process` — корутина, реально дожидается отправки, и метка `_mark`
ставится только при успехе (иначе транзиентный сбой Resend хоронит уведомление
так же, как хоронил баг с event loop).
"""

from datetime import timedelta

from backend.time_utils import utcnow

import pytest

from backend.models import PushSentLog


@pytest.fixture
def pilot_user(user_free, db):
    user_free.pilot_started_at = utcnow() - timedelta(days=28)  # 2 дня до конца
    db.commit()
    return user_free


class TestFarewellEmailActuallyAwaited:

    async def test_process_is_coroutine_and_completes(self, db, pilot_user, monkeypatch):
        from backend.pilot import cron

        sent = {}

        async def fake_send_pilot_farewell(to, windows, **kwargs):
            sent["to"] = to
            return True

        monkeypatch.setattr(cron, "_upcoming_windows", lambda db, user: [])
        monkeypatch.setattr("backend.email_service.send_pilot_farewell", fake_send_pilot_farewell)
        monkeypatch.setattr("backend.push.sender.send_to_user", lambda *a, **k: 0)

        result = await cron._process(db, pilot_user)

        assert sent.get("to") == pilot_user.email
        assert result.get("farewell") is True

        marked = db.query(PushSentLog).filter(
            PushSentLog.user_id == pilot_user.id, PushSentLog.kind == "farewell",
        ).first()
        assert marked is not None

    async def test_failed_email_does_not_mark_as_sent(self, db, pilot_user, monkeypatch):
        """Раньше именно эта ветка (сбой) хоронила уведомление навсегда."""
        from backend.pilot import cron

        async def fake_send_fail(to, windows, **kwargs):
            return False

        monkeypatch.setattr(cron, "_upcoming_windows", lambda db, user: [])
        monkeypatch.setattr("backend.email_service.send_pilot_farewell", fake_send_fail)
        monkeypatch.setattr("backend.push.sender.send_to_user", lambda *a, **k: 0)

        result = await cron._process(db, pilot_user)

        assert not result.get("farewell")
        marked = db.query(PushSentLog).filter(
            PushSentLog.user_id == pilot_user.id, PushSentLog.kind == "farewell",
        ).first()
        assert marked is None, "сбой отправки не должен блокировать повторную попытку завтра"

    async def test_exception_in_send_does_not_crash_tick(self, db, pilot_user, monkeypatch):
        from backend.pilot import cron

        async def fake_raise(to, windows, **kwargs):
            raise RuntimeError("Resend недоступен")

        monkeypatch.setattr(cron, "_upcoming_windows", lambda db, user: [])
        monkeypatch.setattr("backend.email_service.send_pilot_farewell", fake_raise)
        monkeypatch.setattr("backend.push.sender.send_to_user", lambda *a, **k: 0)

        result = await cron._process(db, pilot_user)
        assert not result.get("farewell")


class TestPilotTickEndpoint:

    def test_tick_processes_pilot_users(self, client, db, pilot_user, monkeypatch):
        import os

        async def fake_send(*a, **k):
            return True

        monkeypatch.setattr("backend.email_service.send_pilot_farewell", fake_send)
        monkeypatch.setattr("backend.push.sender.send_to_user", lambda *a, **k: 0)
        monkeypatch.setattr("backend.pilot.cron._upcoming_windows", lambda db, user: [])
        monkeypatch.setenv("INTERNAL_SECRET", "test-secret")

        resp = client.post(
            "/api/v1/internal/pilot-tick",
            headers={"X-Internal-Secret": "test-secret"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["users"] == 1
        assert body["farewell_sent"] == 1
