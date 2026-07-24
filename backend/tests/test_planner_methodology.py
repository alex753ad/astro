"""tests/test_planner_methodology.py — планер не должен придумывать текст.

Единственный источник lead/theme/items — backend/transit/methodology.json.
Тест проходит по ВСЕМ планетам и ВСЕМ 12 домам и построчно сверяет то, что
отдают _planet_lead/_planet_theme/_planet_items/_moon_items, с файлом —
без урезаний, дополнений и склеек. Любая строка, которой нет в файле
(или несовпадение списка items), — провал теста.

Запуск: pytest backend/tests/test_planner_methodology.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.transit.planner_engine import (
    METHODOLOGY,
    _KEY_TO_ENG,
    _moon_items,
    _planet_items,
    _planet_lead,
    _planet_theme,
)

METHODOLOGY_PATH = Path(__file__).resolve().parents[1] / "transit" / "methodology.json"


def _load_source() -> dict:
    with open(METHODOLOGY_PATH, encoding="utf-8") as f:
        return json.load(f)


ALL_HOUSES = list(range(1, 13))
ALL_PLANETS_ENG = ["Moon", *sorted(_KEY_TO_ENG.values())]


def test_loaded_methodology_matches_file_verbatim():
    """Модульный кэш METHODOLOGY не должен расходиться с файлом на диске."""
    assert METHODOLOGY == _load_source()


@pytest.mark.parametrize("planet_eng", ALL_PLANETS_ENG)
def test_lead_matches_file(planet_eng):
    source = _load_source()
    expected = source.get(planet_eng, {}).get("meta", {}).get("lead", "")
    actual = _planet_lead(planet_eng)
    assert actual == expected, f"{planet_eng}: lead разошёлся с файлом"


@pytest.mark.parametrize("planet_eng", ALL_PLANETS_ENG)
@pytest.mark.parametrize("house", ALL_HOUSES)
def test_theme_matches_file(planet_eng, house):
    source = _load_source()
    expected = source.get(planet_eng, {}).get("houses", {}).get(str(house), {}).get("theme", "")
    actual = _planet_theme(planet_eng, house)
    assert actual == expected, f"{planet_eng}/{house}: theme разошёлся с файлом"


@pytest.mark.parametrize("planet_eng", ALL_PLANETS_ENG)
@pytest.mark.parametrize("house", ALL_HOUSES)
def test_items_match_file_exactly(planet_eng, house):
    """Список items должен совпадать поэлементно и по количеству — не подмножество, а равенство."""
    source = _load_source()
    expected = source.get(planet_eng, {}).get("houses", {}).get(str(house), {}).get("items", [])
    if planet_eng == "Moon":
        actual = _moon_items(house)
    else:
        actual = _planet_items(planet_eng, house)
    assert actual == expected, f"{planet_eng}/{house}: items разошлись с файлом (ничего не добавлять/убирать)"


def test_no_forbidden_dicts_imported_by_planner_engine():
    """planner_engine.py не должен тащить старые словари/AI-промпты — только methodology.json."""
    import backend.transit.planner_engine as pe

    forbidden_names = ("PLANET_HOUSE_MEANINGS", "MOON_HOUSE_ACTIONS", "PLANET_SUBTITLES")
    for name in forbidden_names:
        assert not hasattr(pe, name), f"planner_engine.py не должен иметь {name} в своём пространстве имён"
