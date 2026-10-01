"""«Неделя вперёд» (флаг week_ahead, backend/week_ahead.py).

Отбор — чистая функция pick_week; пуш и карточка проверяются с подменённым
week_events, чтобы тест не зависел от эфемерид конкретной недели.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
import pytz

from backend import day_event as de
from backend import flags
from backend import week_ahead as wa
from backend.models import DeviceToken, FeatureFlag, PushSentLog
from backend.push import cron
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура
from backend.time_utils import utcnow

TZ = pytz.timezone("Europe/Moscow")
SUNDAY = date(2026, 10, 4)


def _ev(day, transit="Saturn", natal="Moon", aspect="opposition", score=37.5, hh=16):
    at = TZ.localize(datetime(2026, 10, day, hh, 49))
    return de.DayEvent(key=f"{transit}:{natal}:{day}", at_local=at, transit=transit,
                       natal=natal, aspect=aspect, score=score, timed=True)


WEEK = [_ev(7), _ev(8, "Mercury", "Sun", "square", 15.0, 12),
        _ev(10, "new_moon", None, None, 12, 18)]


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def flag_on(db, user_free):
    db.add(FeatureFlag(key="week_ahead", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


@pytest.fixture
def device(db, user_free):
    db.add(DeviceToken(user_id=user_free.id, token="t", platform="android"))
    user_free.created_at = utcnow() - timedelta(days=30)
    db.commit()


@pytest.fixture
def week(monkeypatch):
    box = {"events": WEEK}
    monkeypatch.setattr(de, "week_events", lambda *a, **k: box["events"])
    return box


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(cron, "send_to_user", lambda db_, uid, payload: out.append(payload) or 1)
    return out


def _evening(d=SUNDAY):
    return TZ.localize(datetime(d.year, d.month, d.day, 20, 30))


class TestPick:
    def test_strong_first_then_by_date(self):
        moon = [_ev(5, "Moon", "Sun", "conjunction", 9), _ev(6, "Moon", "Midheaven", "opposition", 7.5)]
        got = de.pick_week(moon + WEEK)
        assert [e.at_local.day for e in got] == [7, 8, 10]

    def test_fill_one_moon_at_most(self):
        evs = [_ev(7), _ev(5, "Moon", "Sun", "conjunction", 9), _ev(6, "Moon", "Moon", "square", 7.5),
               _ev(9, "Venus", "Mercury", "trine", 8)]
        got = de.pick_week(evs)
        assert [(e.transit, e.at_local.day) for e in got] == [("Moon", 5), ("Saturn", 7), ("Venus", 9)]

    def test_below_fill_dropped(self):
        assert de.pick_week([_ev(5, "Moon", "Venus", "trine", 4)]) == []

    def test_top_matches_week_top(self):
        evs = [_ev(7, score=15.0), _ev(9, score=15.0)]
        assert min(de.pick_week(evs), key=lambda e: (-e.score, e.at_local)).at_local.day == 7


class TestTexts:
    def test_variant_a(self):
        assert wa.push_texts(WEEK) == (
            "Неделя вперёд: 7, 8 и 10 октября",
            "Сатурн к твоей Луне, Меркурий к твоему Солнцу, новолуние.",
        )

    def test_one_and_month_border(self):
        assert wa.push_texts([WEEK[0]])[1] == "Сатурн к твоей Луне — главное на неделе."
        assert wa.dates_text([date(2026, 9, 30), date(2026, 10, 2)]) == "30 сентября и 2 октября"
        assert wa.range_text(date(2026, 10, 5)) == "5–11 октября"
        assert wa.range_text(date(2026, 9, 28)) == "28 сентября – 4 октября"


class TestEvening:
    def test_replaces_tomorrow(self, db, user_free, chart, flag_on, device, week, sent):
        assert cron._send_evening(db, user_free, chart, _evening()) == 1
        assert sent[0]["title"] == "Неделя вперёд: 7, 8 и 10 октября"
        assert sent[0]["target"] == "feed_today"
        kinds = {(r.kind, r.ref_key) for r in db.query(PushSentLog).all()}
        assert {("week_ahead", "2026-10-05"), ("tomorrow", "2026-10-05")} <= kinds
        assert cron._send_evening(db, user_free, chart, _evening()) == 0

    def test_calm_week_keeps_tomorrow(self, db, user_free, chart, flag_on, device, week, sent):
        week["events"] = [_ev(5, "Moon", "Sun", "conjunction", 9)]
        cron._send_evening(db, user_free, chart, _evening())
        assert sent[0]["title"] == "Прогноз на завтра"

    def test_not_sunday(self, db, user_free, chart, flag_on, device, week, sent):
        cron._send_evening(db, user_free, chart, _evening(SUNDAY - timedelta(days=1)))
        assert sent[0]["title"] == "Прогноз на завтра"

    def test_web_only_and_flag_off(self, db, user_free, chart, week, sent):
        cron._send_evening(db, user_free, chart, _evening())
        assert sent[0]["title"] == "Прогноз на завтра"

    def test_no_device(self, db, user_free, chart, flag_on, week, sent):
        cron._send_evening(db, user_free, chart, _evening())
        assert sent[0]["title"] == "Прогноз на завтра"

    def test_first_week_wins(self, db, user_free, chart, flag_on, device, week, sent, monkeypatch):
        db.add(FeatureFlag(key="first_week", mode="users", user_ids=[user_free.id]))
        db.commit()
        flags.reset_cache()
        monkeypatch.setattr("backend.first_week.day_number", lambda *a: 3)
        assert wa.evening_candidate(db, user_free, chart, SUNDAY) is None


class TestCard:
    def test_shown_sunday_evening_and_monday(self, db, user_free, chart, device, week):
        late = wa.card(db, user_free, chart, _evening())
        assert late["range"] == "5–11 октября" and late["calm"] is False
        assert late["events"][0]["when"] == "Ср, 7 октября · 16:49"
        assert late["events"][0]["advice"] == de.advice(WEEK[0])
        monday = TZ.localize(datetime(2026, 10, 5, 23, 0))
        assert wa.card(db, user_free, chart, monday)["range"] == "5–11 октября"

    def test_hidden_other_times(self, db, user_free, chart, device, week):
        assert wa.card(db, user_free, chart, TZ.localize(datetime(2026, 10, 4, 18, 59))) is None
        assert wa.card(db, user_free, chart, TZ.localize(datetime(2026, 10, 6, 9, 0))) is None

    def test_calm(self, db, user_free, chart, device, week):
        week["events"] = [_ev(5, "Moon", "Sun", "conjunction", 9)]
        assert wa.card(db, user_free, chart, _evening())["calm"] is True

    def test_endpoint_flag_off_404(self, client, auth_headers_free):
        assert client.get("/api/v1/week-ahead", headers=auth_headers_free).status_code == 404
