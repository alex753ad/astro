"""GET /calendar/monthly — без модели, знаки фаз кодом, кэш.

Ручка анонимная. До 03.10.2026 ходила в claude-sonnet-4 на каждый запрос
(потом — с кэшем и бюджетом), а из ответа модели веб брал только знаки
новолуния и полнолуния, уже известные коду. Шаг 6 аудита (04.10.2026):
вызова модели нет вовсе — тест держит, что ручка не ходит в сеть.
"""

import pytest

from backend.cache import interpretation_cache

MONTH = "2031-07"
CACHE_KEY = "general_calendar:code1:2031-07"
EVENTS = [
    {"date": "2031-07-04", "type": "full_moon", "sign": "Козерог"},
    {"date": "2031-07-19", "type": "new_moon", "sign": "Рак"},
    {"date": "2031-07-20", "type": "ingress", "sign": "Лев"},
]


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    interpretation_cache.delete(CACHE_KEY)
    calls = {"n": 0}

    def fake_calendar(y, m):
        calls["n"] += 1
        return EVENTS

    class _NoNet:
        def __init__(self, *a, **kw):
            raise AssertionError("/calendar/monthly не ходит в сеть")

    monkeypatch.setattr("httpx.AsyncClient", _NoNet)
    monkeypatch.setattr("backend.main.get_monthly_calendar", fake_calendar)
    yield calls
    interpretation_cache.delete(CACHE_KEY)


def test_signs_computed_without_model(client):
    r = client.get(f"/api/v1/calendar/monthly?month={MONTH}")
    assert r.status_code == 200
    assert r.json()["overview"] == {"new_moon": {"sign": "Рак"}, "full_moon": {"sign": "Козерог"}}


def test_works_with_exhausted_budget(client, monkeypatch):
    monkeypatch.setattr("backend.cache.budget_tracker.is_within_budget", lambda *a, **kw: False)
    assert client.get(f"/api/v1/calendar/monthly?month={MONTH}").status_code == 200


def test_second_request_from_cache(client, clean_cache):
    first = client.get(f"/api/v1/calendar/monthly?month={MONTH}").json()
    second = client.get(f"/api/v1/calendar/monthly?month={MONTH}").json()
    assert first == second and clean_cache["n"] == 1
