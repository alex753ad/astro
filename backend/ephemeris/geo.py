"""Geocoding (place → coordinates) and timezone resolution.

Uses Nominatim (free, no API key) as primary geocoder.
Handles DST ambiguity edge-cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytz
from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()

# ── Geocoding cache (24h TTL) ──
from backend.cache import RedisCache
_geo_cache = RedisCache("geo", 24 * 3600)


@dataclass
class GeoResult:
    latitude: float
    longitude: float
    display_name: str
    timezone: str


class GeocodingError(Exception):
    """Raised when geocoding fails."""
    pass


class AmbiguousTimeError(Exception):
    """Raised when birth time falls in a DST transition gap/overlap."""

    def __init__(self, message: str, options: list[str] | None = None):
        super().__init__(message)
        self.options = options or []


async def geocode_place(place: str) -> GeoResult:
    """Geocode a place name to coordinates using Nominatim.

    Returns GeoResult with lat, lon, display name, and timezone.
    Raises GeocodingError if place cannot be found.
    Results are cached for 24 hours.
    """
    import httpx

    # Check cache first
    cache_key = place.lower().strip()
    cached = _geo_cache.get(cache_key)
    if cached:
        return GeoResult(**cached)

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": place,
        "format": "json",
        "limit": 1,
        "accept-language": "en",
    }
    headers = {"User-Agent": "AstroSPA/0.1 (26363@list.ru)"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise GeocodingError(f"Geocoding service error: {e}") from e

    data = resp.json()
    if not data:
        raise GeocodingError(
            f"Place not found: '{place}'. Please provide a more specific location "
            "(e.g., 'Berlin, Germany' instead of just 'Berlin')."
        )

    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    display = data[0].get("display_name", place)

    tz_name = _tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        tz_name = "UTC"

    result = GeoResult(
        latitude=round(lat, 6),
        longitude=round(lon, 6),
        display_name=display,
        timezone=tz_name,
    )

    # Store in cache
    _geo_cache.set(cache_key, {
        "latitude": result.latitude,
        "longitude": result.longitude,
        "display_name": result.display_name,
        "timezone": result.timezone,
    })

    return result


def resolve_utc_datetime(
    birth_date: str,
    birth_time: str | None,
    timezone: str,
) -> tuple[datetime, bool, list[str]]:
    """Convert local birth date/time to UTC.

    Returns (utc_datetime, time_unknown, warnings).

    Handles:
    - Unknown time: defaults to 12:00 noon
    - DST ambiguity: raises AmbiguousTimeError for user clarification
    - Non-existent time (spring forward): adjusts to nearest valid time
    """
    warnings: list[str] = []
    time_unknown = birth_time is None

    if time_unknown:
        birth_time = "12:00"
        warnings.append(
            "Birth time not provided. Using 12:00 noon as default. "
            "Houses and Ascendant will be approximate."
        )

    hour, minute = map(int, birth_time.split(":"))
    year, month, day = map(int, birth_date.split("-"))

    tz = pytz.timezone(timezone)
    naive_dt = datetime(year, month, day, hour, minute, 0)

    try:
        local_dt = tz.localize(naive_dt, is_dst=None)
    except pytz.exceptions.AmbiguousTimeError:
        dt_dst = tz.localize(naive_dt, is_dst=True)
        dt_std = tz.localize(naive_dt, is_dst=False)

        raise AmbiguousTimeError(
            f"The time {birth_time} on {birth_date} in timezone {timezone} is ambiguous "
            f"due to DST transition. It could be either "
            f"{dt_dst.strftime('%H:%M %Z')} (summer time) or "
            f"{dt_std.strftime('%H:%M %Z')} (standard time). "
            f"Please specify which one.",
            options=[
                dt_dst.strftime("%H:%M %Z"),
                dt_std.strftime("%H:%M %Z"),
            ],
        )
    except pytz.exceptions.NonExistentTimeError:
        local_dt = tz.localize(naive_dt, is_dst=True)
        warnings.append(
            f"The time {birth_time} on {birth_date} did not exist in timezone {timezone} "
            f"due to DST spring-forward. Adjusted to {local_dt.strftime('%H:%M %Z')}."
        )

    utc_dt = local_dt.astimezone(pytz.UTC).replace(tzinfo=None)
    return utc_dt, time_unknown, warnings


def validate_coordinates(latitude: float, longitude: float) -> list[str]:
    """Validate geographic coordinates and return any warnings."""
    warnings: list[str] = []

    if not (-90 <= latitude <= 90):
        raise ValueError(f"Invalid latitude: {latitude}. Must be between -90 and 90.")
    if not (-180 <= longitude <= 180):
        raise ValueError(f"Invalid longitude: {longitude}. Must be between -180 and 180.")

    if abs(latitude) > 66.5:
        warnings.append(
            f"Location is near/beyond the polar circle (lat={latitude:.2f}°). "
            "Placidus house system may produce inaccurate results. "
            "Consider using Equal or Whole Sign houses."
        )

    return warnings
