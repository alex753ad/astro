"""Один пояс и одна граница дня (time_utils.user_tz / local_day), шаг 2 аудита:
tz запроса → пояс устройства → пояс карты → Москва."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

from backend.time_utils import local_day, local_today, user_tz

_CHART = SimpleNamespace(timezone="Asia/Novosibirsk")


def test_request_tz_wins():
    user = SimpleNamespace(device_timezone="Asia/Vladivostok")
    assert user_tz("America/New_York", user, _CHART) == "America/New_York"


def test_device_tz_when_request_has_none_or_garbage():
    user = SimpleNamespace(device_timezone="Asia/Vladivostok")
    assert user_tz(None, user, _CHART) == "Asia/Vladivostok"
    assert user_tz("Not/AZone", user, _CHART) == "Asia/Vladivostok"


def test_chart_tz_then_moscow():
    assert user_tz("", SimpleNamespace(device_timezone=None), _CHART) == "Asia/Novosibirsk"
    # Прогноз дня до 04.10.2026 падал здесь в UTC, чат — в None.
    assert user_tz(None, None, SimpleNamespace(timezone=None)) == "Europe/Moscow"
    assert user_tz() == "Europe/Moscow"


def test_local_day_bounds():
    s, e = local_day(date(2026, 10, 5), "Asia/Vladivostok")
    assert (s, e) == (datetime(2026, 10, 4, 14, tzinfo=timezone.utc), datetime(2026, 10, 5, 14, tzinfo=timezone.utc))
    s, e = local_day(date(2026, 10, 5), "America/New_York")
    assert (s, e) == (datetime(2026, 10, 5, 4, tzinfo=timezone.utc), datetime(2026, 10, 6, 4, tzinfo=timezone.utc))


def test_local_day_dst_is_25_hours():
    s, e = local_day(date(2026, 11, 1), "America/New_York")   # переход на зимнее
    assert (e - s).total_seconds() == 25 * 3600


def test_local_today_around_midnight():
    instant = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)   # 00:30 5-го во Владивостоке
    assert local_today("Asia/Vladivostok", instant) == date(2026, 10, 5)
    assert local_today("America/New_York", instant) == date(2026, 10, 4)
    instant = datetime(2026, 10, 5, 3, 30, tzinfo=timezone.utc)    # 23:30 4-го в Нью-Йорке
    assert local_today("America/New_York", instant) == date(2026, 10, 4)
