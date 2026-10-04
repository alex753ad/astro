"""Шаг 2б аудита (04.10.2026): граница периода по дому — настоящий вход и
окончательный выход планеты, а не край окна поиска; ретроградная петля —
один период. Расчёт настоящий (Swiss Ephemeris), куспиды подобраны."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd, _find_house
from backend.transit import house_passages as hp


def _lon(planet: str, t: datetime) -> float:
    return _calc_planet_position(PLANETS[planet], round(_datetime_to_jd(t), 6))[0]


def _house(planet: str, t: datetime, cusps: list[float]) -> int:
    return _find_house(_lon(planet, t), cusps)


def _cusps(first: float) -> list[float]:
    return [(first + 30 * i) % 360 for i in range(12)]


def _crossing(planet: str, lon: float, a: datetime, b: datetime) -> datetime:
    """Момент, когда планета проходит долготу `lon` между a и b (бисекция)."""
    side = lambda t: ((_lon(planet, t) - lon + 180) % 360) - 180 > 0
    sa = side(a)
    for _ in range(40):
        m = a + (b - a) / 2
        a, b = (m, b) if side(m) == sa else (a, m)
    return b


def _close(x: datetime, y: datetime, minutes: int = 5) -> bool:
    return abs(x - y) <= timedelta(minutes=minutes)


# ── Длинный проход Солнца ─────────────────────────────────────────────────────

_WIDE = [0, 30, 60, 90, 120, 150, 240, 255, 270, 300, 330, 345]

def test_long_sun_passage_has_real_edges_in_any_window():
    """Дом 6 шириной 90° (150°–240°): Солнце в нём ~3 месяца, выход 22.11 —
    позже прежнего края «конец месяца + 40 дней» (09.11). Планер (окно — сентябрь) и лента (окно до ноября)
    обязаны дать одни и те же настоящие границы."""
    cusps = _WIDE
    entry = _crossing("Sun", 150, datetime(2026, 8, 15), datetime(2026, 9, 1))
    exit_ = _crossing("Sun", 240, datetime(2026, 11, 15), datetime(2026, 12, 1))
    for frm, to in ((datetime(2026, 9, 1), datetime(2026, 9, 30, 23, 59)),
                    (datetime(2026, 9, 20), datetime(2026, 11, 3, 23, 59))):
        p = next(x for x in hp.house_periods("Sun", cusps, frm, to) if x["house"] == 6)
        assert _close(p["start_dt"], entry), (p, entry)
        assert _close(p["end_dt"] + timedelta(minutes=1), exit_), (p, exit_)


def test_planner_month_string_uses_real_exit():
    cusps = _WIDE
    houses = [{"number": i + 1, "degree": c} for i, c in enumerate(cusps)]
    r = hp.compute_planner_periods({"houses": houses}, date(2026, 9, 1), date(2026, 9, 30),
                                   today=date(2026, 9, 10), user_timezone="UTC", with_moon_week=False)
    sun = next(x for x in r["fast_planets"] if x["planet_key"] == "sun")
    six = next(x for x in sun["periods"] if x["house"] == 6)
    exit_ = _crossing("Sun", 240, datetime(2026, 11, 15), datetime(2026, 12, 1))
    assert six["period"].endswith((exit_ - timedelta(minutes=1)).strftime("%d.%m")), six


# ── Медленная планета с ретроградной петлёй ───────────────────────────────────

def _saturn_loop():
    """Куспид на 2° ниже станции ретроградности Сатурна: вперёд через куспид
    (c1), назад (c2), снова вперёд (c3)."""
    st = next(s for s in hp.compute_retrograde_stations(date(2026, 1, 1), date(2027, 12, 31), "UTC")
              if s["planet"] == "saturn" and s["status"] == "start")
    t_st = datetime.fromisoformat(st["at"]).replace(tzinfo=None)
    cusp = (_lon("Saturn", t_st) - 2) % 360
    c1 = _crossing("Saturn", cusp, t_st - timedelta(days=200), t_st)
    c2 = _crossing("Saturn", cusp, t_st, t_st + timedelta(days=140))
    c3 = _crossing("Saturn", cusp, t_st + timedelta(days=140), t_st + timedelta(days=400))
    cusps = _cusps(cusp)
    below, above = _house("Saturn", c1 - timedelta(days=1), cusps), _house("Saturn", c1 + timedelta(days=1), cusps)
    return cusps, c1, c2, c3, below, above


def test_retro_loop_is_one_period_until_final_exit():
    cusps, c1, c2, c3, below, above = _saturn_loop()
    assert c1 < c2 < c3
    ps = hp.house_periods("Saturn", cusps, c1 - timedelta(days=30), c3 + timedelta(days=30), step_hours=72)
    ab = [p for p in ps if p["house"] == above]
    be = [p for p in ps if p["house"] == below]
    assert len(ab) == 1 and len(be) == 1, ps
    assert _close(ab[0]["start_dt"], c1, 60), (ab, c1)                         # первый вход
    assert _close(be[0]["end_dt"] + timedelta(minutes=1), c3, 60), (be, c3)    # окончательный выход


def test_retro_reentry_is_not_a_new_period_start():
    """Пуши и «Ближайшие 30 дней»: возврат в дом петлёй — не «начался период»."""
    cusps, c1, c2, c3, below, above = _saturn_loop()
    day = timedelta(days=1)
    assert [p["house"] for p in hp.period_starts("Saturn", cusps, c1 - day, c1 + day)] == [above]
    assert hp.period_starts("Saturn", cusps, c2 - day, c2 + day) == []   # назад в «below» — возврат
    assert hp.period_starts("Saturn", cusps, c3 - day, c3 + day) == []   # снова в «above» — возврат


# ── Проход, начавшийся задолго до окна ────────────────────────────────────────

def test_passage_started_before_window_gets_first_entry():
    """Сатурн вошёл в дом за ~2 года до окна: начало — настоящий первый вход,
    а не край окна, и до него в пределах петли планеты в доме не было."""
    t0 = datetime(2024, 9, 1)
    cusps = _cusps((_lon("Saturn", t0) - 1) % 360)
    frm, to = datetime(2026, 6, 1), datetime(2026, 6, 30)
    house = _house("Saturn", frm, cusps)
    p = next(x for x in hp.house_periods("Saturn", cusps, frm, to, step_hours=72) if x["house"] == house)
    assert p["start_dt"] < frm - timedelta(days=300), p
    assert _house("Saturn", p["start_dt"] + timedelta(minutes=1), cusps) == house
    assert _house("Saturn", p["start_dt"] - timedelta(minutes=1), cusps) != house
    loop = timedelta(days=hp.LOOP_DAYS["Saturn"])
    assert hp._seen_within(PLANETS["Saturn"], cusps, p["start_dt"], house, -loop) is None
