"""Межкарточные аспекты синастрии.

`calculate_aspects()` из aspects.py перебирает уникальные пары ВНУТРИ одного
списка планет и потому для синастрии не подходит: там нужна полная решётка
«каждая планета первой карты × каждая планета второй», включая пары одного
имени (Солнце одного к Солнцу другого) и обе комбинации разных планет
(Венера А — Марс Б и Марс А — Венера Б это разные связи).

Орбы и определения аспектов переиспользуются из aspects.py, чтобы сетка
синастрии оставалась согласованной с натальной.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.ephemeris.aspects import (
    ASPECTS,
    AspectResult,
    _angular_distance,
    _get_orb,
)
from backend.ephemeris.calculator import PlanetResult

# Значимость связи: светила и «личные» планеты весомее для совместимости.
_PERSONAL = {"Sun", "Moon", "Venus", "Mars", "Ascendant"}
_HIGH_ASPECTS = {"conjunction", "opposition", "square"}


def _importance(planet1: str, planet2: str, aspect_type: str) -> str:
    both_personal = planet1 in _PERSONAL and planet2 in _PERSONAL
    if both_personal and aspect_type in _HIGH_ASPECTS:
        return "high"
    if both_personal or aspect_type in _HIGH_ASPECTS:
        return "medium"
    return "low"


def calculate_synastry_aspects(
    planets1: list[PlanetResult],
    planets2: list[PlanetResult],
) -> list[AspectResult]:
    """Аспекты между планетами двух карт.

    В `AspectResult.planet1` — планета первой карты, в `planet2` — второй.
    Поле `applying` здесь смысла не имеет (карты неподвижны друг относительно
    друга) и всегда False.
    """
    results: list[AspectResult] = []

    for p1 in planets1:
        for p2 in planets2:
            angle = _angular_distance(p1.longitude, p2.longitude)

            for aspect_name, exact_angle in ASPECTS.items():
                orb = abs(angle - exact_angle)
                if orb <= _get_orb(p1.name, p2.name, aspect_name):
                    results.append(
                        AspectResult(
                            planet1=p1.name,
                            planet2=p2.name,
                            aspect_type=aspect_name,
                            angle=round(angle, 2),
                            orb=round(orb, 2),
                            applying=False,
                            importance=_importance(p1.name, p2.name, aspect_name),
                        )
                    )
                    break  # один аспект на пару — ближайший по определению орбов

    # Сначала самые точные и значимые связи.
    _rank = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda a: (_rank.get(a.importance, 3), a.orb))
    return results
