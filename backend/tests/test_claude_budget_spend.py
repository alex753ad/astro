"""Прямой вызов Anthropic записывает свой расход в общий суточный бюджет.

До правки списание было ровно одно на всё приложение —
interpretation/router.py (_track_spend), то есть считались только
интерпретации натальных карт. Прямые вызовы моделей бюджет СПРАШИВАЛИ, но не
пополняли, и суточный потолок упирался позже, чем деньги реально кончались.

Раньше проверялось на /forecast/daily. Эти ручки удалены 23.09.2026, и
единственный потребитель контура Claude теперь — общий астрокалендарь
(/calendar/monthly); проверка переехала на него. Каждый тест берёт свой
месяц: ответ календаря кэшируется по месяцу, и общий месяц отдал бы второму
тесту кэш без вызова модели.
"""

import pytest


def _fake_client(monkeypatch, payload: dict):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _Resp:
        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr("httpx.AsyncClient", _Client)


@pytest.fixture
def spend_log(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "backend.cache.budget_tracker.add_spend",
        lambda amount: calls.append(amount) or amount,
    )
    monkeypatch.setattr("backend.cache.interpretation_cache.get", lambda key: None)
    return calls


_WITH_USAGE = {
    "content": [{"text": '{"summary": "тест"}'}],
    "usage": {"input_tokens": 2000, "output_tokens": 800},
}


def test_calendar_records_spend(client, monkeypatch, spend_log):
    _fake_client(monkeypatch, _WITH_USAGE)
    resp = client.get("/api/v1/calendar/monthly?month=2031-01")
    assert resp.status_code == 200, resp.text
    assert spend_log, "вызов Anthropic не записал расход в бюджет"
    assert spend_log[0] > 0


def test_spend_matches_provider_usage(client, monkeypatch, spend_log):
    """Сумма считается из usage провайдера, а не оценкой.

    2000 входных по $3/M + 800 выходных по $15/M = $0.018. Проверяем именно
    это число: если кто-то заменит usage на прикидку «по длине текста»,
    тест упадёт.
    """
    _fake_client(monkeypatch, _WITH_USAGE)
    client.get("/api/v1/calendar/monthly?month=2031-02")
    expected = 2000 * (3.0 / 1_000_000) + 800 * (15.0 / 1_000_000)
    assert spend_log[0] == pytest.approx(expected)


def test_no_usage_means_no_spend(client, monkeypatch, spend_log):
    """Ответ без usage — не повод выдумывать число: выдуманный расход молча
    смещает общий потолок для всех остальных контуров."""
    _fake_client(monkeypatch, {"content": [{"text": '{"summary": "тест"}'}]})
    client.get("/api/v1/calendar/monthly?month=2031-03")
    assert spend_log == [], "расход записан при отсутствии usage"
