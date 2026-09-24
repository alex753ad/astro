"""Geocoding (place → coordinates) and timezone resolution.

Uses Nominatim (free, no API key) as primary geocoder.
Handles DST ambiguity edge-cases.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

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

    def __init__(self, message: str, options: list[str] | None = None,
                 offsets: list[int] | None = None):
        super().__init__(message)
        self.options = options or []
        # Смещения от UTC в минутах, парой к `options`. Нужны, чтобы выбор
        # человека можно было ОТПРАВИТЬ обратно: `options` — подписи вида
        # «02:30 MSD», поле времени их не принимает (^HH:MM$), а голое «02:30»
        # снова неоднозначно. До 24.09.2026 кнопки выбора слали подпись и
        # получали 422 — родившийся в час перевода часов назад не мог
        # построить карту вовсе.
        self.offsets = offsets or []


async def _nominatim_get(client: "httpx.AsyncClient", params: dict) -> "httpx.Response":
    """Один запрос к Nominatim: троттлинг на весь процесс + retry на 429.

    До 2 повторных попыток при 429, пауза берётся из Retry-After (капается
    5 сек, чтобы не растягивать ответ пользователю на неадекватное время).
    """
    global _last_nominatim_request

    url = "https://nominatim.openstreetmap.org/search"
    _contact = os.getenv("NOMINATIM_CONTACT", "https://aristeatime.ru")
    headers = {"User-Agent": f"AristeaTime/1.0 (+{_contact})"}

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


def _fmt_offset(dt: datetime) -> str:
    """aware datetime → «UTC+4», «UTC−3:30»."""
    minutes = int(dt.utcoffset().total_seconds() // 60)
    sign = "+" if minutes >= 0 else "−"
    h, m = divmod(abs(minutes), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def resolve_utc_datetime(
    birth_date: str,
    birth_time: str | None,
    timezone: str,
    utc_offset_minutes: int | None = None,
) -> tuple[datetime, bool, list[str]]:
    """Convert local birth date/time to UTC.

    `utc_offset_minutes` — смещение, заданное человеком вручную. Имеет
    приоритет над поясом места: история поясов в tzdata хороша, но не
    безупречна (местные решения, самовольный переход районов на соседнее
    время), и у человека должен быть способ её поправить. Неоднозначности
    при нём не бывает — смещение и есть ответ на вопрос «какое из двух».

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

    naive_dt = datetime(year, month, day, hour, minute, 0)
    if utc_offset_minutes is not None:
        return naive_dt - timedelta(minutes=utc_offset_minutes), time_unknown, warnings

    tz = pytz.timezone(timezone)

    try:
        local_dt = tz.localize(naive_dt, is_dst=None)
    except pytz.exceptions.AmbiguousTimeError:
        dt_dst = tz.localize(naive_dt, is_dst=True)
        dt_std = tz.localize(naive_dt, is_dst=False)

        raise AmbiguousTimeError(
            f"В эту ночь часы переводили назад, и {birth_time} наступало дважды: "
            f"сначала по летнему времени ({_fmt_offset(dt_dst)}), потом по "
            f"зимнему ({_fmt_offset(dt_std)}). Выбери, какое из двух.",
            options=[
                dt_dst.strftime("%H:%M %Z"),
                dt_std.strftime("%H:%M %Z"),
            ],
            offsets=[
                int(dt_dst.utcoffset().total_seconds() // 60),
                int(dt_std.utcoffset().total_seconds() // 60),
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


def applied_utc_offset_minutes(
    birth_date: str, birth_time: str | None, utc_dt: datetime | None,
) -> int | None:
    """Смещение от UTC, которое карта ФАКТИЧЕСКИ применила, в минутах.

    Считается из сохранённого, а не заново из пояса: местное время рождения
    минус `utc_datetime`. Так показанное человеку число — ровно то, по
    которому построена карта, даже если с тех пор обновилась tzdata или
    смещение задано вручную. Время неизвестно — местным берётся 12:00, как
    в `resolve_utc_datetime`.
    """
    if utc_dt is None:
        return None
    hour, minute = map(int, (birth_time or "12:00").split(":"))
    year, month, day = map(int, birth_date.split("-"))
    local = datetime(year, month, day, hour, minute)
    return round((local - utc_dt.replace(tzinfo=None)).total_seconds() / 60)
