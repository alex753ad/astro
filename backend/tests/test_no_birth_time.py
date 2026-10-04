"""Шаг 3 аудита (04.10.2026): карта без времени рождения — ни один раздел не
отдаёт натальную Луну, ASC, MC и дома (backend/chart_points.py).

Карта подобрана так, чтобы эти точки ТОЧНО задевались: натальная Луна стоит
на Сатурне, ASC — на Юпитере, MC — на Марсе дней теста. С известным временем
те же разделы их отдают (контроль, `_known_time_is_seen`) — иначе проверка
«нет Луны» была бы пустой."""

from __future__ import annotations

import types
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.feed.builder import feed_cache
from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd

D0 = date(2026, 10, 5)
DAYS = [D0 + timedelta(days=i) for i in range(5)]
TZ = "Europe/Moscow"
HIDDEN = {"Moon", "Ascendant", "Midheaven"}
_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio",
          "Sagittarius", "Capricorn", "Aquarius", "Pisces"]


def _lon(planet: str, d: date = D0) -> float:
    return _calc_planet_position(PLANETS[planet], round(_datetime_to_jd(datetime(d.year, d.month, d.day, 12)), 6))[0]


def _point(name: str, lon: float, house=4) -> dict:
    lon %= 360
    return {"name": name, "longitude": lon, "sign": _SIGNS[int(lon // 30)],
            "degree_in_sign": lon % 30, "house": house, "retrograde": False}


def _chart(time_unknown: bool):
    planets = [_point("Sun", 100), _point("Moon", _lon("Saturn")), _point("Mercury", _lon("Saturn") + 90),
               _point("Venus", 300), _point("Mars", 330), _point("Jupiter", 20), _point("Saturn", 50),
               _point("Uranus", 160), _point("Neptune", 250), _point("Pluto", 190),
               _point("North Node", 70), _point("South Node", 250)]
    asc, mc = _lon("Jupiter"), _lon("Mars")
    return types.SimpleNamespace(
        id=f"no-time-{time_unknown}", planets=planets, timezone=TZ, time_unknown=time_unknown,
        houses=[{"number": i + 1, "sign": _SIGNS[int(((asc + 30 * i) % 360) // 30)], "degree": (asc + 30 * i) % 360}
                for i in range(12)],
        aspects=[{"planet1": "Moon", "planet2": "Sun", "aspect_type": "trine", "orb": 1.0},
                 {"planet1": "Ascendant", "planet2": "Sun", "aspect_type": "square", "orb": 0.5},
                 {"planet1": "Sun", "planet2": "Venus", "aspect_type": "trine", "orb": 2.0}],
        ascendant={"longitude": asc, "sign": _SIGNS[int(asc // 30)], "degree": asc % 30},
        midheaven={"longitude": mc, "sign": _SIGNS[int(mc // 30)], "degree": mc % 30},
    )


@pytest.fixture(autouse=True)
def _clean_feed_cache():
    feed_cache.clear()
    yield
    feed_cache.clear()


def _feed_natals(chart) -> tuple[set, set]:
    from backend.feed.builder import build_feed
    ev = build_feed(chart=chart, from_date=D0 - timedelta(days=40), to_date=D0 + timedelta(days=40),
                    today=D0, tier="premium")["events"]
    return ({e["meta"]["natal_planet"] for e in ev if e["kind"] == "transit"},
            {e["kind"] for e in ev if e["kind"].startswith("planner_")})


def _push_natals(chart) -> tuple[set, set]:
    from backend.push import cron
    natals, kinds = set(), set()
    for d in [D0 + timedelta(days=i) for i in range(-60, 60)]:
        for c in (cron._four_degree_candidates(chart, d, "/p") + cron._triple_touch_candidates(chart, d, "/p")
                  + cron._transit_entry_candidates(chart, d, "/p")):
            kinds.add(c["kind"])
            parts = c["ref"].split(":")
            natals.update(p for p in parts if p in HIDDEN)
    return natals, kinds


def test_known_time_is_seen():
    """Контроль: с известным временем Луна, углы и дома в разделах есть."""
    from backend import day_event
    natals, planner = _feed_natals(_chart(False))
    assert "Moon" in natals and planner
    assert {"Ascendant", "Midheaven"} <= {p["name"] for p in day_event._targets(_chart(False))}
    push_natals, kinds = _push_natals(_chart(False))
    assert "Moon" in push_natals or "cusp_approach" in kinds
    from backend.chart_points import planets
    from backend.pdf_reports import sections as S
    assert "Moon" in {t["natal"] for t in S.main_transits(planets(_chart(False)), D0, 12, 20)}


def test_feed_without_moon_and_houses():
    natals, planner = _feed_natals(_chart(True))
    assert not natals & HIDDEN, natals
    assert not planner


def test_main_event_and_forecast_without_hidden_points():
    from backend import day_event
    from backend.forecast.facts import compute_day
    chart = _chart(True)
    assert not {p["name"] for p in day_event._targets(chart)} & HIDDEN
    for d in DAYS:
        ev = day_event.main_event(chart, d, TZ, "08:00", "22:00")
        assert not (ev and ev.natal in HIDDEN), ev
        f = compute_day(chart, d, ZoneInfo(TZ))
        assert not f.houses and all(a["natal"] not in HIDDEN for a in f.aspects)


def test_chat_without_hidden_points():
    from backend.interpretation.rag import build_chart_summary, build_transits_block, chat_chart_data
    c = _chart(True)
    data = chat_chart_data({k: getattr(c, k) for k in ("planets", "houses", "aspects", "ascendant", "midheaven")}, True)
    assert not {p["name"] for p in data["planets"]} & HIDDEN
    assert not data["houses"] and not data["ascendant"] and not data["midheaven"]
    assert all(a["planet1"] not in HIDDEN and a["planet2"] not in HIDDEN for a in data["aspects"])
    text = build_chart_summary(data, True) + build_transits_block(data, 5, D0, c.id, TZ)
    assert "Натальная планета: Луна" not in text and "Луна:" not in text
    assert "дом " not in text.replace("домах", "").replace("домов", "")


def test_pushes_without_moon_angles_and_houses():
    from backend.chart_points import cusps
    natals, kinds = _push_natals(_chart(True))
    assert not natals, natals
    assert "cusp_approach" not in kinds          # «Новая сфера» — по полуденным домам
    assert cusps(_chart(True)) is None           # пуши планера без домов не считаются


def test_pdf_without_longterm_moon_and_angles():
    from backend.chart_points import planets
    from backend.pdf_reports import sections as S
    c = _chart(True)
    assert S.longterm_section(c, D0, TZ) == []
    assert all(a["planet1"] not in HIDDEN and a["planet2"] not in HIDDEN
               for a in S.top_aspects(c.aspects, 10, True))
    assert all(t["natal"] not in HIDDEN for t in S.main_transits(planets(c), D0, 12, 20))
    assert not {p["name"] for p in planets(c)} & HIDDEN


def test_interpretation_prompt_without_houses_and_angles():
    from backend.interpretation.prompts import _compact_profile
    c = _chart(True)
    prof = _compact_profile({"planets": c.planets, "houses": c.houses, "aspects": c.aspects,
                             "ascendant": c.ascendant, "midheaven": c.midheaven, "time_unknown": True})
    assert "houses" not in prof and "ascendant" not in prof and "midheaven" not in prof
    assert all("house" not in p for p in prof["planets"])
    assert all("Ascendant" not in a["planets"] for a in prof["aspects"])


def test_share_page_without_moon_and_ascendant(client, db, monkeypatch):
    from backend.tests.test_share_page import _async_return, _make_shared_chart
    seen = {}

    def quote(token, sun, moon, asc):
        seen.update(moon=moon, asc=asc)
        return _async_return("")
    monkeypatch.setattr("backend.share_router._get_share_quote", quote)
    chart = _make_shared_chart(db)
    chart.time_unknown = True
    chart.planets = chart.planets + [_point("Moon", 10)]
    db.commit()
    html = client.get(f"/share/{chart.public_token}").text
    assert "Луна:" not in html and "Асцендент" not in html
    assert seen == {"moon": "", "asc": ""}
