"""Geocoding (place → coordinates) and timezone resolution.

Uses Nominatim (free, no API key) as primary geocoder.
Handles DST ambiguity edge-cases.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
import pytz
from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()

# ── Geocoding cache (24h TTL) ──
from backend.cache import RedisCache
_geo_cache = RedisCache("geo", 24 * 3600)

_NEGATIVE_TTL = 5 * 60  # неудачный геокодинг кэшируем ненадолго — не долбить API повторно

# ── Троттлинг Nominatim: политика сервиса — максимум 1 запрос/сек.
# Semaphore(1) сериализует запросы на весь процесс, пауза между вызовами
# гарантирует интервал. При масштабировании на несколько воркеров троттлинг
# нужно будет выносить в Redis (single-worker deployment — см. start.sh).
_nominatim_semaphore = asyncio.Semaphore(1)
_last_nominatim_request = 0.0
_MIN_INTERVAL = 1.1  # сек


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


async def _nominatim_get(client: "httpx.AsyncClient", params: dict) -> "httpx.Response":
    """Один запрос к Nominatim: троттлинг на весь процесс + retry на 429.

    До 2 повторных попыток при 429, пауза берётся из Retry-After (капается
    5 сек, чтобы не растягивать ответ пользователю на неадекватное время).
    """
    global _last_nominatim_request

    url = "https://nominatim.openstreetmap.org/search"
    _contact = os.getenv("NOMINATIM_CONTACT", "https://astreatime.ru")
    headers = {"User-Agent": f"AstreaTime/1.0 (+{_contact})"}

    resp = None
    for attempt in range(3):
        async with _nominatim_semaphore:
            elapsed = time.monotonic() - _last_nominatim_request
            if elapsed < _MIN_INTERVAL:
                await asyncio.sleep(_MIN_INTERVAL - elapsed)
            resp = await client.get(url, params=params, headers=headers)
            _last_nominatim_request = time.monotonic()

        if resp.status_code != 429 or attempt == 2:
            return resp

        retry_after = resp.headers.get("Retry-After")
        try:
            pause = min(float(retry_after), 5.0) if retry_after else 2.0
        except ValueError:
            pause = 2.0
        await asyncio.sleep(pause)

    return resp


async def geocode_place(place: str) -> GeoResult:
    """Geocode a place name to coordinates using Nominatim.

    Returns GeoResult with lat, lon, display name, and timezone.
    Raises GeocodingError if place cannot be found.
    Results are cached for 24 hours; failures are cached briefly to avoid
    hammering Nominatim with the same bad/rate-limited query.
    """
    # Прямой ключ — точный ввод. Нормализованный — до первой запятой, чтобы
    # "Moscow", "Moscow, Russia" и "Moscow, Central Federal District, Russia"
    # были одним кэш-хитом. Прямой ключ проверяется первым и не теряет
    # точность при повторном точном совпадении.
    direct_key = place.lower().strip()
    normalized_key = direct_key.split(",")[0].strip()

    cached = _geo_cache.get(direct_key)
    if cached is None and normalized_key != direct_key:
        cached = _geo_cache.get(normalized_key)
    if cached:
        return GeoResult(**cached)

    neg_key = f"neg:{direct_key}"
    negative = _geo_cache.get(neg_key)
    if negative:
        raise GeocodingError(negative["error"])

    params = {
        "q": place,
        "format": "json",
        "limit": 1,
        "accept-language": "ru",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await _nominatim_get(client, params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            error_msg = f"Geocoding service error: {e}"
            _geo_cache.set(neg_key, {"error": error_msg}, ttl=_NEGATIVE_TTL)
            raise GeocodingError(error_msg) from e

    data = resp.json()
    if not data:
        error_msg = (
            f"Place not found: '{place}'. Please provide a more specific location "
            "(e.g., 'Berlin, Germany' instead of just 'Berlin')."
        )
        _geo_cache.set(neg_key, {"error": error_msg}, ttl=_NEGATIVE_TTL)
        raise GeocodingError(error_msg)

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

    payload = {
        "latitude": result.latitude,
        "longitude": result.longitude,
        "display_name": result.display_name,
        "timezone": result.timezone,
    }
    _geo_cache.set(direct_key, payload)
    if normalized_key != direct_key:
        _geo_cache.set(normalized_key, payload)

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


geocode_location = geocode_place


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
