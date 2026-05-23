"""Transit calculation engine — v2.

Key changes vs v1:
- TransitEvent now has start_date / peak_date / end_date (full period in orb)
- get_active_transits(date) returns all transits active on a given day
- get_planet_positions_for_date(date) returns all transit planet longitudes
  so the frontend can show planet movement on the wheel

Algorithm:
1. Scan the period in daily steps for slow planets, 4-hour steps for fast ones.
2. When a (transit_planet, natal_planet, aspect) combo enters orb → open a window.
3. While still in orb → update current orb; track minimum (peak).
4. When it leaves orb → close the window, emit one TransitEvent with the full span.
5. At query time, filter by active date rather than exact date.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
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

# ── Planet classification ──
FAST_PLANETS  = {"Sun", "Moon", "Mercury", "Venus", "Mars"}
SLOW_PLANETS  = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "North Node"}

FAST_STEP_HOURS = 4
SLOW_STEP_HOURS = 24

# Transit orbs (tighter than natal)
TRANSIT_ORBS = {
    "conjunction": 2.0,
    "sextile":     1.5,
    "square":      2.0,
    "trine":       1.5,
    "opposition":  2.0,
}

BISECT_ITERATIONS = 12


@dataclass
class TransitEvent:
    """A transit aspect with full period of activity."""
    start_date:     str             # first day orb is active   (ISO)
    peak_date:      str             # day of tightest orb       (ISO)
    end_date:       str             # last day orb is active    (ISO)
    transit_planet: str
    transit_sign:   str             # sign on peak_date
    natal_planet:   str
    natal_sign:     str
    aspect_type:    str
    peak_orb:       float           # tightest orb (degrees)
    exact_date:     Optional[str] = None   # precise peak datetime (ISO)
    applying:       bool = True

    # ── convenience ──
    @property
    def date(self) -> str:
        """Alias so old code using .date still works (returns peak_date)."""
        return self.peak_date

    @property
    def orb(self) -> float:
        """Alias for peak_orb."""
        return self.peak_orb

    def is_active_on(self, d: date) -> bool:
        s = date.fromisoformat(self.start_date)
        e = date.fromisoformat(self.end_date)
        return s <= d <= e


@dataclass
class _Window:
    """Internal: tracks an open transit window while planet is in orb."""
    transit_planet: str
    natal_planet:   str
    aspect_type:    str
    natal_sign:     str
    start_dt:       datetime
    peak_dt:        datetime
    peak_orb:       float
    peak_sign:      str
    applying:       bool
    last_dt:        datetime        # updated each step while in orb


def calculate_transits(
    natal_planets: list[dict],
    from_date: date,
    to_date: date,
    orb_filter: Optional[float] = None,
    planet_filter: Optional[list[str]] = None,
) -> list[TransitEvent]:
    """Calculate all transit periods for a natal chart over a date range.

    Returns one TransitEvent per (transit_planet, natal_planet, aspect) passage,
    with start_date/peak_date/end_date covering the full active window.
    """
    natal_positions = {
        p["name"]: {"longitude": p["longitude"], "sign": p["sign"]}
        for p in natal_planets
    }

    transit_planet_names = set(PLANETS.keys()) - {"North Node"}
    if planet_filter:
        transit_planet_names &= set(planet_filter)

    # open_windows[(t_name, n_name, aspect_name)] = _Window
    open_windows: dict[tuple, _Window] = {}
    closed_events: list[TransitEvent] = []

    # Extend scan slightly beyond requested range to catch windows that close after to_date
    scan_end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59) + timedelta(days=3)
    current   = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)

    while current <= scan_end:
        jd = _datetime_to_jd(current)

        for t_name in transit_planet_names:
            t_id = PLANETS[t_name]
            t_lon, _, _, t_speed = _calc_planet_position(t_id, round(jd, 6))
            t_sign, _           = _longitude_to_sign(t_lon)

            for n_name, n_data in natal_positions.items():
                n_lon  = n_data["longitude"]
                angle  = _angular_distance(t_lon, n_lon)

                for aspect_name, exact_angle in ASPECTS.items():
                    max_orb = TRANSIT_ORBS[aspect_name]
                    if orb_filter is not None:
                        max_orb = min(max_orb, orb_filter)

                    orb = abs(angle - exact_angle)
                    key = (t_name, n_name, aspect_name)

                    if orb <= max_orb:
                        if key not in open_windows:
                            # Open new window
                            open_windows[key] = _Window(
                                transit_planet=t_name,
                                natal_planet=n_name,
                                aspect_type=aspect_name,
                                natal_sign=n_data["sign"],
                                start_dt=current,
                                peak_dt=current,
                                peak_orb=orb,
                                peak_sign=t_sign,
                                applying=t_speed >= 0,
                                last_dt=current,
                            )
                        else:
                            w = open_windows[key]
                            w.last_dt = current
                            if orb < w.peak_orb:
                                w.peak_orb  = orb
                                w.peak_dt   = current
                                w.peak_sign = t_sign
                                w.applying  = t_speed >= 0
                    else:
                        if key in open_windows:
                            # Close window → emit event
                            w = open_windows.pop(key)
                            # Only emit if window overlaps requested range
                            if w.last_dt.date() >= from_date and w.start_dt.date() <= to_date:
                                step_h = FAST_STEP_HOURS if t_name in FAST_PLANETS else SLOW_STEP_HOURS
                                exact_dt = _find_exact_aspect(t_id, n_lon, exact_angle, w.peak_dt, step_h)
                                closed_events.append(_make_event(w, exact_dt))

        # Step size: use fast step so Moon is caught properly
        current += timedelta(hours=FAST_STEP_HOURS)

    # Close any windows still open at scan end
    for key, w in open_windows.items():
        t_name = w.transit_planet
        if w.last_dt.date() >= from_date and w.start_dt.date() <= to_date:
            t_id = PLANETS[t_name]
            n_lon = natal_positions[w.natal_planet]["longitude"]
            exact_angle = ASPECTS[w.aspect_type]
            step_h = FAST_STEP_HOURS if t_name in FAST_PLANETS else SLOW_STEP_HOURS
            exact_dt = _find_exact_aspect(t_id, n_lon, exact_angle, w.peak_dt, step_h)
            closed_events.append(_make_event(w, exact_dt))

    closed_events.sort(key=lambda e: (e.start_date, e.peak_orb))

    logger.info(
        "Calculated %d transit periods for %s → %s",
        len(closed_events), from_date, to_date,
    )
    return closed_events


def _make_event(w: _Window, exact_dt: Optional[datetime]) -> TransitEvent:
    return TransitEvent(
        start_date=w.start_dt.strftime("%Y-%m-%d"),
        peak_date=w.peak_dt.strftime("%Y-%m-%d"),
        end_date=w.last_dt.strftime("%Y-%m-%d"),
        transit_planet=w.transit_planet,
        transit_sign=w.peak_sign,
        natal_planet=w.natal_planet,
        natal_sign=w.natal_sign,
        aspect_type=w.aspect_type,
        peak_orb=round(w.peak_orb, 4),
        exact_date=exact_dt.strftime("%Y-%m-%dT%H:%M") if exact_dt else None,
        applying=w.applying,
    )


def get_active_transits(
    events: list[TransitEvent],
    on_date: date,
) -> list[TransitEvent]:
    """Filter transit events to those active on a specific date."""
    return [e for e in events if e.is_active_on(on_date)]


def get_planet_positions_for_date(query_date: date) -> list[dict]:
    """Return current ecliptic longitudes for all transit planets on a given date.

    Used by the frontend to show planet positions on the natal wheel for a
    selected day, so the user can see where planets are moving.

    Returns list of:
      {name, longitude, sign, degree_in_sign, retrograde, glyph}
    """
    dt = datetime(query_date.year, query_date.month, query_date.day, 12, 0, 0)
    jd = _datetime_to_jd(dt)

    GLYPHS = {
        "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀",
        "Mars": "♂", "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅",
        "Neptune": "♆", "Pluto": "♇", "North Node": "☊",
    }

    result = []
    for name, planet_id in PLANETS.items():
        lon, _, _, speed = _calc_planet_position(planet_id, round(jd, 6))
        sign, deg = _longitude_to_sign(lon)
        result.append({
            "name":          name,
            "longitude":     round(lon, 4),
            "sign":          sign,
            "degree_in_sign": round(deg, 4),
            "retrograde":    speed < 0,
            "glyph":         GLYPHS.get(name, "?"),
        })
    return result


def _find_exact_aspect(
    transit_planet_id: int,
    natal_longitude: float,
    target_angle: float,
    approx_dt: datetime,
    window_hours: int,
) -> Optional[datetime]:
    dt_start = approx_dt - timedelta(hours=window_hours)
    dt_end   = approx_dt + timedelta(hours=window_hours)
    jd_start = _datetime_to_jd(dt_start)
    jd_end   = _datetime_to_jd(dt_end)

    def orb_at_jd(jd: float) -> float:
        lon, _, _, _ = _calc_planet_position(transit_planet_id, round(jd, 6))
        return abs(_angular_distance(lon, natal_longitude) - target_angle)

    best_jd  = jd_start
    best_orb = orb_at_jd(jd_start)
    steps    = 24
    jd_step  = (jd_end - jd_start) / steps

    for i in range(steps + 1):
        jd  = jd_start + i * jd_step
        orb = orb_at_jd(jd)
        if orb < best_orb:
            best_orb = orb
            best_jd  = jd

    lo = best_jd - jd_step
    hi = best_jd + jd_step
    for _ in range(BISECT_ITERATIONS):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if orb_at_jd(m1) < orb_at_jd(m2):
            hi = m2
        else:
            lo = m1

    try:
        year, month, day, hf = swe.revjul((lo + hi) / 2)
        h, m = int(hf), int((hf - int(hf)) * 60)
        return datetime(year, month, day, h, m)
    except Exception:
        return None


def get_transit_summary(events: list[TransitEvent]) -> dict:
    summary = {
        "total_events":      len(events),
        "by_aspect":         {},
        "by_transit_planet": {},
        "significant":       [],
    }
    for e in events:
        summary["by_aspect"][e.aspect_type]             = summary["by_aspect"].get(e.aspect_type, 0) + 1
        summary["by_transit_planet"][e.transit_planet]  = summary["by_transit_planet"].get(e.transit_planet, 0) + 1

    for e in sorted(events, key=lambda x: x.peak_orb)[:10]:
        summary["significant"].append({
            "date":        e.peak_date,
            "description": f"{e.transit_planet} {e.aspect_type} {e.natal_planet}",
            "orb":         e.peak_orb,
            "exact_date":  e.exact_date,
            "period":      f"{e.start_date} → {e.end_date}",
        })
    return summary
