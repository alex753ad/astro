"""Регрессия C-2: служебные /api/v1/internal/* закрыты при любом INTERNAL_SECRET.

Раньше в каждом таком роутере стояло `if secret and x_internal_secret != secret`.
Пустой INTERNAL_SECRET означал, что проверка пропускается целиком, и наружу
оказывались открыты выдача pilot-токена (эскалация до premium на 30 дней),
массовые рассылки через Resend и постановка Celery-задач.

Проверяем оба состояния переменной. Ключевой случай — именно ПУСТОЙ секрет:
при нём старый код отвечал 2xx.
"""

import os
from unittest.mock import patch

import pytest


# Все шесть ручек из аудита. Держать список полным важно: новая ручка в
# роутере /internal без строки здесь останется непроверенной.
INTERNAL_ENDPOINTS = [
    "/api/v1/internal/pilot-token",
    "/api/v1/internal/onboarding-emails",
    "/api/v1/internal/weekly-digest",
    "/api/v1/internal/lunar-returns",
    "/api/v1/internal/push-tick",
    "/api/v1/internal/pilot-tick",
]

SECRET = "internal-secret-for-tests-0123456789"  # gitleaks:allow — тестовая фикстура, не реальный секрет


@pytest.fixture
def with_secret():
    with patch.dict(os.environ, {"INTERNAL_SECRET": SECRET}):
        yield SECRET


@pytest.fixture
def without_secret():
    # Именно удаление, а не пустая строка: так ведёт себя невыставленная
    # переменная в свежем окружении.
    saved = os.environ.pop("INTERNAL_SECRET", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["INTERNAL_SECRET"] = saved


class TestSecretConfigured:
    """Секрет задан — пускаем только с правильным заголовком."""

    @pytest.mark.parametrize("path", INTERNAL_ENDPOINTS)
    def test_no_header_rejected(self, client, with_secret, path):
        assert client.post(path).status_code == 403

    @pytest.mark.parametrize("path", INTERNAL_ENDPOINTS)
    def test_wrong_header_rejected(self, client, with_secret, path):
        resp = client.post(path, headers={"X-Internal-Secret": "wrong"})
        assert resp.status_code == 403

    def test_correct_header_passes_authz(self, client, with_secret):
        """С верным секретом дальше уже дело самой ручки, но не 403."""
        resp = client.post(
            "/api/v1/internal/pilot-token",
            headers={"X-Internal-Secret": SECRET},
            json={"tg_user_id": "12345"},
        )
        assert resp.status_code != 403


class TestSecretMissing:
    """Секрета нет — 503, а не «проходите».

    Это и есть исправление fail-open: отсутствие конфигурации теперь ошибка
    конфигурации, а не молчаливое разрешение.
    """

    @pytest.mark.parametrize("path", INTERNAL_ENDPOINTS)
    def test_no_header_not_allowed(self, client, without_secret, path):
        resp = client.post(path)
        assert resp.status_code == 503
        assert resp.status_code < 200 or resp.status_code >= 300

    @pytest.mark.parametrize("path", INTERNAL_ENDPOINTS)
    def test_any_header_not_allowed(self, client, without_secret, path):
        """Подобрать «пустой» секрет тоже нельзя."""
        for candidate in ("", "wrong", SECRET):
            resp = client.post(path, headers={"X-Internal-Secret": candidate})
            assert resp.status_code == 503, f"{path} с секретом {candidate!r}"


class TestPrivilegeEscalationPath:
    """Цепочка из аудита: pilot-token -> claim -> tier=premium.

    Проверяем самое начало цепочки — без него остальное недостижимо.
    """

    def test_pilot_token_not_issued_without_secret(self, client, without_secret):
        resp = client.post(
            "/api/v1/internal/pilot-token", json={"tg_user_id": "any-value"}
        )
        assert resp.status_code == 503
        assert "token" not in resp.json()
