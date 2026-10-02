"""Пояс чата — как у ленты и планера: tz запроса → пояс устройства → пояс карты."""
from types import SimpleNamespace

from backend.interpretation.rag_router import chat_timezone

_CHART = SimpleNamespace(timezone="Europe/Moscow")


def test_request_tz_wins():
    user = SimpleNamespace(device_timezone="Asia/Novosibirsk")
    assert chat_timezone("Asia/Vladivostok", user, _CHART) == "Asia/Vladivostok"


def test_device_tz_when_request_has_none_or_garbage():
    user = SimpleNamespace(device_timezone="Asia/Novosibirsk")
    assert chat_timezone(None, user, _CHART) == "Asia/Novosibirsk"
    assert chat_timezone("Not/AZone", user, _CHART) == "Asia/Novosibirsk"


def test_chart_tz_last():
    user = SimpleNamespace(device_timezone=None)
    assert chat_timezone("", user, _CHART) == "Europe/Moscow"
