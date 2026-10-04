"""Шаг 2 аудита (04.10.2026): событие около МЕСТНОЙ полуночи попадает в
местные сутки человека во всех разделах — лента, планер, станции, пуши
планера, чат. Пояса — Владивосток (UTC+10) и Нью-Йорк (UTC-4): у первого
местная дата впереди UTC с 14:00 UTC, у второго позади до 04:00 UTC.

До шага 2 всё это сравнивалось по UTC-дате (docs/audit_unified_model.md,
раздел 1.2, п. 7)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytz

from backend.feed import builder
from backend.push import cron
from backend.transit import house_passages as hp

VLA, NYC = "Asia/Vladivostok", "America/New_York"
_NATAL = {"houses": [{"number": i + 1, "sign": "Овен", "degree": i * 30} for i in range(12)]}
_CUSPS = [i * 30.0 for i in range(12)]

# 15:00 UTC 04.10 — во Владивостоке уже 01:00 05.10, в Нью-Йорке 11:00 04.10.
# 03:30 UTC 05.10 — в Нью-Йорке ещё 23:30 04.10, во Владивостоке 13:30 05.10.
_A = datetime(2026, 10, 4, 15, 0)
_B = datetime(2026, 10, 5, 3, 30)


def _chunk_event(exact: datetime, natal: str) -> dict:
    return {"transit_planet": "Saturn", "natal_planet": natal, "aspect_type": "square",
            "transit_sign": "Aries", "transit_degree": 1.0, "natal_sign": "Cancer",
            "peak_date": exact.date().isoformat(), "exact_date": exact.isoformat(),
            "peak_orb": 0.0, "applying": False, "significant": True, "free_unlocked": True}


# ── Лента: окно по местной дате пика ──────────────────────────────────────────

def _feed_natals(tzname: str, d_from: date, d_to: date, chunks: dict) -> set[str]:
    with patch.object(builder, "_transit_chunk", lambda _c, _p, y, m: chunks.get((y, m), [])):
        evs = builder._transit_events("c", [], d_from, d_to, pytz.timezone(tzname), "free")
    return {e["meta"]["natal_planet"] for e in evs}


def test_feed_window_uses_local_peak_date():
    chunks = {(2026, 10): [_chunk_event(_A, "Sun"), _chunk_event(_B, "Venus")]}
    d4, d5 = date(2026, 10, 4), date(2026, 10, 5)
    assert _feed_natals(VLA, d5, d5, chunks) == {"Sun", "Venus"}
    assert _feed_natals(VLA, d4, d4, chunks) == set()
    assert _feed_natals(NYC, d4, d4, chunks) == {"Sun", "Venus"}
    assert _feed_natals(NYC, d5, d5, chunks) == set()


def test_feed_takes_neighbour_utc_month_at_window_edge():
    """Пик 30.09 15:00 UTC — во Владивостоке 1 октября. Чанк сентября лента
    обязана прочитать, хотя окно начинается 1-го."""
    chunks = {(2026, 9): [_chunk_event(datetime(2026, 9, 30, 15, 0), "Mars")]}
    assert _feed_natals(VLA, date(2026, 10, 1), date(2026, 10, 31), chunks) == {"Mars"}
    assert _feed_natals(NYC, date(2026, 10, 1), date(2026, 10, 31), chunks) == set()


# ── Планер: строки периодов ───────────────────────────────────────────────────

def _fake_passages(planet_name, cusps, from_dt, to_dt, step_hours=None, refine_edges=False):
    if planet_name != "Sun":
        return [{"house": 1, "start_dt": from_dt, "end_dt": to_dt}]
    return [
        {"house": 6, "start_dt": from_dt, "end_dt": _A - timedelta(minutes=1)},
        {"house": 7, "start_dt": _A, "end_dt": datetime(2026, 11, 3, 3, 30)},
        {"house": 8, "start_dt": datetime(2026, 11, 3, 3, 31), "end_dt": to_dt},
    ]


def _sun_period(tzname: str) -> str:
    with patch.object(hp, "calculate_house_passages", side_effect=_fake_passages):
        p = hp.compute_planner_periods(_NATAL, date(2026, 10, 1), date(2026, 10, 31),
                                       today=date(2026, 10, 10), user_timezone=tzname,
                                       with_moon_week=False)
    sun = next(x for x in p["fast_planets"] if x["planet_key"] == "sun")
    return next(x["period"] for x in sun["periods"] if x["house"] == 7)


def test_planner_period_string_is_local():
    # Вход 15:00 UTC 04.10, выход 03:30 UTC 03.11 (в Нью-Йорке — 23:30 02.11).
    assert _sun_period(VLA) == "05.10 — 03.11"
    assert _sun_period(NYC) == "04.10 — 02.11"


# ── Пуши планера: «начался период» в местные сутки ───────────────────────────

def test_push_period_starts_on_local_day():
    with patch.object(hp, "calculate_house_passages", side_effect=_fake_passages):
        assert cron._period_starts_on("Sun", _CUSPS, date(2026, 10, 5), VLA) == [7]
        assert cron._period_starts_on("Sun", _CUSPS, date(2026, 10, 4), VLA) == []
        assert cron._period_starts_on("Sun", _CUSPS, date(2026, 10, 4), NYC) == [7]
        assert cron._period_starts_on("Sun", _CUSPS, date(2026, 10, 5), NYC) == []


def test_period_push_not_repeated_after_date_shift(monkeypatch):
    """В день выкатки ref входа около полуночи сдвинулся на сутки — пуш,
    ушедший вчера со старым ref, не уходит повторно с новым."""
    monkeypatch.setattr(cron, "_already_sent", lambda db, uid, kind, ref: ref == "Venus:7:2026-10-04")
    assert cron._seen_nearby(None, "u", "planner", "Venus:7:2026-10-05")
    assert cron._seen_nearby(None, "u", "planner_week", "Venus:7:2026-10-03")
    assert not cron._seen_nearby(None, "u", "planner", "Venus:7:2026-10-06")
    assert not cron._seen_nearby(None, "u", "daily", "2026-10-05")
    assert not cron._seen_nearby(None, "u", "transit", "Saturn:Sun:square:2026-10-05")


# ── Станции: точный момент и местная дата ─────────────────────────────────────

def test_station_date_is_local_and_has_exact_moment():
    stations = hp.compute_retrograde_stations(date(2026, 1, 1), date(2027, 12, 31), "UTC")
    shifted = 0
    for s in stations:
        at = datetime.fromisoformat(s["at"])
        assert at.tzinfo is not None
        for tz in (VLA, NYC):
            local = at.astimezone(ZoneInfo(tz)).date()
            shifted += local != at.date()
            got = hp.compute_retrograde_stations(local, local, tz)
            assert any(g["planet"] == s["planet"] and g["status"] == s["status"]
                       and g["date_iso"] == local.isoformat() for g in got), (s, tz)
            prev = hp.compute_retrograde_stations(local - timedelta(days=1), local - timedelta(days=1), tz)
            assert not any(g["planet"] == s["planet"] and g["status"] == s["status"] for g in prev), (s, tz)
    assert shifted, "в выборке нет станции, у которой местная дата отличается от UTC"


def test_feed_station_at_is_exact_not_noon():
    feed_tz = pytz.timezone(VLA)
    r = hp.compute_retrograde_stations(date(2026, 1, 1), date(2026, 12, 31), VLA)[0]
    with patch("backend.transit.house_passages.compute_planner_periods",
               return_value={"retrogrades": [r]}):
        evs = builder._planner_events("c", _NATAL, date(2026, 1, 1), date(2026, 12, 31),
                                      date(2026, 1, 1), VLA, "free", feed_tz,
                                      datetime(2026, 1, 1, 12))
    st = next(e for e in evs if e["kind"] == "retrograde")
    assert datetime.fromisoformat(st["at"]) == datetime.fromisoformat(r["at"])
    assert st["at"][:10] == r["date_iso"]


# ── Чат: дата точного аспекта ────────────────────────────────────────────────

def test_chat_exact_date_is_local():
    """Натальный Меркурий в квадрате к Юпитеру ровно в 18:00 UTC 02.10:
    во Владивостоке это уже 03.10 04:00, в Нью-Йорке — 02.10 14:00."""
    from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd
    from backend.interpretation.rag import build_transits_block
    from backend.tests.test_chat_p0 import _exact_dates, _natal

    moment = datetime(2026, 10, 2, 18, 0)
    lon = _calc_planet_position(PLANETS["Jupiter"], round(_datetime_to_jd(moment), 6))[0]
    chart = {"planets": [_natal("Mercury", lon + 90)], "houses": []}
    today = date(2026, 10, 2)
    assert _exact_dates(build_transits_block(chart, 5, today, "test-local-day", VLA)) == [date(2026, 10, 3)]
    assert _exact_dates(build_transits_block(chart, 5, today, "test-local-day", NYC)) == [date(2026, 10, 2)]


# ── «Сегодня» одно у всех разделов ───────────────────────────────────────────

def test_today_same_everywhere_around_midnight(monkeypatch):
    import types
    import backend.time_utils as tu
    from backend.pdf_reports.build import today_for
    from backend.time_utils import local_today, user_tz

    for tz, instant, want in (
        (VLA, datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc), date(2026, 10, 5)),   # 00:30
        (NYC, datetime(2026, 10, 5, 3, 30, tzinfo=timezone.utc), date(2026, 10, 4)),    # 23:30
    ):
        class Frozen(datetime):
            @classmethod
            def now(cls, tzinfo=None, _i=instant):
                return _i.astimezone(tzinfo) if tzinfo else _i.replace(tzinfo=None)
        monkeypatch.setattr(tu, "datetime", Frozen)
        user = types.SimpleNamespace(device_timezone=tz)
        chart = types.SimpleNamespace(timezone="Europe/Moscow")
        assert local_today(user_tz(None, user, chart)) == want   # пуши, письма, /transits
        assert today_for(user, chart) == want                      # PDF
        assert local_today(user_tz(tz, None, chart)) == want       # лента, планер, прогноз, чат
