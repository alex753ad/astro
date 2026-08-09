"""Регрессия №8 (аудит от 09.08): /forecast/daily|weekly|monthly вызывали
Claude/GPT-4o без тарифного гейта и без дневного бюджета — единственным
ограничением был общий IP-лимит 30/минуту, то есть Free-пользователь мог
делать неограниченное число дорогих AI-вызовов.

Прогноз — та же тарифная категория, что и AI-расшифровка транзитов
(`tier_limiter.check_transit_ai_limit` уже применяется на соседнем
`/transits/interpret`), поэтому переиспользуем существующий гейт, а не
изобретаем новый.

Оба внешних провайдера (ANTHROPIC_API_KEY, OPENAI_API_KEY) должны быть пусты
в этих тестах, независимо от окружения запуска: иначе тест, прошедший гейт,
попытается дернуть настоящий api.anthropic.com.
"""

import pytest


ENDPOINTS = [
    "/api/v1/chart/{chart_id}/forecast/daily?on_date=2026-08-15",
    "/api/v1/chart/{chart_id}/forecast/weekly?week_start=2026-08-10&week_end=2026-08-16",
    "/api/v1/chart/{chart_id}/forecast/monthly?from_date=2026-08-01&to_date=2026-08-31",
]


@pytest.fixture(autouse=True)
def no_ai_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def created_chart_pro(client, mock_calculator, mock_geo, auth_headers_pro):
    """Карта, принадлежащая Pro-пользователю — created_chart из conftest.py
    привязана к user_free, а BOLA-защита (resolve_chart_access) корректно
    отдаёт 404 на чужую карту вне зависимости от тарифа. Нужна своя."""
    resp = client.post(
        "/api/v1/chart/calculate",
        json={
            "birth_date": "1990-01-10",
            "birth_time": "12:00",
            "birth_place": "Moscow",
            "house_system": "placidus",
        },
        headers=auth_headers_pro,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


class TestFreeTierBlocked:
    """Раньше Free проходил без единой проверки тарифа."""

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_free_user_gets_403(self, client, created_chart, auth_headers_free, path):
        resp = client.get(path.format(chart_id=created_chart), headers=auth_headers_free)
        assert resp.status_code == 403

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_anonymous_gets_403_on_own_anonymous_chart(self, client, mock_calculator, mock_geo, path):
        """Анонимная (непривязанная) карта, доступ по capability-токену —
        check_transit_ai_limit трактует отсутствие user как tier=free."""
        create = client.post(
            "/api/v1/chart/calculate",
            json={
                "birth_date": "1990-01-10", "birth_time": "12:00",
                "birth_place": "Moscow", "house_system": "placidus",
            },
        )
        assert create.status_code == 200
        body = create.json()
        chart_id, token = body["id"], body.get("access_token")

        headers = {"X-Chart-Token": token} if token else {}
        resp = client.get(path.format(chart_id=chart_id), headers=headers)
        assert resp.status_code == 403


class TestProTierPassesGate:
    """Pro проходит тарифный гейт — дальше упирается в отсутствие API-ключа
    (503), а не в 403. Это подтверждает, что именно тарифная проверка была
    единственным новым барьером, а не побочный эффект."""

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_pro_user_passes_tier_check(self, client, created_chart_pro, auth_headers_pro, path):
        resp = client.get(path.format(chart_id=created_chart_pro), headers=auth_headers_pro)
        assert resp.status_code != 403
        assert resp.status_code == 503  # AI недоступен — ключей нет


class TestBudgetExhausted:

    def test_pro_user_blocked_when_daily_budget_spent(
        self, client, created_chart_pro, auth_headers_pro, monkeypatch
    ):
        from backend.cache import budget_tracker

        monkeypatch.setattr(budget_tracker, "get_spent", lambda: 10_000.0)
        resp = client.get(
            f"/api/v1/chart/{created_chart_pro}/forecast/daily?on_date=2026-08-15",
            headers=auth_headers_pro,
        )
        assert resp.status_code == 503
        assert "лимит" in resp.json()["detail"].lower()
