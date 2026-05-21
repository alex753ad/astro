"""Core ephemeris calculator using pyswisseph (Swiss Ephemeris).

Computes planet positions, ascendant, midheaven for a given UTC datetime
and geographic coordinates. Accuracy: < 1 arc-second.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Optional

import swisseph as swe

from backend.config import get_settings

# ── Initialize Swiss Ephemeris path ──
_settings = get_settings()
_ephe_path = os.path.abspath(_settings.ephe_path)
if os.path.isdir(_ephe_path):
    swe.set_ephe_path(_ephe_path)

# ── Planet constants ──
PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Uranus": swe.URANUS,
    "Neptune": swe.NEPTUNE,
    "Pluto": swe.PLUTO,
    "North Node": swe.MEAN_NODE,
}

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# House system codes for pyswisseph
HOUSE_SYSTEMS = {
    "placidus": b"P",
    "koch": b"K",
    "equal": b"E",
    "whole_sign": b"W",
}


@dataclass
class PlanetResult:
    name: str
    longitude: float       # 0–360
    latitude: float
    distance: float
    speed: float
    sign: str
    degree_in_sign: float
    retrograde: bool


@dataclass
class HouseResult:
    number: int
    sign: str
    degree: float          # cusp longitude 0–360


@dataclass
class PointResult:
    sign: str
    degree: float
    longitude: float


@dataclass
class FullChart:
    planets: list[PlanetResult]
    houses: list[HouseResult]
    ascendant: Optional[PointResult]
    midheaven: Optional[PointResult]
    warnings: list[str]


def _datetime_to_jd(dt: datetime) -> float:
    """Convert a UTC datetime to Julian Day number."""
    return swe.julday(
        dt.year, dt.month, dt.day,
        dt.hour + dt.minute / 60.0 + dt.second / 3600.0,
    )


def _longitude_to_sign(longitude: float) -> tuple[str, float]:
    """Convert ecliptic longitude (0–360) to zodiac sign and degree within sign."""
    sign_index = int(longitude / 30.0)
    degree_in_sign = longitude - sign_index * 30.0
    return ZODIAC_SIGNS[sign_index % 12], round(degree_in_sign, 4)


@lru_cache(maxsize=4096)
def _calc_planet_position(planet_id: int, jd: float) -> tuple:
    """Cached planet position calculation. Returns (lon, lat, dist, speed)."""
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    result, _ret_flags = swe.calc_ut(jd, planet_id, flags)
    # result = (longitude, latitude, distance, speed_lon, speed_lat, speed_dist)
    return (result[0], result[1], result[2], result[3])


def calculate_planets(utc_dt: datetime) -> list[PlanetResult]:
    """Calculate positions of all planets for a given UTC datetime."""
    jd = _datetime_to_jd(utc_dt)
    results = []

    for name, planet_id in PLANETS.items():
        lon, lat, dist, speed = _calc_planet_position(planet_id, jd)
        sign, deg = _longitude_to_sign(lon)
        results.append(PlanetResult(
            name=name,
            longitude=round(lon, 4),
            latitude=round(lat, 4),
            distance=round(dist, 6),
            speed=round(speed, 4),
            sign=sign,
            degree_in_sign=deg,
            retrograde=speed < 0,
        ))

    return results


def calculate_houses(
    utc_dt: datetime,
    latitude: float,
    longitude: float,
    system: str = "placidus",
) -> tuple[list[HouseResult], PointResult, PointResult, list[str]]:
    """Calculate house cusps, Ascendant, and Midheaven.

    Returns (houses, ascendant, midheaven, warnings).
    """
    warnings: list[str] = []
    jd = _datetime_to_jd(utc_dt)
    sys_code = HOUSE_SYSTEMS.get(system, b"P")

    # Polar latitudes warning — Placidus can be inaccurate
    if abs(latitude) > 66.0 and system == "placidus":
        warnings.append(
            "Placidus house system may be inaccurate for polar latitudes "
            f"(lat={latitude:.2f}°). Consider using Equal or Whole Sign houses."
        )

    try:
        cusps, ascmc = swe.houses(jd, latitude, longitude, sys_code)
    except swe.Error:
        # Placidus/Koch can fail at extreme latitudes — fall back to Equal
        warnings.append(
            f"House system '{system}' failed for latitude {latitude:.2f}°. "
            "Falling back to Equal house system."
        )
        cusps, ascmc = swe.houses(jd, latitude, longitude, b"E")
    # cusps: tuple of 12 house cusp longitudes
    # ascmc: (ASC, MC, ARMC, Vertex, Equatorial ASC, ...)

    houses = []
    for i in range(12):
        sign, deg = _longitude_to_sign(cusps[i])
        houses.append(HouseResult(
            number=i + 1,
            sign=sign,
            degree=round(cusps[i], 4),
        ))

    asc_sign, asc_deg = _longitude_to_sign(ascmc[0])
    ascendant = PointResult(sign=asc_sign, degree=asc_deg, longitude=round(ascmc[0], 4))

    mc_sign, mc_deg = _longitude_to_sign(ascmc[1])
    midheaven = PointResult(sign=mc_sign, degree=mc_deg, longitude=round(ascmc[1], 4))

    return houses, ascendant, midheaven, warnings


def assign_houses(planets: list[PlanetResult], houses: list[HouseResult]) -> list[PlanetResult]:
    """Assign each planet to its house based on cusp longitudes."""
    cusps = [h.degree for h in houses]

    for planet in planets:
        house_num = _find_house(planet.longitude, cusps)
        planet.house = house_num

    return planets


def _find_house(longitude: float, cusps: list[float]) -> int:
    """Determine which house a given longitude falls in.

    Normalises all cusps relative to cusp[0] so the comparison works
    correctly even when the sequence wraps around 0° Aries or when
    Placidus produces non-monotonic cusp sequences.
    """
    lon = longitude % 360
    asc = cusps[0] % 360

    # Shift longitude and all cusps so that cusp[0] = 0
    def _norm(x: float) -> float:
        return (x - asc) % 360

    lon_n = _norm(lon)

    for i in range(12):
        start_n = _norm(cusps[i])
        end_n   = _norm(cusps[(i + 1) % 12])

        # In the normalised frame the sector always runs start_n → end_n
        # with end_n > start_n (because we shifted by asc).
        # The only exception is the last house which wraps back to 360.
        if end_n == 0:
            end_n = 360
        if start_n < end_n:
            if start_n <= lon_n < end_n:
                return i + 1

    return 1  # fallback


def calculate_full_chart(
    utc_dt: datetime,
    latitude: float,
    longitude: float,
    house_system: str = "placidus",
    time_unknown: bool = False,
) -> FullChart:
    """Calculate complete natal chart: planets, houses, aspects.

    If time_unknown, houses/ASC/MC are computed but flagged as unreliable.
    """
    from backend.ephemeris.aspects import calculate_aspects

    warnings: list[str] = []

    planets = calculate_planets(utc_dt)
    houses, ascendant, midheaven, house_warnings = calculate_houses(
        utc_dt, latitude, longitude, house_system
    )
    warnings.extend(house_warnings)

    if time_unknown:
        warnings.append(
            "Birth time is unknown. Houses, Ascendant, and Midheaven are calculated "
            "for 12:00 noon and may be significantly inaccurate."
        )
        # Still assign houses but they're flagged
        planets = assign_houses(planets, houses)
    else:
        planets = assign_houses(planets, houses)

    aspects = calculate_aspects(planets)

    return FullChart(
        planets=planets,
        houses=houses,
        ascendant=ascendant,
        midheaven=midheaven,
        warnings=warnings,
    ), aspects
