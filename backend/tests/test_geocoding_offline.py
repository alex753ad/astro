"""geocode_place — разбор ответа Nominatim без обращения к Nominatim.

Зачем этот файл существует. `mock_geo` в conftest.py подменяет саму функцию
`geocode_place`, то есть весь наш код внутри неё — разбор JSON, выбор
часового пояса, ветки ошибок, кэш, ретрай на 429 — в остальных тестах не
исполняется вовсе. Мок, поставленный на границе с чужим сервисом, экономит
время и убирает зависимость от Nominatim, но он же уносит из-под проверки
наш собственный код обработки ответа: заменили бы `data[0]["lat"]` на
`data[0]["latitude"]` — ни один тест бы не заметил.

Поэтому здесь мок стоит НИЖЕ нашего кода: подменяется httpx-транспорт
(канонический ответ Nominatim в виде байтов), а `geocode_place` исполняется
целиком и по-настоящему. Так внешний сервис из тестов убран, а наш разбор —
нет.
"""

import httpx
import pytest
from unittest.mock import patch

from backend.ephemeris import geo
from backend.ephemeris.geo import GeocodingError, geocode_place
from backend.tests.netguard import OutboundNetworkBlocked


# Ответ Nominatim в том виде, в каком он приходит на самом деле (поля,
# которых мы не читаем, оставлены намеренно: если код начнёт зависеть от
# лишнего поля, это должно быть видно здесь, а не на проде).
NOMINATIM_BERLIN = [
    {
        "place_id": 240109189,
        "licence": "Data © OpenStreetMap contributors",
        "osm_type": "relation",
        "lat": "52.5170365",
        "lon": "13.3888599",
        "display_name": "Берлин, Германия",
        "class": "boundary",
        "type": "administrative",
        "importance": 0.8,
    }
]


@pytest.fixture(autouse=True)
def clean_geo_cache():
    """Кэш геокодинга — модульный синглтон, живёт между тестами.

    Без сброса второй тест получил бы результат первого и проверял бы кэш
    вместо разбора ответа.
    """
    def _clear():
        geo._geo_cache._local.clear()
        if geo._geo_cache._redis is not None:
            try:
                for key in geo._geo_cache._redis.scan_iter("geo:*"):
                    geo._geo_cache._redis.delete(key)
            except Exception:
                pass

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def no_throttle():
    """Троттлинг 1.1 с/запрос — политика Nominatim, к разбору ответа не относится."""
    with patch.object(geo, "_MIN_INTERVAL", 0.0):
        yield


def _mock_transport(handler):
    """Подменяет httpx.AsyncClient так, чтобы запросы шли в handler, а не в сеть."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    return patch.object(geo.httpx, "AsyncClient", factory)


def _json_response(payload, status_code=200):
    return lambda request: httpx.Response(status_code, json=payload)


class TestResponseParsing:
    """Наш код разбора ответа — исполняется по-настоящему."""

    async def test_parses_coordinates_and_display_name(self):
        with _mock_transport(_json_response(NOMINATIM_BERLIN)):
            result = await geocode_place("Berlin, Germany")

        assert result.latitude == 52.517037   # округление до 6 знаков — наше
        assert result.longitude == 13.38886
        assert result.display_name == "Берлин, Германия"

    async def test_resolves_timezone_from_coordinates(self):
        """Часовой пояс мы не берём из ответа — считаем сами по координатам."""
        with _mock_transport(_json_response(NOMINATIM_BERLIN)):
            result = await geocode_place("Berlin, Germany")

        assert result.timezone == "Europe/Berlin"

    async def test_display_name_falls_back_to_query(self):
        payload = [{"lat": "52.5", "lon": "13.4"}]  # без display_name
        with _mock_transport(_json_response(payload)):
            result = await geocode_place("Некое место")

        assert result.display_name == "Некое место"

    async def test_timezone_falls_back_to_utc_when_lookup_finds_nothing(self):
        """Ветка `if not tz_name: tz_name = "UTC"` — наша, и она достижима.

        Реальные координаты сюда не годятся: у timezonefinder даже посреди
        океана есть ответ (для 0.0/-140.0 — Etc/GMT+9), поэтому None
        подставляется явно. Иначе тест проверял бы не наш фолбэк, а данные
        библиотеки.
        """
        class _NoZone:
            # TimezoneFinder — C-расширение, его timezone_at read-only, поэтому
            # подменяется объект целиком, а не метод на нём.
            def timezone_at(self, **kwargs):
                return None

        payload = [{"lat": "0.0", "lon": "-140.0", "display_name": "Ocean"}]
        with _mock_transport(_json_response(payload)), patch.object(geo, "_tf", _NoZone()):
            result = await geocode_place("Точка в океане")

        assert result.timezone == "UTC"

    async def test_sends_query_to_nominatim(self):
        """Параметры запроса — тоже наш код, а не чужой."""
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["user_agent"] = request.headers.get("user-agent")
            return httpx.Response(200, json=NOMINATIM_BERLIN)

        with _mock_transport(handler):
            await geocode_place("Berlin, Germany")

        assert "q=Berlin" in seen["url"]
        assert "format=json" in seen["url"]
        assert "limit=1" in seen["url"]
        # Nominatim требует опознаваемый User-Agent, без него банит.
        assert "AstreaTime" in seen["user_agent"]


class TestErrorHandling:
    async def test_empty_result_raises_place_not_found(self):
        with _mock_transport(_json_response([])):
            with pytest.raises(GeocodingError, match="Place not found"):
                await geocode_place("Такого места нет")

    async def test_http_error_raises_service_error(self):
        with _mock_transport(_json_response({"error": "boom"}, status_code=500)):
            with pytest.raises(GeocodingError, match="Geocoding service error"):
                await geocode_place("Berlin")

    async def test_retries_on_429_and_succeeds(self):
        """429 — ровно то, на чём развалился прогон CI 31.08.2026."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"}, json={})
            return httpx.Response(200, json=NOMINATIM_BERLIN)

        with _mock_transport(handler):
            result = await geocode_place("Berlin, Germany")

        assert calls["n"] == 2
        assert result.timezone == "Europe/Berlin"

    async def test_gives_up_after_three_attempts_on_429(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})

        with _mock_transport(handler):
            with pytest.raises(GeocodingError, match="Geocoding service error"):
                await geocode_place("Berlin")

        assert calls["n"] == 3


