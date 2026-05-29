"""Aspect calculation between planets.

Supports: conjunction, sextile, square, trine, opposition.
Uses standard orbs differentiated by planet (luminaries get wider orbs).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.ephemeris.calculator import PlanetResult


PERSONAL_PLANETS = {"Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant", "Midheaven"}
CORE_PLANETS     = {"Sun", "Moon", "Ascendant", "Midheaven"}


def calculate_importance(planet1: str, planet2: str, orb: float) -> str:
    """F4: Classify aspect importance as high / medium / low."""
    planets = {planet1, planet2}
    if orb < 2 and bool(planets & CORE_PLANETS):
        return "high"
    if orb < 5 and bool(planets & PERSONAL_PLANETS):
        return "medium"
    return "low"


@dataclass
class AspectResult:
    planet1: str
    planet2: str
    aspect_type: str
    angle: float        # exact angle between planets
    orb: float          # deviation from exact aspect
    applying: bool      # True if orb is decreasing
    importance: str = "low"  # high / medium / low


# ── Aspect definitions ──
ASPECTS = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "opposition": 180.0,
}

# Standard orbs — luminaries (Sun, Moon) get wider orbs
LUMINARIES = {"Sun", "Moon"}

DEFAULT_ORBS = {
    "conjunction": 8.0,
    "sextile": 5.0,
    "square": 7.0,
    "trine": 7.0,
    "opposition": 8.0,
}

LUMINARY_ORBS = {
    "conjunction": 10.0,
    "sextile": 6.0,
    "square": 8.0,
    "trine": 8.0,
    "opposition": 10.0,
}


def _get_orb(planet1: str, planet2: str, aspect_type: str) -> float:
    """Get the allowed orb for an aspect between two planets."""
    if planet1 in LUMINARIES or planet2 in LUMINARIES:
        return LUMINARY_ORBS[aspect_type]
    return DEFAULT_ORBS[aspect_type]


def _angular_distance(lon1: float, lon2: float) -> float:
    """Calculate the shortest angular distance between two longitudes."""
    diff = abs(lon1 - lon2) % 360
    return min(diff, 360 - diff)


def _is_applying(planet1: PlanetResult, planet2: PlanetResult, angle: float) -> bool:
    """Determine if an aspect is applying (getting closer) or separating."""
    # Calculate future positions (rough: use speed)
    future_lon1 = (planet1.longitude + planet1.speed) % 360
    future_lon2 = (planet2.longitude + planet2.speed) % 360
    future_dist = _angular_distance(future_lon1, future_lon2)

    current_dist = angle
    return future_dist < current_dist


def calculate_aspects(planets: list[PlanetResult]) -> list[AspectResult]:
    """Calculate all aspects between planets.

    Iterates over all unique planet pairs and checks each aspect type.
    """
    results: list[AspectResult] = []

    for i in range(len(planets)):
        for j in range(i + 1, len(planets)):
            p1, p2 = planets[i], planets[j]
            angle = _angular_distance(p1.longitude, p2.longitude)

            for aspect_name, exact_angle in ASPECTS.items():
                max_orb = _get_orb(p1.name, p2.name, aspect_name)
                orb = abs(angle - exact_angle)

                if orb <= max_orb:
                    applying   = _is_applying(p1, p2, angle)
                    orb_rounded = round(orb, 4)
                    results.append(AspectResult(
                        planet1=p1.name,
                        planet2=p2.name,
                        aspect_type=aspect_name,
                        angle=round(angle, 4),
                        orb=orb_rounded,
                        applying=applying,
                        importance=calculate_importance(p1.name, p2.name, orb_rounded),
                    ))

    # Sort by orb (tightest aspects first)
    results.sort(key=lambda a: a.orb)
    return results
