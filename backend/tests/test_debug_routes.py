"""Регрессия: debug-эндпоинты не должны существовать в проде.

Debug-роуты регистрируются на этапе импорта backend.main (гейт
`settings.debug or settings.testing`), поэтому в уже импортированном модуле
режим не переключить — оба состояния проверяются отдельными процессами с явно
заданным окружением. Полагаться на окружение прогона нельзя: локально его
задаёт .env (DEBUG=true), в CI — переменная TESTING, и тест, зависящий от
этого, зелёный по случайной причине.

Проверяются схема OpenAPI и фактический ответ HTTP, а не структура
app.routes: в разных версиях FastAPI include_router по-разному раскладывает
объекты роутов, и интроспекция ломается на ровном месте.
"""

import json
import os
import subprocess
import sys

import pytest


DEBUG_PATHS = [
    "/api/v1/debug/moon",
    "/api/v1/chart/{chart_id}/debug/cusps",
]

# Путь без параметров — по нему проба делает реальный запрос.
MOON_PATH = "/api/v1/debug/moon"

_PROBE = """
import json
from fastapi.testclient import TestClient
from backend.main import app

spec = sorted(app.openapi()["paths"].keys())
# Без контекстного менеджера: lifespan не запускается, значит проба не лезет
# в БД — для проверки роутинга это не нужно.
status = TestClient(app).get("%s").status_code
print("@@" + json.dumps({"openapi": spec, "moon_status": status}))
""" % MOON_PATH


def _probe(**overrides):
    """Импортирует приложение в отдельном процессе с заданным окружением."""
    env = {
        "JWT_SECRET": "probe-secret-long-enough-to-pass-startup-check-0123",
        "TRUSTED_PROXY_IPS": "",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        # DEBUG и TESTING задаются вызывающим всегда: переменные окружения
        # имеют приоритет над .env, где локально стоит DEBUG=true.
        **overrides,
    }
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, env=env, timeout=300,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@")]
    assert marker, f"no output marker:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(marker[0][2:])


@pytest.fixture(scope="module")
def debug_on():
    """DEBUG=true — режим задан явно, а не унаследован от окружения."""
    return _probe(DEBUG="true", TESTING="false")


@pytest.fixture(scope="module")
def debug_off():
    return _probe(DEBUG="false", TESTING="false")


@pytest.fixture(scope="module")
def testing_on():
    """TESTING=true тоже включает debug-роуты — так гейт и написан."""
    return _probe(DEBUG="false", TESTING="true")


class TestDebugRoutesEnabled:

    def test_present_in_openapi(self, debug_on):
        for path in DEBUG_PATHS:
            assert path in debug_on["openapi"]

    def test_moon_route_responds(self, debug_on):
        """Не 404 — эндпоинт существует. Конкретный код зависит от эфемерид."""
        assert debug_on["moon_status"] != 404

    def test_testing_flag_also_enables(self, testing_on):
        for path in DEBUG_PATHS:
            assert path in testing_on["openapi"]


class TestDebugRoutesDisabled:

    def test_absent_from_openapi(self, debug_off):
        for path in DEBUG_PATHS:
            assert path not in debug_off["openapi"]

    def test_moon_route_is_404(self, debug_off):
        """Главная проверка: в проде эндпоинта нет."""
        assert debug_off["moon_status"] == 404

    def test_normal_routes_still_present(self, debug_off):
        """Отключается только debug — остальное приложение на месте."""
        assert "/api/v1/chart/{chart_id}" in debug_off["openapi"]
        assert "/health" in debug_off["openapi"]


class TestCuspsOwnership:
    """debug/cusps подчиняется проверке владельца из задачи 1.

    Выполняется в текущем процессе, поэтому требует, чтобы debug-роуты в нём
    были зарегистрированы; иначе тест пропускается, а не падает ложно.
    """

    @pytest.fixture(autouse=True)
    def _require_debug_routes(self):
        from backend.main import DEBUG_ROUTES_ENABLED

        if not DEBUG_ROUTES_ENABLED:
            pytest.skip("debug-роуты выключены в этом процессе")

    def test_owner_gets_200(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart

        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(
            f"/api/v1/chart/{chart.id}/debug/cusps", headers=auth_headers_free
        )
        assert resp.status_code == 200
        assert "houses" in resp.json()

    def test_foreign_chart_gets_404(self, client, db, user_free, auth_headers_pro):
        from backend.tests.test_chart_access import _make_chart

        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(
            f"/api/v1/chart/{chart.id}/debug/cusps", headers=auth_headers_pro
        )
        assert resp.status_code == 404
