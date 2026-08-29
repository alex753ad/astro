"""Прогнозы записывают свой расход в общий суточный бюджет.

До правки списание было ровно одно на всё приложение —
interpretation/router.py:429 (_track_spend), то есть считались только
интерпретации натальных карт. Прогнозы, чат Астреи, CRM и расширенные карты
бюджет СПРАШИВАЛИ (13 проверок), но не пополняли.

Практическое следствие было такое: суточный потолок считал одну статью из
четырёх и упирался позже, чем деньги реально кончались — тем сильнее, чем
активнее чат и прогнозы.

Здесь проверяется дневной прогноз как представитель контура «прямой вызов
Anthropic мимо InterpretationRouter». Соседние weekly/monthly устроены
идентично (те же две ветки: Anthropic, затем фолбэк на OpenAI).
"""

import pytest

from backend.tests.test_chart_access import _make_chart


# user_pro / auth_headers_pro берутся из conftest (Лира: AI-транзиты без
# квоты — гейт check_transit_ai_limit пропускает, и тест доходит до вызова
# модели, а не отбивается лимитом раньше). Своей одноимённой фикстуры здесь
# быть не должно: она бы молча подменила ту, которую видит auth_headers_pro.


@pytest.fixture
def fake_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _Resp:
        def json(self):
            return {
                "content": [{"text": '{"summary": "тест"}'}],
                "usage": {"input_tokens": 2000, "output_tokens": 800},
            }

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
    return calls


def test_daily_forecast_records_spend(
    client, db, user_pro, auth_headers_pro, fake_anthropic, spend_log
):
    chart = _make_chart(db, user_id=user_pro.id)

    resp = client.get(
        f"/api/v1/chart/{chart.id}/forecast/daily?on_date=2026-09-15",
        headers=auth_headers_pro,
    )

    assert resp.status_code == 200, resp.text
    assert spend_log, "прогноз не записал расход в бюджет"
    assert spend_log[0] > 0


def test_spend_matches_provider_usage(
    client, db, user_pro, auth_headers_pro, fake_anthropic, spend_log
):
    """Сумма считается из usage провайдера, а не оценкой.

    2000 входных по $3/M + 800 выходных по $15/M = $0.018. Проверяем именно
    это число: если кто-то заменит usage на прикидку «по длине текста»,
    тест упадёт.
    """
    chart = _make_chart(db, user_id=user_pro.id)

    client.get(
        f"/api/v1/chart/{chart.id}/forecast/daily?on_date=2026-09-15",
        headers=auth_headers_pro,
    )

    expected = 2000 * (3.0 / 1_000_000) + 800 * (15.0 / 1_000_000)
    assert spend_log[0] == pytest.approx(expected)


def test_no_usage_means_no_spend(
    client, db, user_pro, auth_headers_pro, monkeypatch, spend_log
):
    """Ответ без usage — не повод выдумывать число.

    Выдуманный расход хуже пропущенного: он молча смещает общий потолок для
    всех остальных контуров.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _Resp:
        def json(self):
            return {"content": [{"text": '{"summary": "тест"}'}]}

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
    chart = _make_chart(db, user_id=user_pro.id)

    client.get(
        f"/api/v1/chart/{chart.id}/forecast/daily?on_date=2026-09-15",
        headers=auth_headers_pro,
    )

    assert spend_log == [], "расход записан при отсутствии usage"
