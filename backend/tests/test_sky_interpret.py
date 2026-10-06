"""Разбор транзита из ядра (задание 4.5, флаг sky_event). Карта вымышленная,
как в test_sky.py."""
import types
from datetime import date

import pytest

from backend import flags
from backend.models import FeatureFlag, NatalChart
from backend.sky import find_event, interpret_facts
from backend.tests.test_sky import CHART

TZ = "Europe/Moscow"


def _ns(cid):
    return types.SimpleNamespace(**CHART, id=cid, time_unknown=False)


def test_saturn_trine_mc_facts_from_core():
    """Касание к MC: знак, градус и даты — из ядра; даты местные (вход
    21:57 UTC 5 апреля — уже 6 апреля в Москве)."""
    ev = find_event(_ns("test-sky-int-mc"), "Saturn", "Midheaven", "trine", date(2027, 4, 17))
    f = interpret_facts(ev, TZ, None)
    assert (f["transit_sign"], f["transit_degree"]) == ("Aries", 18.94)
    assert (f["natal_sign"], f["natal_degree"]) == ("Sagittarius", 18.94)
    assert f["exact_dates"] == ["2027-04-17"]
    assert (f["period_start"], f["period_end"]) == ("2027-04-06", "2027-04-30")


def test_mercury_loop_one_event_three_touches_gap():
    """Петля Меркурия к Плутону: карточка любого касания открывает одно
    событие — три касания и перерыв вне орба."""
    chart = _ns("test-sky-int-loop")
    evs = [find_event(chart, "Mercury", "Pluto", "conjunction", d)
           for d in (date(2026, 10, 21), date(2026, 10, 27), date(2026, 11, 29))]
    assert len({e.key for e in evs}) == 1
    f = interpret_facts(evs[0], TZ, None)
    assert f["exact_dates"] == ["2026-10-21", "2026-10-27", "2026-11-29"]
    assert f["gaps"] == [("2026-10-30", "2026-11-28")]
    assert (f["period_start"], f["period_end"]) == ("2026-10-17", "2026-12-01")


def test_venus_trine_asc_late_touch_gets_whole_period():
    """Карточка последнего касания петли (27.11.26) — период всего события,
    с 3 сентября, а не только последнего прохода (как было у
    compute_exact_facts)."""
    ev = find_event(_ns("test-sky-int-asc"), "Venus", "Ascendant", "trine", date(2026, 11, 27))
    f = interpret_facts(ev, TZ, None)
    assert f["period_start"] == "2026-09-03"
    assert f["exact_dates"] == ["2026-09-05", "2026-10-31", "2026-11-27"]


# ── Ручка: один разбор на событие (О5) ───────────────────────────────────────

class _Engine:
    name = "fake"

    def __init__(self):
        self.prompts = []

    async def stream(self, request):
        self.prompts.append(request.custom_prompt)
        yield "Разбор."


class _Router:
    def __init__(self):
        self.engine = _Engine()
        self._engines = [self.engine]

    def _check_budget(self, name):
        return True

    def _track_spend(self, name, tokens):
        pass


@pytest.fixture
def router(monkeypatch):
    from backend.cache import transit_interp_cache
    r = _Router()
    monkeypatch.setattr("backend.interpretation.router.get_router", lambda: r)
    transit_interp_cache.clear()
    flags.reset_cache()
    yield r
    transit_interp_cache.clear()
    flags.reset_cache()


def _angle(name):
    a = CHART[name]
    return {**a, "degree": a["longitude"] % 30}   # как в сохранённой карте


def test_loop_cards_open_one_interpretation(client, db, user_free, auth_headers_free, router):
    from backend.auth.rate_limits import get_monthly_usage
    user_free.tier = "lite"
    chart = NatalChart(user_id=user_free.id, birth_date="1991-03-08", birth_time="06:40",
                       birth_place="Moscow", latitude=55.75, longitude=37.62, timezone=TZ,
                       planets=CHART["planets"], ascendant=_angle("ascendant"),
                       midheaven=_angle("midheaven"), houses=[], aspects=[])
    db.add(chart)
    db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user_free.id]))
    db.commit()
    for d in ("2026-10-21", "2026-10-27", "2026-11-29"):
        r = client.post(f"/api/v1/chart/{chart.id}/transits/event/interpret", headers=auth_headers_free,
                        json={"transit_planet": "Mercury", "natal_planet": "Pluto",
                              "aspect_type": "conjunction", "peak_date": d})
        assert r.status_code == 200
        r.read()
    assert len(router.engine.prompts) == 1
    db.expire_all()
    assert get_monthly_usage(db, str(user_free.id), "transit_ai") == 1
    prompt = router.engine.prompts[0]
    assert "Точные касания: 21 октября, 27 октября и 29 ноября 2026" in prompt
    assert "Период влияния: 17 октября — 1 декабря 2026, с перерывом с 30 октября по 28 ноября" in prompt
    assert "орб" not in prompt.split("## ФАКТЫ")[1].split("## ПРАВИЛА")[0]


def test_facts_lines_year_at_last_date_of_each_year():
    """Год — у последней даты каждого года (решение владельца 06.10.2026)."""
    from backend.transit.prompts import _sky_date_lines
    lines = _sky_date_lines({
        "exact_dates": ["2026-11-22", "2027-01-02", "2027-07-07"],
        "period_start": "2026-11-01", "period_end": "2027-07-18",
        "gaps": [("2027-01-24", "2027-06-26")],
    })
    assert lines == ["Точные касания: 22 ноября 2026, 2 января и 7 июля 2027",
                     "Период влияния: 1 ноября 2026 — 18 июля 2027, с перерывом с 24 января по 26 июня"]
    one = _sky_date_lines({"exact_dates": ["2027-04-17"], "gaps": [],
                           "period_start": "2027-04-06", "period_end": "2027-04-30"})
    assert one == ["Точный аспект: 17 апреля 2027", "Период влияния: 6 апреля — 30 апреля 2027"]
