"""Лента из ядра (задание 4.4, флаг sky_event). Карта вымышленная, как в
test_sky.py. У каждого теста свой id карты: чанки `sky:v1` и `feed:v5-sky`
кэшируются по id, без набора точек в ключе."""
import types
from datetime import date

import pytz

from backend.feed import builder
from backend.tests.test_sky import CHART

TZ = pytz.timezone("Europe/Moscow")


def _chart(cid, **kw):
    return types.SimpleNamespace(**{**CHART, "id": cid, "time_unknown": False, **kw})


def _cards(chart, d0, d1, sky=True):
    return builder.transit_cards(chart, d0, d1, TZ, "premium", sky)


def _of(cards, transit, natal, aspect):
    return [c for c in cards if (c["meta"]["transit_planet"], c["meta"]["natal_planet"],
                                 c["meta"]["aspect_type"]) == (transit, natal, aspect)]


def test_pluto_station_at_saturn_has_no_card():
    """18.10.2027 Плутон разворачивается в 1,6° от Сатурна — касания нет (О3)."""
    cards = _cards(_chart("test-sky-feed-station"), date(2027, 10, 1), date(2027, 11, 1))
    assert cards
    assert not _of(cards, "Pluto", "Saturn", "conjunction")


def test_loop_card_per_touch_in_order():
    """Петля Меркурия к Плутону: три касания — три карточки, touch_n 1, 2, 3;
    срок события и все касания — в meta, верхний ends_at — null."""
    cards = _of(_cards(_chart("test-sky-feed-loop"), date(2026, 10, 15), date(2026, 12, 5)),
                "Mercury", "Pluto", "conjunction")
    assert [c["meta"]["touch_n"] for c in cards] == [1, 2, 3]
    assert [c["at"][:10] for c in cards] == ["2026-10-21", "2026-10-27", "2026-11-29"]
    assert [c["meta"]["peak_date"] for c in cards] == ["2026-10-21", "2026-10-27", "2026-11-29"]
    assert len({c["key"] for c in cards}) == 3
    for c in cards:
        m = c["meta"]
        assert c["ends_at"] is None
        assert m["starts_at"].startswith("2026-10-17") and m["ends_at"].startswith("2026-12-01")
        assert [t[:10] for t in m["touches"]] == ["2026-10-21", "2026-10-27", "2026-11-29"]


def test_no_birth_time_no_moon_asc_mc():
    cards = _cards(_chart("test-sky-feed-notime", time_unknown=True), date(2026, 10, 1), date(2026, 10, 31))
    assert cards
    assert not {c["meta"]["natal_planet"] for c in cards} & {"Moon", "Ascendant", "Midheaven"}


def test_without_flag_meta_unchanged():
    """Без флага — старый движок: полей срока в meta нет."""
    cards = _cards(_chart("test-sky-feed-off"), date(2026, 10, 15), date(2026, 10, 31), sky=False)
    assert cards and not any("touch_n" in c["meta"] for c in cards)


# ── Подпись срока в приложении (4.13): строки дословно — таблица владельца 06.10.2026 ──
def _term(start, end, passes, touches):
    iso = lambda d: f"{d}T12:00:00+00:00"
    return builder._term_meta({
        "starts_at": iso(start), "ends_at": iso(end), "touches": [iso(t) for t in touches],
        "passes": [[iso(a), iso(b)] for a, b in passes],
    }, TZ)


def test_term_plain():
    m = _term("2027-04-06", "2027-04-30", [("2027-04-06", "2027-04-30")], ["2027-04-17"])
    assert m["period_line"] == "Период влияния: 6 апреля — 30 апреля 2027"
    assert m["touches_line"] == "Точный аспект: 17 апреля 2027"
    assert m["gaps"] == []


def test_term_loop_one_gap():
    m = _term("2026-10-17", "2026-12-01", [("2026-10-17", "2026-10-30"), ("2026-11-28", "2026-12-01")],
              ["2026-10-21", "2026-10-27", "2026-11-29"])
    assert m["period_line"] == "Период влияния: 17 октября — 1 декабря 2026, с перерывом с 30 октября по 28 ноября"
    assert m["touches_line"] == "Точные касания: 21 октября, 27 октября и 29 ноября 2026"
    assert m["gaps"] == [("2026-10-30", "2026-11-28")]


def test_term_loop_several_gaps():
    m = _term("2027-03-03", "2027-12-20",
              [("2027-03-03", "2027-04-01"), ("2027-06-10", "2027-08-05"), ("2027-10-02", "2027-12-20")],
              ["2027-03-20", "2027-07-01", "2027-11-11"])
    assert m["period_line"] == ("Период влияния: 3 марта — 20 декабря 2027, "
                                "с перерывами с 1 апреля по 10 июня и с 5 августа по 2 октября")


def test_term_across_new_year():
    m = _term("2026-11-01", "2027-07-18", [("2026-11-01", "2027-01-24"), ("2027-06-26", "2027-07-18")],
              ["2026-11-22", "2027-01-02", "2027-07-07"])
    assert m["period_line"] == "Период влияния: 1 ноября 2026 — 18 июля 2027, с перерывом с 24 января по 26 июня"


def test_term_gap_across_new_year():
    m = _term("2026-11-01", "2027-07-18", [("2026-11-01", "2026-12-24"), ("2027-06-26", "2027-07-18")],
              ["2026-11-22", "2027-07-07"])
    assert m["period_line"] == ("Период влияния: 1 ноября 2026 — 18 июля 2027, "
                                "с перерывом с 24 декабря 2026 по 26 июня")


def test_term_in_feed_meta_only_under_flag():
    chart = _chart("test-sky-feed-term")
    cards = _of(_cards(chart, date(2026, 10, 15), date(2026, 12, 5)), "Mercury", "Pluto", "conjunction")
    m = cards[0]["meta"]
    assert m["touches_line"] == "Точные касания: 21 октября, 27 октября и 29 ноября 2026"
    assert m["period_line"].startswith("Период влияния: 17 октября — 1 декабря 2026, с перерывом с ")
    off = _cards(_chart("test-sky-feed-term-off"), date(2026, 10, 15), date(2026, 12, 5), sky=False)
    assert off and not any("period_line" in c["meta"] for c in off)
