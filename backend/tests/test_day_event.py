"""Главное событие дня и лимит пушей (флаг push_day_event).

Правило — docs/notifications.md, «Главное событие дня и лимит пушей».
Без флага тик обязан вести себя как до него: потолок мягких 1/48ч на месте,
в push_sends ничего не пишется (docs/flags.md, п.4).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytz

from backend import flags
from backend.day_event import (
    LUNATION_ADVICE, MOON_ADVICE, NATAL_PLANETS, SLOW, TONE_ADVICE, DayEvent,
    advice, main_event, title,
)
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

    def test_title_names_time_only_when_timed(self, chart):
        for i in range(10):
            ev = main_event(chart, date(2026, 9, 10) + timedelta(days=i), "Europe/Moscow", "08:00", "22:00")
            if ev:
                assert title(ev).startswith(f"{ev.at_local:%H:%M} · ") == ev.timed
                assert "✦" not in title(ev)
                assert advice(ev)


class TestTexts:
    """Тексты согласованы владельцем 01.10.2026: совет до 60 знаков."""

    def test_every_advice_fits_collapsed_shade(self):
        texts = [t for row in MOON_ADVICE.values() for t in row]
        texts += [*TONE_ADVICE.values(), *LUNATION_ADVICE.values()]
        assert len(texts) == 36 + 3 + 2
        assert all(len(t) <= 60 for t in texts), [t for t in texts if len(t) > 60]

    def test_moon_covers_every_natal_point(self):
        assert set(MOON_ADVICE) == set(NATAL_PLANETS) | {"Ascendant", "Midheaven"}

    def test_moon_by_tone_other_planets_general(self):
        ev = DayEvent(key="k", at_local=datetime(2026, 10, 1, 15, 1, tzinfo=timezone.utc),
                      transit="Moon", natal="Moon", aspect="square", score=1, timed=True)
        assert title(ev) == "15:01 · Луна к твоей Луне"
        assert advice(ev) == MOON_ADVICE["Moon"][1]
        mars = DayEvent(**{**ev.__dict__, "transit": "Mars", "aspect": "trine"})
        assert advice(mars) == TONE_ADVICE["harmonious"]
        slow = DayEvent(**{**ev.__dict__, "transit": "Saturn", "natal": "Sun", "timed": False})
        assert title(slow) == "Сатурн к твоему Солнцу"
        nm = DayEvent(**{**ev.__dict__, "transit": "new_moon", "natal": None, "aspect": None})
        assert (title(nm), advice(nm)) == ("15:01 · Новолуние", LUNATION_ADVICE["new_moon"])


class TestFlagOff:
    def test_soft_cap_kept_and_nothing_recorded(self, db, user_free, chart, only_daily, sent):
        _soft_capped_yesterday(db, user_free)
        assert cron._process_user(db, user_free) == 0
        assert sent == []
        assert db.query(PushSend).count() == 0

    def test_pilot_is_not_limited(self, db, user_free, chart, sent):
        assert cron.pilot_push_allowed(db, user_free)


class TestFlagOn:
    def test_morning_every_day_despite_soft_cap(self, db, user_free, chart, only_daily, flag_on, sent):
        _soft_capped_yesterday(db, user_free)
        assert cron._process_user(db, user_free) == 1
        # У тестовой карты в этот день есть главное событие — заголовок его.
        assert " · " in sent[0]["title"] and "✦" not in sent[0]["title"]
        assert len(sent[0]["body"]) <= 60
        assert [r.slot for r in db.query(PushSend).all()] == ["morning"]

    def test_cap_blocks_third_push(self, db, user_free, chart, only_daily, flag_on, sent):
        for slot in ("pilot", "pilot"):
            db.add(PushSend(user_id=user_free.id, local_date=MORNING.date(), slot=slot))
        db.commit()
        assert cron._process_user(db, user_free) == 0
        assert sent == []
        assert db.query(PushSentLog).filter(PushSentLog.kind == "daily").count() == 0

    def test_pilot_keeps_room_for_morning_and_evening(self, db, user_free, chart, flag_on, sent):
        assert not cron.pilot_push_allowed(db, user_free)
        # Тихие часы с 19:00 — вечера нет, одно место свободно.
        user_free.push_quiet_from = "19:00"
        db.commit()
        assert cron.pilot_push_allowed(db, user_free)
        db.add(PushSend(user_id=user_free.id, local_date=MORNING.date(), slot="morning"))
        db.commit()
        assert cron.pilot_push_allowed(db, user_free)