class TestCaching:
    async def test_second_call_does_not_hit_the_network(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json=NOMINATIM_BERLIN)

        with _mock_transport(handler):
            first = await geocode_place("Berlin, Germany")
            second = await geocode_place("Berlin, Germany")

        assert calls["n"] == 1
        assert first.latitude == second.latitude

    async def test_normalized_key_shares_cache_entry(self):
        """«Berlin, Germany» и «Berlin» — один вход в кэше (до первой запятой)."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json=NOMINATIM_BERLIN)

        with _mock_transport(handler):
            await geocode_place("Berlin, Germany")
            await geocode_place("Berlin")

        assert calls["n"] == 1

    async def test_failure_is_cached_too(self):
        """Отрицательный кэш — чтобы не долбить чужой сервис одним и тем же."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json=[])

        with _mock_transport(handler):
            with pytest.raises(GeocodingError):
                await geocode_place("Место, которого нет")
            with pytest.raises(GeocodingError):
                await geocode_place("Место, которого нет")

        assert calls["n"] == 1


class TestNetworkGuard:
    """Сам предохранитель: незамоканный вызов обязан падать, а не уходить в сеть.

    Без этих двух тестов заглушка — необязательное украшение: если она
    однажды перестанет ловить (как уже было с асинхронным путём на Windows,
    где ProactorEventLoop идёт мимо socket.connect), прогон снова начнёт
    молча ходить в интернет и снова станет зависеть от чужого сервера.
    """

    async def test_async_client_cannot_reach_the_network(self):
        with pytest.raises(OutboundNetworkBlocked):
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get("https://nominatim.openstreetmap.org/search")

    def test_sync_client_cannot_reach_the_network(self):
        with pytest.raises(OutboundNetworkBlocked):
            httpx.get("https://api.openai.com/v1/models", timeout=5)

    async def test_unmocked_geocode_raises_guard_error_not_geocoding_error(self):
        """Ошибка предохранителя не маскируется под ошибку геокодинга.

        `geocode_place` ловит `httpx.HTTPError` и переупаковывает его в
        `GeocodingError("Geocoding service error: ...")`. Наш
        `OutboundNetworkBlocked` — не `HTTPError`, поэтому проходит наверх
        как есть, и в отчёте видно «тест пытался обратиться наружу», а не
        «внешний сервис недоступен». Разница существенная: во втором случае
        забытый мок выглядит как сбой чужого сервера — ровно та подмена
        причины, из-за которой прогон CI 31.08.2026 разбирали не с того
        конца.
        """
        with pytest.raises(OutboundNetworkBlocked):
            await geocode_place("Место, которого нет в кэше 20260831")
