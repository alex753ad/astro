"""Регрессия: debug-эндпоинты не должны существовать в проде.

Позитив проверяется в текущем процессе (TESTING=true — роуты есть).
Негатив требует отдельного процесса: регистрация роутов происходит на этапе
импорта backend.main, поэтому в уже импортированном модуле её не отменить.
"""

import subprocess
import sys

import pytest


DEBUG_PATHS = [
    "/api/v1/debug/moon",
    "/api/v1/chart/{chart_id}/debug/cusps",
]


class TestDebugRoutesEnabled:
    """TESTING=true — роуты зарегистрированы (conftest выставляет флаг)."""

    def test_routes_registered(self):
        from backend.main import app

        paths = {r.path for r in app.routes}
        for path in DEBUG_PATHS:
            assert path in paths

    def test_cusps_reachable(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart

        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(
            f"/api/v1/chart/{chart.id}/debug/cusps", headers=auth_headers_free
        )
        assert resp.status_code == 200
        assert "houses" in resp.json()

    def test_cusps_enforces_ownership(self, client, db, user_free, auth_headers_pro):
        """Задача 1: debug/cusps тоже подчиняется проверке владельца."""
        from backend.tests.test_chart_access import _make_chart

        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(
            f"/api/v1/chart/{chart.id}/debug/cusps", headers=auth_headers_pro
        )
        assert resp.status_code == 404


class TestDebugRoutesDisabled:
    """DEBUG=false и TESTING=false — роутов нет ни в app, ни в openapi."""

    @pytest.fixture(scope="class")
    def prod_app_probe(self):
        """Импортирует backend.main в чистом процессе с выключенным debug."""
        code = (
            "import json\n"
            "from backend.main import app\n"
            "paths = sorted({r.path for r in app.routes})\n"
            "spec = sorted(app.openapi()['paths'].keys())\n"
            "print('@@' + json.dumps({'routes': paths, 'openapi': spec}))\n"
        )
        env = {
            "DEBUG": "false",
            "TESTING": "false",
            "JWT_SECRET": "test-secret-not-the-default-placeholder",
            "PATH": __import__("os").environ.get("PATH", ""),
            "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        }
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env, timeout=300,
        )
        assert proc.returncode == 0, f"probe failed:\n{proc.stderr}"
        marker = [l for l in proc.stdout.splitlines() if l.startswith("@@")]
        assert marker, f"no output marker:\n{proc.stdout}\n{proc.stderr}"
        import json
        return json.loads(marker[0][2:])

    def test_routes_absent(self, prod_app_probe):
        for path in DEBUG_PATHS:
            assert path not in prod_app_probe["routes"]

    def test_absent_from_openapi(self, prod_app_probe):
        for path in DEBUG_PATHS:
            assert path not in prod_app_probe["openapi"]

    def test_normal_routes_still_present(self, prod_app_probe):
        """Отключается только debug — остальное приложение на месте."""
        assert "/api/v1/chart/{chart_id}" in prod_app_probe["routes"]
        assert "/health" in prod_app_probe["routes"]
