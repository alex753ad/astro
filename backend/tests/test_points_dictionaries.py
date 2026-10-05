"""Полнота словарей по набору точек (шаг 5 аудита, задание владельца 05.10.2026).

Набор натальных точек один — `day_event.POINT_NAMES` (Солнце–Плутон, ASC, MC,
Сев. узел). Каждая точка обязана иметь строку во всех словарях, через которые
событие идёт к человеку: пуш, виджет, сторис, письмо «Важный транзит», PDF,
лента, прогноз дня. Пропуск — это KeyError в проде в день, когда главным
впервые станет такое событие, поэтому проверяется перебором, а не примером.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend import day_event as de
from backend import story_card
from backend.ephemeris.aspects import ASPECTS
from backend.feed.builder import transit_text
from backend.forecast.meanings import sphere_of
from backend.pdf_reports.sections import _SLOW, transit_title
from backend.push.cron import _sphere_short
from backend.transit.engine import (
    ALERT_PLANETS, NATAL_SPHERE, _build_transit_alert_description, _build_transit_alert_subject,
)

AT = datetime(2026, 10, 8, 14, 5, tzinfo=ZoneInfo("Europe/Moscow"))
PAIRS = [(tp, np_, asp) for tp in de.WEIGHT_TRANSIT for np_ in de.POINT_NAMES
         for asp in ASPECTS if de.counts(np_, asp)]


def test_point_names_are_the_decided_set():
    assert set(de.POINT_NAMES) == {*de.NATAL_PLANETS, "Ascendant", "Midheaven", "North Node"}
    assert "South Node" not in de.POINT_NAMES


@pytest.mark.parametrize("tp, np_, asp", PAIRS)
def test_day_event_texts(tp, np_, asp):
    """Пуш, виджет, «Неделя вперёд», возврат, сторис — без KeyError."""
    ev = de.DayEvent(key="k", at_local=AT, transit=tp, natal=np_, aspect=asp,
                     score=de.score(tp, np_, asp), timed=True)
    assert de.title(ev) and de.short(ev) and de.return_title(ev)
    assert 0 < len(de.advice(ev)) <= 60
    assert story_card.phrase(ev, "new_moon")
    story_card.event_label(ev)   # None у ASC/MC — нормально, KeyError — нет


@pytest.mark.parametrize("tp", sorted(ALERT_PLANETS))
@pytest.mark.parametrize("np_", de.POINT_NAMES)
def test_alert_sphere_for_every_pair(tp, np_):
    """«Важный транзит»: сфера у каждой пары; письмо — без «🌟» и без
    «катастрофы». (Запятая в первой части у старых сфер есть — пуш режет по
    ней намеренно, см. push/cron._sphere_short; новые строки 05.10.2026 —
    без неё.)"""
    assert _sphere_short(NATAL_SPHERE[(tp, np_)])
    for asp in ASPECTS:
        if not de.counts(np_, asp):
            continue
        subject = _build_transit_alert_subject(tp, np_, asp, "П")
        text = _build_transit_alert_description(tp, np_, asp, "П")
        assert "🌟" not in subject and "катастроф" not in text


@pytest.mark.parametrize("tp", _SLOW)
@pytest.mark.parametrize("np_", de.POINT_NAMES)
def test_pdf_titles(tp, np_):
    for asp in ASPECTS:
        if de.counts(np_, asp):
            assert transit_title(tp, np_, asp)


@pytest.mark.parametrize("np_", de.POINT_NAMES)
def test_feed_label_and_forecast_sphere(np_):
    assert transit_text("Mars", np_, "conjunction")
    assert sphere_of(np_, "conjunction")
    assert sphere_of(np_, "opposition")


def test_node_opposition_reads_as_south_node():
    assert sphere_of("North Node", "opposition") == sphere_of("South Node")
