"""tests/test_load.py — нагрузочный тест: 100 одновременных запросов.

Цель: p95 времени ответа < 2000 мс на POST /api/v1/chart/calculate

Запуск: pytest backend/tests/test_load.py -v -s
Только нагрузочные тесты: pytest -v -s -m load

ВАЖНО: Запускать с моком calculator, иначе нужны ephemeris-файлы.
Для нагрузки на реальный сервер используйте LOAD_TEST_URL=http://localhost:8000
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import NamedTuple
from unittest.mock import patch, MagicMock

import pytest
import httpx

try:
    from fastapi.testclient import TestClient
    from backend.main import app
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


# ── Конфигурация ──────────────────────────────────────────────────────────────

CONCURRENT_REQUESTS = 100
TARGET_P95_MS = 2000
TARGET_P99_MS = 5000
TARGET_ERROR_RATE = 0.01  # < 1% ошибок

EXTERNAL_URL = os.getenv("LOAD_TEST_URL", "")  # если задан — тест против живого сервера


# ── Типы ─────────────────────────────────────────────────────────────────────

class RequestResult(NamedTuple):
    status_code: int
    elapsed_ms: float
    error: str | None


# ── Фикстуры ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_full_calculator():
    """Быстрый мок calculator — возвращает результат без реальных вычислений."""
    with patch("backend.ephemeris.calculator.calculate_full_chart") as m:
        from backend.ephemeris.calculator import FullChart, PlanetResult, HouseResult, PointResult

        def _make_chart(*args, **kwargs):
            planets = []
            for i, name in enumerate(["Sun", "Moon", "Mercury", "Venus", "Mars",
                                       "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "North Node"]):
                p = PlanetResult(
                    name=name, longitude=float(i * 30), latitude=0.0,
                    distance=1.0, speed=1.0, sign="Aries",
                    degree_in_sign=float(i * 2), retrograde=False,
                )
                p.house = (i % 12) + 1
                planets.append(p)

            houses = [HouseResult(number=i + 1, sign="Aries", degree=float(i * 30)) for i in range(12)]
            asc = PointResult(sign="Aries", degree=5.0, longitude=5.0)
            mc = PointResult(sign="Capricorn", degree=10.0, longitude=280.0)
            chart = FullChart(planets=planets, houses=houses, ascendant=asc, midheaven=mc, warnings=[])
            return chart, []

        m.side_effect = _make_chart
        yield m


@pytest.fixture
def mock_geo_fast():
    with patch("backend.ephemeris.geo.geocode_location") as m:
        m.return_value = {"lat": 55.75, "lon": 37.62, "display_name": "Moscow"}
        yield m


# ── Логика нагрузки ───────────────────────────────────────────────────────────

def _single_request(client: TestClient, payload: dict, index: int) -> RequestResult:
    """Один HTTP-запрос с замером времени."""
    start = time.perf_counter()
    try:
        resp = client.post("/api/v1/chart/calculate", json=payload)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            status_code=resp.status_code,
            elapsed_ms=elapsed_ms,
            error=None if resp.status_code == 200 else f"HTTP {resp.status_code}",
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return RequestResult(status_code=0, elapsed_ms=elapsed_ms, error=str(e))


def _run_concurrent_requests(
    client: TestClient,
    n: int = CONCURRENT_REQUESTS,
    max_workers: int = 20,
) -> list[RequestResult]:
    """Запускаем N параллельных запросов через ThreadPoolExecutor."""
    payload = {
        "name": "Load Test",
        "birth_date": "1990-06-15",
        "birth_time": "10:30",
        "birth_place": "Moscow",
        "latitude": 55.75,
        "longitude": 37.62,
        "house_system": "placidus",
    }

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_single_request, client, payload, i)
            for i in range(n)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    return results


def _percentile(data: list[float], pct: float) -> float:
    sorted_data = sorted(data)
    index = int(len(sorted_data) * pct / 100)
    return sorted_data[min(index, len(sorted_data) - 1)]


def _print_stats(results: list[RequestResult], label: str = ""):
    times = [r.elapsed_ms for r in results]
    errors = [r for r in results if r.error]
    print(f"\n{'=' * 50}")
    print(f"Load Test Results {label}")
    print(f"{'=' * 50}")
    print(f"  Total requests : {len(results)}")
    print(f"  Errors         : {len(errors)} ({len(errors)/len(results)*100:.1f}%)")
    print(f"  Min            : {min(times):.1f} ms")
    print(f"  Mean           : {statistics.mean(times):.1f} ms")
    print(f"  Median (p50)   : {_percentile(times, 50):.1f} ms")
    print(f"  p90            : {_percentile(times, 90):.1f} ms")
    print(f"  p95            : {_percentile(times, 95):.1f} ms")
    print(f"  p99            : {_percentile(times, 99):.1f} ms")
    print(f"  Max            : {max(times):.1f} ms")
    if errors:
        from collections import Counter
        error_counts = Counter(r.error for r in errors)
        print(f"  Error types    : {dict(error_counts)}")
    print(f"{'=' * 50}")


# ═══════════════════════════════════════════════════════════
# Нагрузочные тесты
# ═══════════════════════════════════════════════════════════

@pytest.mark.load
@pytest.mark.skipif(not APP_AVAILABLE, reason="backend app not importable")
class TestLoadChartCalculate:

    def test_100_concurrent_p95_under_2s(
        self, client, mock_full_calculator, mock_geo_fast
    ):
        """100 одновременных запросов, p95 < 2000 мс."""
        results = _run_concurrent_requests(client, n=CONCURRENT_REQUESTS)
        _print_stats(results, "(100 concurrent)")

        times = [r.elapsed_ms for r in results]
        p95 = _percentile(times, 95)

        assert p95 < TARGET_P95_MS, (
            f"p95={p95:.0f}ms превышает лимит {TARGET_P95_MS}ms"
        )

    def test_100_concurrent_error_rate_under_1pct(
        self, client, mock_full_calculator, mock_geo_fast
    ):
        """100 запросов, менее 1% ошибок."""
        results = _run_concurrent_requests(client, n=CONCURRENT_REQUESTS)

        errors = [r for r in results if r.error is not None]
        error_rate = len(errors) / len(results)

        assert error_rate <= TARGET_ERROR_RATE, (
            f"Error rate {error_rate:.1%} превышает {TARGET_ERROR_RATE:.1%}"
        )

    def test_100_concurrent_all_return_200(
        self, client, mock_full_calculator, mock_geo_fast
    ):
        """Все 100 запросов возвращают HTTP 200."""
        results = _run_concurrent_requests(client, n=CONCURRENT_REQUESTS)

        non_200 = [r for r in results if r.status_code != 200]
        assert len(non_200) == 0, (
            f"{len(non_200)} запросов вернули не 200: "
            f"{[(r.status_code, r.error) for r in non_200[:5]]}"
        )

    def test_50_concurrent_p95_under_1s(
        self, client, mock_full_calculator, mock_geo_fast
    ):
        """50 одновременных → p95 < 1000 мс (менее нагруженный сценарий)."""
        results = _run_concurrent_requests(client, n=50)
        _print_stats(results, "(50 concurrent)")

        times = [r.elapsed_ms for r in results]
        p95 = _percentile(times, 95)

        assert p95 < 1000, f"p95={p95:.0f}ms для 50 запросов слишком высок"

    def test_sequential_baseline(self, client, mock_full_calculator, mock_geo_fast):
        """Базовый последовательный тест: один запрос < 500 мс."""
        payload = {
            "name": "Baseline",
            "birth_date": "1990-06-15",
            "birth_time": "10:30",
            "birth_place": "Moscow",
            "latitude": 55.75,
            "longitude": 37.62,
        }

        times = []
        for _ in range(10):
            start = time.perf_counter()
            resp = client.post("/api/v1/chart/calculate", json=payload)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            assert resp.status_code == 200

        median = statistics.median(times)
        print(f"\nBaseline (10 sequential): median={median:.1f}ms")
        assert median < 500, f"Базовый запрос {median:.0f}ms > 500ms"


# ═══════════════════════════════════════════════════════════
# Нагрузка против внешнего сервера
# ═══════════════════════════════════════════════════════════

@pytest.mark.load
@pytest.mark.skipif(not EXTERNAL_URL, reason="LOAD_TEST_URL не задан")
class TestExternalLoadTest:
    """Тест против реального сервера (Railway/localhost).

    Использование:
        LOAD_TEST_URL=http://localhost:8000 pytest -v -s -m load tests/test_load.py::TestExternalLoadTest
    """

    def test_external_100_concurrent(self):
        payload = {
            "name": "External Load",
            "birth_date": "1990-06-15",
            "birth_time": "10:30",
            "birth_place": "Moscow",
            "latitude": 55.75,
            "longitude": 37.62,
        }

        def _req(i):
            start = time.perf_counter()
            try:
                resp = httpx.post(
                    f"{EXTERNAL_URL}/api/v1/chart/calculate",
                    json=payload,
                    timeout=10.0,
                )
                elapsed = (time.perf_counter() - start) * 1000
                return RequestResult(resp.status_code, elapsed, None if resp.status_code == 200 else str(resp.status_code))
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                return RequestResult(0, elapsed, str(e))

        results = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(_req, i) for i in range(CONCURRENT_REQUESTS)]
            for f in as_completed(futures):
                results.append(f.result())

        _print_stats(results, f"(External: {EXTERNAL_URL})")

        times = [r.elapsed_ms for r in results]
        p95 = _percentile(times, 95)
        errors = [r for r in results if r.error]

        print(f"\np95={p95:.0f}ms, errors={len(errors)}/{len(results)}")
        assert p95 < TARGET_P95_MS, f"p95={p95:.0f}ms > {TARGET_P95_MS}ms"
        assert len(errors) / len(results) <= TARGET_ERROR_RATE


# ═══════════════════════════════════════════════════════════
# Утилита: запуск вручную
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    """Быстрый запуск без pytest для отладки нагрузки."""
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    print(f"Нагрузочный тест: {n} запросов → {url}")

    payload = {
        "name": "Manual Load",
        "birth_date": "1990-06-15",
        "birth_time": "10:30",
        "birth_place": "Moscow",
        "latitude": 55.75,
        "longitude": 37.62,
    }

    def _req(i):
        start = time.perf_counter()
        try:
            resp = httpx.post(f"{url}/api/v1/chart/calculate", json=payload, timeout=10.0)
            return RequestResult(resp.status_code, (time.perf_counter() - start) * 1000, None)
        except Exception as e:
            return RequestResult(0, (time.perf_counter() - start) * 1000, str(e))

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_req, i) for i in range(n)]
        for f in as_completed(futures):
            results.append(f.result())

    _print_stats(results)
