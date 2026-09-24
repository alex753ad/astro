"""Смена года и 29 февраля: всё, что считает «сегодня», месяцы и окна дней.

Моменты из задания 24.09.2026: 31.12.2026 23:30 → 01.01.2027 00:30 по Москве
и 28–29.02.2028 (високосный). ⚠️ По Москве Новый год наступает в 21:00 UTC, а
сервер живёт в UTC — поэтому каждая проверка ниже смотрит на МЕСТНУЮ дату
там, где её видит человек, а не на серверную.
"""

from __future__ import annotations

import types
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
import pytz

MSK = pytz.timezone("Europe/Moscow")
EVE = MSK.localize(datetime(2026, 12, 31, 23, 30))   # 20:30 UTC
NY = MSK.localize(datetime(2027, 1, 1, 0, 30))       # 21:30 UTC 31.12 — сервер ещё в 2026


# ── Даты и окна ──────────────────────────────────────────────────────────────

class TestMonthArithmetic:
    def test_plus_months_over_year_and_leap_day(self):
        from backend.feed.builder import _plus_months
        assert _plus_months(date(2026, 12, 31), 3) == date(2027, 3, 31)
        assert _plus_months(date(2027, 11, 30), 3) == date(2028, 2, 29)
        assert _plus_months(date(2028, 2, 29), 12) == date(2029, 2, 28)

    def test_minus_one_month_over_year(self):
        from backend.feed.horizon import _minus_one_month
        assert _minus_one_month(date(2027, 1, 1)) == date(2026, 12, 1)
        assert _minus_one_month(date(2028, 3, 31)) == date(2028, 2, 29)

    @pytest.mark.parametrize("tier", ["free", "lite", "pro", "premium"])
    @pytest.mark.parametrize("today", [date(2026, 12, 31), date(2027, 1, 1),
                                       date(2028, 2, 28), date(2028, 2, 29)])
    def test_transit_window_contains_today_and_ends_on_month_end(self, tier, today):
        import calendar
        from backend.auth.rate_limits import transits_date_window
        lo, hi = transits_date_window(tier, today)
        assert lo <= today <= hi
        assert hi.day == calendar.monthrange(hi.year, hi.month)[1]

    @pytest.mark.parametrize("today", [date(2026, 12, 31), date(2027, 1, 1), date(2028, 2, 29)])
    def test_feed_horizon_contains_today(self, today):
        from backend.feed.horizon import feed_horizon
        for tier in ("free", "lite", "pro", "premium"):
            h = feed_horizon(tier, today)
            assert h.start <= today <= h.end


class TestMonthlyUsageKey:
    """Лимиты «в месяц» — календарный месяц UTC (докстринг _current_period_ym).
    По Москве новый месяц счётчика начинается в 03:00 1-го числа — это
    закреплено, а не случайность: сменить пояс счётчика — решение владельца."""

    def test_rolls_over_at_utc_midnight(self):
        from backend.auth import rate_limits
        with patch.object(rate_limits.time, "gmtime", return_value=NY.astimezone(pytz.utc).timetuple()):
            assert rate_limits._current_period_ym() == "2026-12"
        after = pytz.utc.localize(datetime(2027, 1, 1, 0, 30))
        with patch.object(rate_limits.time, "gmtime", return_value=after.timetuple()):
            assert rate_limits._current_period_ym() == "2027-01"


# ── Прогноз «Сегодня/завтра» и лунный прогноз ────────────────────────────────

class TestForecastDays:
    def test_new_year_eve_opens_first_of_january(self):
        from backend.forecast.router import allowed_days
        assert allowed_days(EVE) == [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1)]

    def test_after_midnight_today_is_january_first(self):
        from backend.forecast.router import allowed_days
        assert allowed_days(NY) == [date(2026, 12, 31), date(2027, 1, 1)]

    def test_leap_day(self):
        from backend.forecast.router import allowed_days
        eve = MSK.localize(datetime(2028, 2, 28, 20, 0))
        assert allowed_days(eve)[-1] == date(2028, 2, 29)
        eve = MSK.localize(datetime(2028, 2, 29, 20, 0))
        assert allowed_days(eve)[-1] == date(2028, 3, 1)

    def test_lunation_found_across_new_year(self):
        from backend.forecast.facts import find_phase
        # Новолуние 07.01.2027 20:24 UTC — ищем от даты в прошлом году окна.
        at = find_phase("new_moon", date(2027, 1, 7))
        assert at is not None and at.date() == date(2027, 1, 7)


# ── Фазы и затмения через Новый год ──────────────────────────────────────────

class TestLunarCalendarAcrossYear:
    def test_every_phase_once_in_dec_and_jan(self):
        from backend.main import _compute_lunar_calendar
        dec = _compute_lunar_calendar(2026, 12)["phases"]
        jan = _compute_lunar_calendar(2027, 1)["phases"]
        keys = [(p["type"], p["date"]) for p in dec + jan]
        assert len(keys) == len(set(keys))
        assert all(d.startswith("2026-12") for _, d in keys[:len(dec)])
        assert all(d.startswith("2027-01") for _, d in keys[len(dec):])
        # Две фазы на месяц, ни одна не потерялась на стыке.
        assert len(dec) >= 2 and len(jan) >= 2

    def test_eclipses_union_of_months_equals_range(self):
        from backend.calendar.lunar_engine import get_eclipses
        whole = get_eclipses(date(2026, 12, 1), date(2027, 2, 28))
        parts = (get_eclipses(date(2026, 12, 1), date(2026, 12, 31))
                 + get_eclipses(date(2027, 1, 1), date(2027, 1, 31))
                 + get_eclipses(date(2027, 2, 1), date(2027, 2, 28)))
        assert sorted(e["date"] for e in whole) == sorted(e["date"] for e in parts)


