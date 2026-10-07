"""Шаг 9 (термины, под sky_event): пуш планера за неделю — «Через неделю —
новый период» под флагом, «Через неделю — новое окно» без него. Реальный путь
рассылки (`_process_user`): карта — строка NatalChart в базе, флаг — строка
feature_flags на получателя, `_sky_on` не подменяется (ловушка из
docs/handoff.md: у копий карты флаг выключен).
"""
from datetime import date

import pytest

from backend import flags
from backend.models import FeatureFlag
from backend.push import cron
from backend.tests.test_day_event import sent  # noqa: F401 — фикстура (время — 10.09.2026 08:30 МСК)
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура

WEEK = date(2026, 9, 17)   # «сегодня» фикстуры `sent` + ADVANCE_WEEK_DAYS


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.mark.parametrize("on, title", [(False, "Через неделю — новое окно"),
                                       (True, "Через неделю — новый период")])
def test_planner_week_title_real_send(db, user_free, chart, sent, monkeypatch, on, title):  # noqa: F811
    user_free.push_daily_forecast = False
    user_free.push_moon_phases = False
    user_free.push_key_transits = False
    user_free.push_planner = True
    if on:
        db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()
    # Один период: Венера входит в 7 дом ровно через неделю; остальное — пусто.
    monkeypatch.setattr(cron, "_period_starts_on",
                        lambda planet, cusps, d, tz: [7] if planet == "Venus" and d == WEEK else [])
    monkeypatch.setattr(cron, "_planner_month_candidates", lambda *a: [])
    cron._process_user(db, user_free)
    assert [p["title"] for p in sent] == [title]
