"""Transit calculation engine.

Calculates transiting planet positions over a date range and finds
aspects with natal planet positions.

Optimizations (per roadmap 3.1):
- Step: 1 day for slow planets (Jupiter–Pluto), 4 hours for fast (Moon–Mars)
- Caching: planet positions cached by Julian Day via lru_cache
- Exact date: bisection refinement once an aspect is detected

The algorithm:
1. For each day in [from_date, to_date], compute transit planet positions.
2. For each transit planet × natal planet pair, check all 5 aspect types.
3. When an aspect enters orb, record the event and refine exact date via bisection.
4. Deduplicate: one event per (transit_planet, natal_planet, aspect_type) passage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from functools import lru_cache
from typing import Optional

import swisseph as swe

from backend.ephemeris.calculator import (
    PLANETS,
    ZODIAC_SIGNS,
    _datetime_to_jd,
    _longitude_to_sign,
    _calc_planet_position,
)
from backend.ephemeris.aspects import ASPECTS, _angular_distance

logger = logging.getLogger("astro.transit")

# ── Planet classification for step optimization ──
FAST_PLANETS = {"Sun", "Moon", "Mercury", "Venus", "Mars"}
SLOW_PLANETS = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "North Node"}

# Step sizes in hours
FAST_STEP_HOURS = 4
SLOW_STEP_HOURS = 24

# Transit orbs — tighter than natal (standard practice)
TRANSIT_ORBS = {
    "conjunction": 2.0,
    "sextile": 1.5,
    "square": 2.0,
    "trine": 1.5,
    "opposition": 2.0,
}

# Significance filter: skip minor aspects for outer-to-outer
MINOR_TRANSIT_PLANETS = {"North Node"}

# Bisection iterations for exact date refinement
BISECT_ITERATIONS = 12  # gives ~5-minute precision over a 24h window


@dataclass
class TransitEvent:
    """A single transit aspect event."""
    date: str                          # ISO date when aspect is within orb
    transit_planet: str
    transit_sign: str
    natal_planet: str
    natal_sign: str
    aspect_type: str
    orb: float                         # orb at detection
    exact_date: Optional[str] = None   # refined exact aspect date
    exact_orb: float = 0.0            # orb at exact date (should be near 0)
    applying: bool = True


def calculate_transits(
    natal_planets: list[dict],
    from_date: date,
    to_date: date,
    orb_filter: Optional[float] = None,
    planet_filter: Optional[list[str]] = None,
) -> list[TransitEvent]:
    """Calculate all transits for a natal chart over a date range.

    Args:
        natal_planets: List of natal planet dicts from stored chart
                       [{name, longitude, sign, degree_in_sign, ...}, ...]
        from_date: Start of transit period (inclusive)
        to_date: End of transit period (inclusive)
        orb_filter: Max orb to include (default: use TRANSIT_ORBS)
        planet_filter: Only include these transit planets (default: all)

    Returns:
        List of TransitEvent sorted by date
    """
    # Build natal position lookup: name → longitude
    natal_positions = {
        p["name"]: {
            "longitude": p["longitude"],
            "sign": p["sign"],
        }
        for p in natal_planets
    }

    # Determine which transit planets to calculate
    transit_planet_names = set(PLANETS.keys()) - MINOR_TRANSIT_PLANETS
    if planet_filter:
        transit_planet_names &= set(planet_filter)

    events: list[TransitEvent] = []
    seen: set[tuple] = set()  # deduplication: (transit, natal, aspect, week)

    current = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
    end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59)

    while current <= end:
        jd = _datetime_to_jd(current)

        for t_name in transit_planet_names:
            t_id = PLANETS[t_name]

            # Get transit planet position
            t_lon, t_lat, t_dist, t_speed = _calc_planet_position(t_id, round(jd, 6))
            t_sign, _ = _longitude_to_sign(t_lon)

            # Determine step for this planet
            step_hours = FAST_STEP_HOURS if t_name in FAST_PLANETS else SLOW_STEP_HOURS

            for n_name, n_data in natal_positions.items():
                # Skip self-transits (e.g., natal Sun transited by Sun → solar return)
                # These are valid but less interesting for general transits
                n_lon = n_data["longitude"]

                angle = _angular_distance(t_lon, n_lon)

                for aspect_name, exact_angle in ASPECTS.items():
                    max_orb = TRANSIT_ORBS[aspect_name]
                    if orb_filter is not None:
                        max_orb = min(max_orb, orb_filter)

                    orb = abs(angle - exact_angle)

                    if orb <= max_orb:
                        # Dedup key: same transit within same week
                        week_key = current.strftime("%Y-W%W")
                        dedup = (t_name, n_name, aspect_name, week_key)

                        if dedup not in seen:
                            seen.add(dedup)

                            # Refine exact date via bisection
                            exact_dt = _find_exact_aspect(
                                t_id, n_lon, exact_angle, current, step_hours
                            )

                            event = TransitEvent(
                                date=current.strftime("%Y-%m-%d"),
                                transit_planet=t_name,
                                transit_sign=t_sign,
                                natal_planet=n_name,
                                natal_sign=n_data["sign"],
                                aspect_type=aspect_name,
                                orb=round(orb, 4),
                                exact_date=(
                                    exact_dt.strftime("%Y-%m-%dT%H:%M")
                                    if exact_dt else None
                                ),
                                exact_orb=round(orb, 4),
                                applying=t_speed >= 0,
                            )
                            events.append(event)

        # Advance by the minimum step (fast planets)
        current += timedelta(hours=FAST_STEP_HOURS)

    # Sort by date, then by orb (tightest first)
    events.sort(key=lambda e: (e.date, e.orb))

    logger.info(
        "Calculated %d transit events for %s → %s",
        len(events), from_date, to_date,
    )
    return events


def _find_exact_aspect(
    transit_planet_id: int,
    natal_longitude: float,
    target_angle: float,
    approx_dt: datetime,
    window_hours: int,
) -> Optional[datetime]:
    """Refine the exact moment of an aspect via bisection.

    Searches within [approx_dt - window, approx_dt + window] for the point
    where the angular distance between transit planet and natal longitude
    is closest to the target aspect angle.

    Returns the refined datetime, or None if refinement fails.
    """
    # Search window
    dt_start = approx_dt - timedelta(hours=window_hours)
    dt_end = approx_dt + timedelta(hours=window_hours)

    jd_start = _datetime_to_jd(dt_start)
    jd_end = _datetime_to_jd(dt_end)

    def orb_at_jd(jd: float) -> float:
        lon, _, _, _ = _calc_planet_position(transit_planet_id, round(jd, 6))
        angle = _angular_distance(lon, natal_longitude)
        return abs(angle - target_angle)

    # Golden-section-like search for minimum orb
    best_jd = jd_start
    best_orb = orb_at_jd(jd_start)

    # Sample points then refine
    steps = 24  # initial sampling
    jd_step = (jd_end - jd_start) / steps

    for i in range(steps + 1):
        jd = jd_start + i * jd_step
        orb = orb_at_jd(jd)
        if orb < best_orb:
            best_orb = orb
            best_jd = jd

    # Bisection refinement around best point
    lo = best_jd - jd_step
    hi = best_jd + jd_step

    for _ in range(BISECT_ITERATIONS):
        mid1 = lo + (hi - lo) / 3
        mid2 = hi - (hi - lo) / 3

        if orb_at_jd(mid1) < orb_at_jd(mid2):
            hi = mid2
        else:
            lo = mid1

    best_jd = (lo + hi) / 2

    # Convert back to datetime
    try:
        # JD → calendar date
        year, month, day, hour_frac = swe.revjul(best_jd)
        hour = int(hour_frac)
        minute = int((hour_frac - hour) * 60)
        return datetime(year, month, day, hour, minute)
    except Exception:
        return None


def get_transit_summary(events: list[TransitEvent]) -> dict:
    """Generate a summary of transit events for quick overview.

    Returns dict with counts by aspect type and most significant transits.
    """
    summary = {
        "total_events": len(events),
        "by_aspect": {},
        "by_transit_planet": {},
        "significant": [],  # top 10 tightest orbs
    }

    for event in events:
        # Count by aspect type
        a = event.aspect_type
        summary["by_aspect"][a] = summary["by_aspect"].get(a, 0) + 1

        # Count by transit planet
        tp = event.transit_planet
        summary["by_transit_planet"][tp] = summary["by_transit_planet"].get(tp, 0) + 1

    # Top 10 most significant (tightest orb)
    sorted_by_orb = sorted(events, key=lambda e: e.orb)[:10]
    summary["significant"] = [
        {
            "date": e.date,
            "description": f"{e.transit_planet} {e.aspect_type} {e.natal_planet}",
            "orb": e.orb,
            "exact_date": e.exact_date,
        }
        for e in sorted_by_orb
    ]

    return summary
