"""Точное касание — корень знаковой разности долгот, а не минимум орба
(аудит 8.1, 05.10.2026). Карта вымышленная, как в test_day_event.py."""
from datetime import date, datetime, timedelta

import pytest

from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd, calculate_full_chart
from backend.transit.engine import calculate_transits

_FULL, _ = calculate_full_chart(datetime(1991, 3, 8, 3, 40), 55.75, 37.62, house_system="placidus")
NATAL = [{"name": p.name, "longitude": p.longitude, "sign": p.sign} for p in _FULL.planets]


def _event(tp, np_, asp, peak, frm, to):
    natal = [p for p in NATAL if p["name"] == np_]
    evs = [e for e in calculate_transits(natal, frm, to, planet_filter=[tp])
           if (e.natal_planet, e.aspect_type) == (np_, asp) and e.peak_date == peak]
    assert len(evs) == 1
    return evs[0]


@pytest.mark.parametrize("tp,np_,asp,peak,orb", [
    # Станция Плутона в 1,6° от Сатурна: минимум орба, касания нет.
    ("Pluto", "Saturn", "conjunction", "2027-10-18", 1.6),
    # Станция Юпитера в 0,08° от Венеры — тоже не касание.
    ("Jupiter", "Venus", "trine", "2027-04-13", 0.08),
])
def test_station_is_not_a_touch(tp, np_, asp, peak, orb):
    p = date.fromisoformat(peak)
    e = _event(tp, np_, asp, peak, p - timedelta(days=20), p + timedelta(days=20))
    assert e.peak_orb == pytest.approx(orb, abs=0.01)
    assert e.exact_date is None
    assert e.no_touch


def test_real_touch_to_the_minute():
    """Юпитер квадрат Плутон 05.10.2026: момент — до минуты против своей
    бисекции до секунды (секунды движок отбрасывает)."""
    e = _event("Jupiter", "Pluto", "square", "2026-10-05", date(2026, 9, 20), date(2026, 10, 20))
    assert not e.no_touch
    n = next(p["longitude"] for p in NATAL if p["name"] == "Pluto")

    def f(t):
        lon = _calc_planet_position(PLANETS["Jupiter"], round(_datetime_to_jd(t), 6))[0]
        return min(((lon - n - s * 90 + 180) % 360 - 180 for s in (1, -1)), key=abs)

    lo, hi = datetime(2026, 10, 4), datetime(2026, 10, 6)
    assert (f(lo) > 0) != (f(hi) > 0)
    while hi - lo > timedelta(seconds=1):
        mid = lo + (hi - lo) / 2
        lo, hi = (mid, hi) if (f(mid) > 0) == (f(lo) > 0) else (lo, mid)
    assert e.exact_date == lo.strftime("%Y-%m-%dT%H:%M")
