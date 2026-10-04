"""Одна функция фаз — одна местная дата во всех разделах (шаг 6 аудита).

До 04.10.2026 новолуние 10.10.2026 18:50 по Москве во Владивостоке (11.10
01:50) лента ставила на 11.10, а лунный календарь, «Ближайшие 30 дней»,
пуш и дайджест — на 10.10 (GMT+3 или дата UTC).

Виджет и сторис — фаза дня story_card.moon_phase (таблица владельца
04.10.2026): точная фаза только в местный день момента.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytz

from backend.calendar.lunar_engine import lunations

# (пояс, тип, местная дата, момент UTC)
CASES = [
    # Владивосток: новолуние 10.10.2026 15:50 UTC — 11.10 01:50 местного.
    ("Asia/Vladivostok", "new_moon", date(2026, 10, 11), datetime(2026, 10, 10, 15, 50, tzinfo=timezone.utc)),
    # Нью-Йорк, до полуночи: новолуние 11.09.2026 03:27 UTC — 10.09 23:27.
    ("America/New_York", "new_moon", date(2026, 9, 10), datetime(2026, 9, 11, 3, 27, tzinfo=timezone.utc)),
    # Нью-Йорк, после полуночи: полнолуние 26.10.2026 04:11 UTC — 26.10 00:11.
    ("America/New_York", "full_moon", date(2026, 10, 26), datetime(2026, 10, 26, 4, 11, tzinfo=timezone.utc)),
]


def _sections(tz: str, d: date) -> dict[str, set[date]]:
    """Местные даты фаз в окне d±3 по каждому разделу."""
    from datetime import timedelta

    from backend.email_service import week_phase_lines
    from backend.feed.builder import _lunar_events
    from backend.main import _compute_lunar_calendar
    from backend.push.cron import _phases_on_local_date
    from backend.story_card import moon_phase

    lo, hi = d - timedelta(days=3), d + timedelta(days=3)
    days = [lo + timedelta(days=i) for i in range(7)]
    cal = _compute_lunar_calendar(d.year, d.month, tz)
    return {
        "лунный календарь, «Ближайшие 30 дней»": {
            date.fromisoformat(p["date"]) for p in cal["phases"]
            if lo <= date.fromisoformat(p["date"]) <= hi},
        "лента": {date.fromisoformat(e["at"][:10]) for e in _lunar_events(lo, hi, pytz.timezone(tz))
                  if e["kind"] == "moon_phase"},
        "пуш фазы": {x for x in days if _phases_on_local_date(x, tz)},
        "дайджест": {date.fromisoformat(x[:10]) for x in week_phase_lines(lo, hi, tz)},
        "виджет и сторис": {x for x in days if moon_phase(x, tz) in ("new_moon", "full_moon")},
    }


@pytest.mark.parametrize("tz,kind,local,at", CASES)
def test_one_local_date_everywhere(tz, kind, local, at):
    for name, got in _sections(tz, local).items():
        assert got == {local}, f"{tz}: {name} — {sorted(got)}"


@pytest.mark.parametrize("tz,kind,local,at", CASES)
def test_moment(tz, kind, local, at):
    from backend.forecast.facts import find_phase

    found = find_phase(kind, local)
    assert found is not None and abs((found - at).total_seconds()) < 60


def test_calendar_time_is_local():
    from backend.main import _compute_lunar_calendar

    cal = _compute_lunar_calendar(2026, 10, "Asia/Vladivostok")
    nm = [p for p in cal["phases"] if p["type"] == "new_moon"]
    assert [(p["date"], p["time"]) for p in nm] == [("2026-10-11", "01:50")]
    assert cal["tz"] == "Asia/Vladivostok"


def test_quarters_and_eclipses():
    got = lunations(datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 9, 1, tzinfo=timezone.utc),
                    types=("new_moon", "first_quarter", "full_moon", "last_quarter"), eclipses=True)
    kinds = [x.type for x in got]
    assert kinds.count("eclipse") == 2  # 12.08 солнечное, 28.08 лунное
    assert {"first_quarter", "last_quarter"} <= set(kinds)
    assert all(x.at.tzinfo is not None for x in got)


def test_daily_sign_at_local_noon():
    """Знак дня — в местный полдень (как прогноз дня), не в 12:00 UTC."""
    from backend.calendar.lunar_engine import ZODIAC_SIGNS, _jd_at, _lon
    from backend.main import _compute_lunar_calendar
    from zoneinfo import ZoneInfo

    tz = "Asia/Vladivostok"
    for row in _compute_lunar_calendar(2026, 10, tz)["daily_signs"]:
        d = date.fromisoformat(row["date"])
        noon = datetime(d.year, d.month, d.day, 12, tzinfo=ZoneInfo(tz))
        assert row["sign"] == ZODIAC_SIGNS[int(_lon(_jd_at(noon), "Moon") // 30)]
