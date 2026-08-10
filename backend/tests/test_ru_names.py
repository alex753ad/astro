"""Тесты на полноту русского словаря планет/аспектов.

Раньше PLANET_RU/NATAL_RU были продублированы по нескольким файлам и каждая
копия покрывала только часть точек — из-за этого узлы (North Node/South Node)
и местами Плутон оставались непереведёнными в письмах и пушах (латиница
"North Node" вместо "Сев. Узел"). backend/ephemeris/ru_names.py — теперь
единственный источник; этот тест проверяет, что он покрывает всё, что может
реально прийти как transit_planet/natal_planet из calculate_transits.
"""

from backend.ephemeris.calculator import PLANETS
from backend.ephemeris.aspects import ASPECTS
from backend.ephemeris.ru_names import PLANET_RU, ASPECT_RU

# calculate_planets() дополнительно синтезирует South Node как точку,
# противоположную North Node (см. backend/ephemeris/calculator.py) — её нет
# в PLANETS, но она попадает в natal_planet точно так же, как остальные точки.
ALL_POINT_NAMES = set(PLANETS.keys()) | {"South Node"}


def test_all_calculated_points_have_translation():
    for name in ALL_POINT_NAMES:
        assert name in PLANET_RU, f"{name} отсутствует в PLANET_RU"
        assert PLANET_RU[name] != name, f"{name} не переведён (латиница как есть)"


def test_all_aspect_types_have_translation():
    for aspect in ASPECTS:
        assert aspect in ASPECT_RU, f"{aspect} отсутствует в ASPECT_RU"
        assert ASPECT_RU[aspect] != aspect, f"{aspect} не переведён (латиница как есть)"
