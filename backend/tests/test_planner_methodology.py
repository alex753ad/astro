"""tests/test_planner_methodology.py — планер не должен придумывать текст.

Единственный источник lead/theme/subtitle/notes/groups — methodology.json
(структура: theme, опционально subtitle+notes у Урана/Нептуна/Плутона, groups[]
из {heading, items[]}). Тест проходит по ВСЕМ планетам и ВСЕМ 12 домам и
сверяет то, что отдают _planet_lead/_unlocked_payload/_locked_payload, с
файлом — точным равенством словаря (ключ в ключ, строка в строку), без
урезаний, дополнений и склеек. Любая лишняя или недостающая строка/ключ —
провал теста.

Запуск: pytest backend/tests/test_planner_methodology.py -v
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.transit.planner_engine import (
    METHODOLOGY,
    _KEY_TO_ENG,
    _locked_payload,
    _planet_lead,
    _unlocked_payload,
    build_planner,
)

METHODOLOGY_PATH = Path(__file__).resolve().parents[1] / "transit" / "methodology.json"


def _load_source() -> dict:
    with open(METHODOLOGY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _expected_payload(source: dict, planet_eng: str, house: int) -> dict:
    """То, что ДОЛЖНО прийти с бэка для этого дома — построено напрямую из файла."""
    entry = source.get(planet_eng, {}).get("houses", {}).get(str(house), {})
    payload = {
        "theme": entry.get("theme", ""),
        "groups": [
            {"heading": g.get("heading", ""), "items": list(g.get("items", []))}
            for g in entry.get("groups", [])
        ],
    }
    if "subtitle" in entry:
        payload["subtitle"] = entry["subtitle"]
    if "notes" in entry:
        payload["notes"] = list(entry["notes"])
    return payload


ALL_HOUSES = list(range(1, 13))
ALL_PLANETS_ENG = ["Moon", *sorted(_KEY_TO_ENG.values())]


def test_loaded_methodology_matches_file_verbatim():
    """Модульный кэш METHODOLOGY не должен расходиться с файлом на диске."""
    assert METHODOLOGY == _load_source()


@pytest.mark.parametrize("planet_eng", ALL_PLANETS_ENG)
def test_lead_matches_file(planet_eng):
    source = _load_source()
    expected = source.get(planet_eng, {}).get("meta", {}).get("lead", "")
    assert _planet_lead(planet_eng) == expected, f"{planet_eng}: lead разошёлся с файлом"


@pytest.mark.parametrize("planet_eng", ALL_PLANETS_ENG)
@pytest.mark.parametrize("house", ALL_HOUSES)
def test_unlocked_payload_matches_file_exactly(planet_eng, house):
    """theme/subtitle/notes/groups — точное совпадение с файлом, ключ в ключ.

    Словарное равенство ловит и лишний ключ (напр. subtitle там, где его нет
    в файле), и лишнюю/недостающую строку внутри groups/notes.
    """
    source = _load_source()
    expected = _expected_payload(source, planet_eng, house)
    actual = _unlocked_payload(planet_eng, house)
    assert actual == expected, f"{planet_eng}/{house}: payload разошёлся с файлом"


def test_locked_payload_leaks_nothing():
    assert _locked_payload() == {"theme": "", "groups": []}


def test_no_forbidden_dicts_imported_by_planner_engine():
    """planner_engine.py не должен тащить старые словари/AI-промпты — только methodology.json."""
    import backend.transit.planner_engine as pe

    forbidden_names = ("PLANET_HOUSE_MEANINGS", "MOON_HOUSE_ACTIONS", "PLANET_SUBTITLES")
    for name in forbidden_names:
        assert not hasattr(pe, name), f"planner_engine.py не должен иметь {name} в своём пространстве имён"


# ── Сквозной прогон build_planner на синтетической карте (реальная эфемерида) ──

_SYNTHETIC_NATAL = {
    "planets": [],
    "houses": [{"number": i + 1, "sign": "Овен", "degree": i * 30} for i in range(12)],
    "ascendant": {"sign": "Овен", "degree": 0},
    "midheaven": {"sign": "Козерог", "degree": 270},
}


@pytest.mark.parametrize("tier", ["free", "lite", "pro", "premium"])
def test_build_planner_end_to_end_matches_file(tier):
    """Полный ответ /planner/monthly — каждый period/longterm/week_day либо
    пуст (locked), либо дословно равен соответствующей записи файла."""
    source = _load_source()
    planner = build_planner(
        natal_profile=_SYNTHETIC_NATAL,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        today=date(2026, 7, 24),
        user_timezone="Europe/Moscow",
        tier=tier,
    )

    for sec in planner["month_sections"]:
        eng = _KEY_TO_ENG[sec["planet"]]
        for p in sec["periods"]:
            expected = _locked_payload() if p["locked"] else _expected_payload(source, eng, p["house"])
            actual = {k: p[k] for k in expected}
            assert actual == expected, f"{tier}/month/{sec['planet']}/{p['house']}: payload разошёлся"

    for lt in planner["longterm"]:
        eng = _KEY_TO_ENG[lt["planet"]]
        expected = _locked_payload() if lt["locked"] else _expected_payload(source, eng, lt["house"])
        actual = {k: lt[k] for k in expected}
        assert actual == expected, f"{tier}/longterm/{lt['planet']}: payload разошёлся"

    for wd in planner["week_days"]:
        locked = wd["locked"] or not wd["house"]
        expected = _locked_payload() if locked else _expected_payload(source, "Moon", wd["house"])
        actual = {k: wd[k] for k in expected}
        assert actual == expected, f"{tier}/week/house={wd['house']}: payload разошёлся"
