"""Лента из ядра (задание 4.4, флаг sky_event). Карта вымышленная, как в
test_sky.py. У каждого теста свой id карты: чанки `sky:v1` и `feed:v4-sky`
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
