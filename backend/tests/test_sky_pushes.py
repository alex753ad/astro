"""Флаг sky_event (задание 4.12, PR б): старые пуши «вошёл в орб», «за 4°»,
«тройное касание» под флагом не собираются и не уходят — ни утром, ни в
выдаче будущих (`collect_upcoming`); без флага — как было."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend import flags
from backend.models import FeatureFlag, PushSentLog
from backend.push import cron
from backend.tests.test_day_event import _fake, sent  # noqa: F401 — фикстура
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура

OLD = {"transit", "transit_approach", "triple"}


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def only_old(monkeypatch, db, user_free):
    """Включены только «Важные транзиты»; три старых вида — подставные."""
    user_free.push_daily_forecast = False
    user_free.push_planner = False
    user_free.push_moon_phases = False
    user_free.push_key_transits = True
    db.commit()
    monkeypatch.setattr(cron, "_transit_entry_candidates", lambda *a: [_fake("transit")])
    monkeypatch.setattr(cron, "_four_degree_candidates", lambda *a: [_fake("transit_approach")])
    monkeypatch.setattr(cron, "_triple_touch_candidates", lambda *a: [_fake("triple")])


@pytest.fixture
def sky_on(db, user_free):
    db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


def test_flag_off_collects_old_kinds(db, user_free, chart, only_old):  # noqa: F811
    kinds = {c["kind"] for c in cron._collect_candidates(db, user_free, chart, date(2026, 9, 10))}
    assert OLD <= kinds


def test_flag_on_old_kinds_not_collected(db, user_free, chart, only_old, sky_on):  # noqa: F811
    kinds = {c["kind"] for c in cron._collect_candidates(db, user_free, chart, date(2026, 9, 10))}
    assert kinds & OLD == set()
    kinds = {e["kind"] for e in cron.collect_upcoming(db, user_free, 3)["events"]}
    assert kinds & OLD == set()


def test_flag_on_old_kinds_not_sent(db, user_free, chart, only_old, sky_on, sent):  # noqa: F811
    assert cron._process_user(db, user_free) == 0
    assert sent == []
    assert {r.kind for r in db.query(PushSentLog).all()} & OLD == set()


def test_daily_line_from_core(monkeypatch):
    """Строка утреннего пуша под флагом — по событиям ядра, активным в
    местные сутки; в перерыве петли событие не считается."""
    U = lambda *a: datetime(*a, tzinfo=timezone.utc)
    ev = lambda aspect, passes: SimpleNamespace(aspect=aspect, passes=passes)
    trine_gap = ev("trine", [(U(2026, 9, 1), U(2026, 9, 5)), (U(2026, 9, 20), U(2026, 9, 30))])
    square = ev("square", [(U(2026, 9, 8), U(2026, 9, 12))])
    monkeypatch.setattr("backend.sky.sky_events", lambda c, s, e: [trine_gap, square])
    body = cron._daily_body(SimpleNamespace(), date(2026, 9, 10), "Europe/Moscow", sky=True)
    assert body.startswith("Сегодня активный день")
