"""/transits из ядра (задание 4.8, флаг sky_event). Карта вымышленная, как в
test_sky.py; у каждого теста свой id карты (чанки sky:v1 кэшируются по id)."""
import types
from datetime import date

from backend.tests.test_sky import CHART
from backend.transit.engine import window_events


def _chart(cid, **kw):
    return types.SimpleNamespace(**{**CHART, "id": cid, "time_unknown": False, **kw})


def _of(rows, tp, np_, asp):
    return [r for r in rows if (r["transit_planet"], r["natal_planet"], r["aspect_type"]) == (tp, np_, asp)]


def test_vladivostok_touch_after_midnight_local_date_on_screen():
    """Касание Меркурия к Плутону 29.11.2026 19:12 UTC — во Владивостоке уже
    30.11 05:12: на экране местная дата, peak_date (ключ) — UTC-дата."""
    rows = window_events(_chart("test-sky-web-vvo"), date(2026, 11, 1), date(2026, 11, 30),
                         sky=True, tz="Asia/Vladivostok")
    r, = [r for r in _of(rows, "Mercury", "Pluto", "conjunction") if r["peak_date"] == "2026-11-29"]
    assert (r["touch_date"], r["exact_date"]) == ("2026-11-30", "2026-11-30T05:12")


def test_loop_card_per_touch_whole_event_bounds():
    chart = _chart("test-sky-web-loop")
    rows = (window_events(chart, date(2026, 10, 1), date(2026, 10, 31), sky=True, tz="Europe/Moscow")
            + window_events(chart, date(2026, 11, 1), date(2026, 11, 30), sky=True, tz="Europe/Moscow"))
    cards = _of(rows, "Mercury", "Pluto", "conjunction")
    assert [c["touch_date"] for c in cards] == ["2026-10-21", "2026-10-27", "2026-11-29"]
    assert {(c["start_date"], c["end_date"]) for c in cards} == {("2026-10-17", "2026-12-01")}


def test_pluto_station_at_saturn_no_card():
    rows = window_events(_chart("test-sky-web-station"), date(2027, 10, 1), date(2027, 10, 31),
                         sky=True, tz="Europe/Moscow")
    assert rows and not _of(rows, "Pluto", "Saturn", "conjunction")


def test_no_birth_time_no_moon_asc_mc():
    rows = window_events(_chart("test-sky-web-notime", time_unknown=True), date(2026, 10, 1),
                         date(2026, 10, 31), sky=True, tz="Europe/Moscow")
    assert rows and not {r["natal_planet"] for r in rows} & {"Moon", "Ascendant", "Midheaven"}


def test_without_flag_no_touch_date():
    rows = window_events(_chart("test-sky-web-off"), date(2026, 10, 1), date(2026, 10, 31))
    assert rows and not any("touch_date" in r for r in rows)
