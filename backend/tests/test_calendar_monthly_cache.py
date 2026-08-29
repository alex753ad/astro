"""GET /calendar/monthly — кэш и суточный бюджет.

Ручка анонимная (ни одной auth-зависимости) и до правки ходила в
claude-sonnet-4 с max_tokens=3000 на КАЖДЫЙ запрос, без кэша и без проверки
бюджета. Это была единственная точка, где посторонний мог тратить деньги
владельца в цикле, ограниченный только rate_limit_anon.

Порядок здесь важен и проверяется отдельно: кэш стоит ДО проверки бюджета,
потому что попадание в кэш ничего не тратит — упирать его в исчерпанный
бюджет значило бы гасить и бесплатную выдачу.
"""

import pytest

from backend.cache import interpretation_cache
from backend.transit.forecast_prompt import GENERAL_CALENDAR_PROMPT_VERSION


MONTH = "2031-07"
# Ключ собирается из версии промпта, а не пишется литералом: иначе поднятие
# GENERAL_CALENDAR_PROMPT_VERSION молча расходило бы тест с кодом, и тест
# начал бы проверять ключ, которого никто не пишет.
CACHE_KEY = f"general_calendar:v{GENERAL_CALENDAR_PROMPT_VERSION}:2031-07"


@pytest.fixture(autouse=True)
def clean_cache():
    interpretation_cache.delete(CACHE_KEY)
    yield
    interpretation_cache.delete(CACHE_KEY)


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Считает обращения к Anthropic. Возвращает ответ в форме провайдера,
    вместе с usage — иначе расход не записался бы (см. track_claude_spend)."""
    calls = {"n": 0}

    class _Resp:
        def json(self):
            return {
                "content": [{"text": '{"overview": "тест"}'}],
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("httpx.AsyncClient", _Client)
    # Эфемериды здесь ни при чём — проверяем кэш и бюджет, а не расчёт.
    monkeypatch.setattr("backend.main.get_monthly_calendar", lambda y, m: [])
    return calls


class TestCache:
    def test_second_request_does_not_hit_llm(self, client, fake_anthropic):
        first = client.get(f"/api/v1/calendar/monthly?month={MONTH}")
        assert first.status_code == 200
        assert fake_anthropic["n"] == 1

        second = client.get(f"/api/v1/calendar/monthly?month={MONTH}")
        assert second.status_code == 200
        # Ровно это и было дырой: каждый запрос уходил в LLM заново.
        assert fake_anthropic["n"] == 1, "второй запрос того же месяца ушёл в LLM"
        assert second.json() == first.json()

    def test_cache_entry_is_written(self, client, fake_anthropic):
        client.get(f"/api/v1/calendar/monthly?month={MONTH}")
        assert interpretation_cache.get(CACHE_KEY) is not None


class TestPromptVersionInvalidatesCache:
    def test_version_bump_changes_the_key(self, client, fake_anthropic):
        """Поднятие версии промпта обнуляет кэш само, без чистки ключей руками.

        Проверяем не сам факт другого ключа (это тавтология), а следствие:
        после поднятия версии запрос снова идёт в LLM.
        """
        client.get(f"/api/v1/calendar/monthly?month={MONTH}")
        assert fake_anthropic["n"] == 1

        from backend.transit import forecast_prompt

        bumped = GENERAL_CALENDAR_PROMPT_VERSION + 1
        original = forecast_prompt.GENERAL_CALENDAR_PROMPT_VERSION
        forecast_prompt.GENERAL_CALENDAR_PROMPT_VERSION = bumped
        try:
            client.get(f"/api/v1/calendar/monthly?month={MONTH}")
            assert fake_anthropic["n"] == 2, "правка промпта не сбросила кэш"
        finally:
            forecast_prompt.GENERAL_CALENDAR_PROMPT_VERSION = original
            interpretation_cache.delete(f"general_calendar:v{bumped}:2031-07")


class TestBudget:
    def test_exhausted_budget_returns_503(self, client, monkeypatch, fake_anthropic):
        monkeypatch.setattr(
            "backend.cache.budget_tracker.is_within_budget",
            lambda *a, **kw: False,
        )
        resp = client.get(f"/api/v1/calendar/monthly?month={MONTH}")

        assert resp.status_code == 503
        # Та же формулировка, что у соседних прогнозных ручек — свой ответ
        # здесь не изобретался.
        assert "лимит" in resp.json()["detail"].lower()
        assert fake_anthropic["n"] == 0, "при исчерпанном бюджете в LLM ходить нельзя"

    def test_cache_hit_survives_exhausted_budget(self, client, monkeypatch, fake_anthropic):
        """Кэш ДО бюджета: уже посчитанный месяц отдаётся и при нуле на счету."""
        first = client.get(f"/api/v1/calendar/monthly?month={MONTH}")
        assert first.status_code == 200

        monkeypatch.setattr(
            "backend.cache.budget_tracker.is_within_budget",
            lambda *a, **kw: False,
        )
        second = client.get(f"/api/v1/calendar/monthly?month={MONTH}")

        assert second.status_code == 200
        assert second.json() == first.json()


class TestSpendIsRecorded:
    def test_successful_generation_adds_spend(self, client, monkeypatch, fake_anthropic):
        """Проверка бюджета без списания смещает потолок для всех контуров."""
        spent = []
        monkeypatch.setattr(
            "backend.cache.budget_tracker.add_spend",
            lambda amount: spent.append(amount) or amount,
        )

        resp = client.get(f"/api/v1/calendar/monthly?month={MONTH}")

        assert resp.status_code == 200
        assert spent, "расход не записан"
        assert spent[0] > 0
