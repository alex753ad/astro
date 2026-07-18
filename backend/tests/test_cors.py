"""Регрессия: CORS отвечает только разрешённым origin, методам и заголовкам."""

import subprocess
import sys

import pytest

from backend.config import get_settings


ALLOWED_ORIGIN = get_settings().cors_origins_list[0]
FOREIGN_ORIGIN = "https://evil.example.com"


def _preflight(client, origin, method="POST", headers="content-type"):
    return client.options(
        "/api/v1/chart/calculate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


class TestForeignOriginRejected:

    def test_no_cors_headers_for_foreign_origin(self, client):
        resp = client.get("/health", headers={"Origin": FOREIGN_ORIGIN})
        assert "access-control-allow-origin" not in resp.headers

    def test_preflight_from_foreign_origin_not_allowed(self, client):
        resp = _preflight(client, FOREIGN_ORIGIN)
        assert resp.headers.get("access-control-allow-origin") != FOREIGN_ORIGIN


class TestAllowedOrigin:

    def test_cors_headers_present(self, client):
        resp = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
        assert resp.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN

    def test_credentials_allowed(self, client):
        resp = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
        assert resp.headers.get("access-control-allow-credentials") == "true"


class TestMethodsAndHeadersAreExplicit:

    def test_allowed_method_passes(self, client):
        resp = _preflight(client, ALLOWED_ORIGIN, method="POST")
        assert resp.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN

    def test_disallowed_method_rejected(self, client):
        """PUT в API нет — preflight на него не должен разрешаться."""
        resp = _preflight(client, ALLOWED_ORIGIN, method="PUT")
        assert "PUT" not in resp.headers.get("access-control-allow-methods", "")

    def test_wildcard_not_echoed_for_methods(self, client):
        resp = _preflight(client, ALLOWED_ORIGIN)
        assert resp.headers.get("access-control-allow-methods") != "*"

    def test_chart_token_header_allowed(self, client):
        """X-Chart-Token нужен анонимному доступу к картам."""
        resp = _preflight(client, ALLOWED_ORIGIN, headers="x-chart-token")
        allowed = resp.headers.get("access-control-allow-headers", "").lower()
        assert "x-chart-token" in allowed

    def test_arbitrary_header_not_echoed(self, client):
        """Раньше ["*"] заставлял Starlette отражать любой запрошенный заголовок."""
        resp = _preflight(client, ALLOWED_ORIGIN, headers="x-totally-made-up")
        allowed = resp.headers.get("access-control-allow-headers", "").lower()
        assert "x-totally-made-up" not in allowed


class TestWildcardOriginRefusedAtStartup:

    def test_app_refuses_to_start(self):
        """С ALLOWED_ORIGINS='*' и credentials приложение не должно подниматься."""
        import os

        env = {
            "CORS_ORIGINS": "*",
            "DEBUG": "false",
            "TESTING": "false",
            "JWT_SECRET": "test-secret-not-the-default-placeholder",
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        }
        proc = subprocess.run(
            [sys.executable, "-c", "import backend.main"],
            capture_output=True, text=True, env=env, timeout=300,
        )
        assert proc.returncode != 0
        assert "ALLOWED_ORIGINS" in proc.stderr


class TestOriginParsing:
    """Origins задаются и JSON-массивом (как в .env), и списком через запятую."""

    def test_json_array_form(self):
        from backend.config import Settings

        s = Settings(cors_origins='["https://a.ru","https://b.ru"]')
        assert s.cors_origins_list == ["https://a.ru", "https://b.ru"]

    def test_comma_separated_form(self):
        from backend.config import Settings

        s = Settings(cors_origins="https://a.ru, https://b.ru")
        assert s.cors_origins_list == ["https://a.ru", "https://b.ru"]

    def test_json_form_has_no_stray_punctuation(self):
        """Раньше split(',') оставлял скобки и кавычки в origins."""
        from backend.config import Settings

        s = Settings(cors_origins='["https://a.ru","https://b.ru"]')
        for origin in s.cors_origins_list:
            assert not any(ch in origin for ch in '[]"')
