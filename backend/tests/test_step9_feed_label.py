"""Шаг 9.4: ярлык транзита в ленте под sky_event — «Сатурн и Венера:
напряжение», к своей точке — «Сатурн и твой Сатурн: напряжение». Без флага —
прежний «Уран Соединение Меркурий». Веб — та же подпись (TransitTimeline.jsx,
transitLabel; держит TransitTimeline.label.test.js)."""
import re
from datetime import date

import pytest
import pytz

from backend import flags
from backend.feed.builder import TEMPLATES, transit_cards, transit_text
from backend.models import FeatureFlag
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура


@pytest.mark.parametrize("args, label", [
    (("Saturn", "Venus", "square"), "Сатурн и Венера: напряжение"),
    (("Jupiter", "Sun", "trine"), "Юпитер и Солнце: гармония"),
    (("Mars", "Midheaven", "conjunction"), "Марс и Середина неба: соединение"),
    (("Saturn", "Saturn", "opposition"), "Сатурн и твой Сатурн: напряжение"),
    (("Sun", "Sun", "sextile"), "Солнце и твоё Солнце: гармония"),
    (("Venus", "Venus", "square"), "Венера и твоя Венера: напряжение"),
])
def test_label_under_flag(args, label):
    assert transit_text(*args, sky=True) == label


def test_label_without_flag_unchanged():
    assert transit_text("Uranus", "Mercury", "conjunction") == "Уран Соединение Меркурий"


def test_every_planet_has_own_label():
    """Каждая транзитная планета может прийти к своей же точке."""
    assert set(TEMPLATES["transit_planets"]) <= set(TEMPLATES["own_natal"])


@pytest.mark.parametrize("on", [False, True])
def test_feed_cards_real_path(db, user_free, chart, on):  # noqa: F811
    """transit_cards с флагом по ORM-карте (sky=None → day_event._sky_on)."""
    flags.reset_cache()
    if on:
        db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user_free.id]))
        db.commit()
    flags.reset_cache()
    try:
        cards = transit_cards(chart, date(2026, 10, 1), date(2026, 10, 31),
                              pytz.timezone("Europe/Moscow"), "pro")
    finally:
        flags.reset_cache()
    texts = [c["text"] for c in cards if c.get("text")]
    assert texts
    new = re.compile(r"^\S+ и .+: (соединение|гармония|напряжение)$")
    for t in texts:
        if " на оси узлов" in t:
            continue
        assert bool(new.match(t)) is on, t
