"""Главное событие дня и лимит пушей (флаг push_day_event).

Правило — docs/notifications.md, «Главное событие дня и лимит пушей».
Без флага тик обязан вести себя как до него: потолок мягких 1/48ч на месте,
в push_sends ничего не пишется (docs/flags.md, п.4).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
import pytz

from backend import flags
from backend.day_event import SLOW, main_event, phrase
from backend.models import FeatureFlag, PushSend, PushSentLog
from backend.push import cron
from backend.push.cron import in_send_window
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура
from backend.time_utils import utcnow

TZ = pytz.timezone("Europe/Moscow")
MORNING = TZ.localize(datetime(2026, 9, 10, 8, 30))


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def flag_on(db, user_free):
    db.add(FeatureFlag(key="push_day_event", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


@pytest.fixture
def only_daily(db, user_free):
    """Только «Прогноз дня»: значимые события сняли бы потолок и без флага."""
    user_free.push_planner = False
    user_free.push_key_transits = False
    user_free.push_moon_phases = False
    db.commit()


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(cron, "send_to_user", lambda db_, uid, payload: out.append(payload) or 1)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz_=None):
            return MORNING.astimezone(tz_) if tz_ else MORNING

    monkeypatch.setattr(cron, "datetime", _Frozen)
    return out


def _soft_capped_yesterday(db, user):
    db.add(PushSentLog(user_id=user.id, kind="daily", ref_key="2026-09-09",
                       sent_at=utcnow() - timedelta(hours=1)))
    db.commit()


class TestMainEvent:
    def test_same_answer_every_call_and_inside_window(self, chart):
        seen = 0
        for i in range(10):
            d = date(2026, 9, 10) + timedelta(days=i)
            a = main_event(chart, d, "Europe/Moscow", "08:00", "22:00")
            assert a == main_event(chart, d, "Europe/Moscow", "08:00", "22:00")
            if a is None:
                continue
            seen += 1
            assert a.at_local.date() == d
            assert in_send_window(a.at_local, "08:00", "22:00") or (a.transit in SLOW and not a.timed)
        assert seen, "за 10 дней у карты должно найтись хоть одно событие"

    def test_phrase_names_time_only_when_timed(self, chart):
        for i in range(10):
            ev = main_event(chart, date(2026, 9, 10) + timedelta(days=i), "Europe/Moscow", "08:00", "22:00")
            if ev:
                text = phrase(ev)
                assert text.startswith("Сегодня")
                assert (f"{ev.at_local:%H:%M}" in text) == ev.timed


class TestFlagOff:
    def test_soft_cap_kept_and_nothing_recorded(self, db, user_free, chart, only_daily, sent):
        _soft_capped_yesterday(db, user_free)
        assert cron._process_user(db, user_free) == 0
        assert sent == []
        assert db.query(PushSend).count() == 0


class TestFlagOn:
    def test_morning_every_day_despite_soft_cap(self, db, user_free, chart, only_daily, flag_on, sent):
        _soft_capped_yesterday(db, user_free)
        assert cron._process_user(db, user_free) == 1
        assert sent[0]["title"] == "✦ Твой день сегодня"
        assert [r.slot for r in db.query(PushSend).all()] == ["morning"]

    def test_cap_blocks_third_push(self, db, user_free, chart, only_daily, flag_on, sent):
        for slot in ("evening", "evening"):  # любые два содержательных
            db.add(PushSend(user_id=user_free.id, local_date=MORNING.date(), slot=slot))
        db.commit()
        assert cron._process_user(db, user_free) == 0
        assert sent == []
        assert db.query(PushSentLog).filter(PushSentLog.kind == "daily").count() == 0