# ── Уведомление о фазе «завтра» — по местной дате ────────────────────────────

class TestMoonPushLocalDate:
    """Раньше сравнивалась UTC-дата фазы с местным «завтра» (push/cron.py)."""

    def test_phase_after_local_midnight_belongs_to_next_local_day(self):
        from backend.push.cron import _phases_on_local_date
        # Полнолуние 20.02.2027 23:23 UTC — по Москве 21.02 02:23.
        assert _phases_on_local_date(date(2027, 2, 20), "Europe/Moscow") == []
        got = _phases_on_local_date(date(2027, 2, 21), "Europe/Moscow")
        assert [p.type for p in got] == ["full_moon"]

    def test_phase_on_first_of_month_is_not_lost(self):
        from backend.push.cron import _phases_on_local_date
        # Новолуние 30.06.2030 21:34 UTC — по Москве 01.07 00:34: UTC-месяц другой.
        got = _phases_on_local_date(date(2030, 7, 1), "Europe/Moscow")
        assert [p.type for p in got] == ["new_moon"]

    def test_west_of_utc(self):
        from backend.push.cron import _phases_on_local_date
        # Новолуние 09.12.2026 00:51 UTC — в Нью-Йорке ещё 08.12.
        got = _phases_on_local_date(date(2026, 12, 8), "America/New_York")
        assert [p.type for p in got] == ["new_moon"]


# ── Неделя планера и лента через Новый год ───────────────────────────────────

class TestMoonWeekLock:
    """Free видит текущую неделю вперёд. Неделя 28.12.2026–03.01.2027."""

    def test_free_current_week_spans_new_year(self):
        from backend.transit.planner_engine import is_moon_week_locked
        now = EVE.replace(tzinfo=None)
        assert not is_moon_week_locked("free", "2027-01-02T10:00:00", "2027-01-04T12:00:00", now)
        assert is_moon_week_locked("free", "2027-01-04T10:00:00", "2027-01-06T12:00:00", now)
        assert not is_moon_week_locked("free", "2026-12-20T10:00:00", "2026-12-22T12:00:00", now)
        assert not is_moon_week_locked("lite", "2027-03-01T10:00:00", "2027-03-03T12:00:00", now)


def _chart():
    from backend.tests.test_feed import _HOUSES, _NATAL_PLANETS
    return types.SimpleNamespace(
        id="year-boundary-chart", planets=_NATAL_PLANETS, houses=_HOUSES,
        ascendant={"longitude": 200.0, "sign": "Libra"},
        midheaven={"longitude": 110.0, "sign": "Cancer"},
        timezone="Europe/Moscow", time_unknown=False,
    )


class TestFeedAcrossNewYear:
    @pytest.fixture(autouse=True)
    def _clear(self):
        from backend.feed.builder import feed_cache
        feed_cache.clear()
        yield
        feed_cache.clear()

    def _moon(self, now):
        from backend.feed.builder import build_feed
        feed = build_feed(chart=_chart(), from_date=date(2026, 12, 20), to_date=date(2027, 4, 30),
                          today=now.date(), tier="pro", now=now.replace(tzinfo=None))
        return feed, [e for e in feed["events"] if e["kind"] == "planner_moon_house"]

    def test_moon_passages_have_no_gap_over_new_year(self):
        _, moon = self._moon(NY)
        starts = sorted(datetime.fromisoformat(e["at"]) for e in moon)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        assert gaps and max(gaps) < timedelta(days=4)
        # Момент Нового года покрыт ровно одним проходом — не дырой и не двумя.
        covering = [e for e in moon
                    if datetime.fromisoformat(e["at"]) <= NY < datetime.fromisoformat(e["ends_at"])]
        assert len(covering) == 1

    def test_three_month_window_counts_from_local_monday(self):
        _, moon = self._moon(NY)
        last = max(datetime.fromisoformat(e["at"]).date() for e in moon)
        # Понедельник недели 01.01.2027 — 28.12.2026, +3 месяца = 28.03.2027.
        assert date(2027, 3, 24) <= last <= date(2027, 3, 28)

    def test_lunar_phases_both_sides_of_new_year(self):
        feed, _ = self._moon(EVE)
        phases = [e["at"][:10] for e in feed["events"] if e["kind"] == "moon_phase"]
        assert any(d.startswith("2026-12") for d in phases)
        assert any(d.startswith("2027-01") for d in phases)


class TestFeedRouterUsesChartLocalDate:
    """До 24.09.2026 роутер ленты брал date.today() (UTC) при «сейчас» по
    поясу карты. В 00:30 по Москве 1 января это давало 31 декабря."""

    def test_today_is_local(self):
        import inspect
        from backend.feed import router
        src = inspect.getsource(router)
        assert "today=date.today()" not in src
        assert "today=now.date()" in src


# ── Письма по окнам дней ─────────────────────────────────────────────────────

class TestLifecycleWindowsAcrossYear:
    def test_day14_due_over_new_year(self, db):
        from backend.lifecycle_emails import _onboarding_candidates
        from backend.models import User
        u = User(email="ny@example.com", hashed_password=None, tier="free",
                 created_at=datetime(2026, 12, 20, 12, 0))
        db.add(u)
        db.commit()
        assert u in _onboarding_candidates(db, "retention_day14", datetime(2027, 1, 3, 12, 0))
        assert u not in _onboarding_candidates(db, "retention_day14", datetime(2027, 1, 2, 12, 0))
        # Последний день окна — +21: 10.01.2027, дальше письмо не догоняется.
        assert u not in _onboarding_candidates(db, "retention_day14", datetime(2027, 1, 11, 12, 1))
