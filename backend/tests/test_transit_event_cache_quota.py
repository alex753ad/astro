"""Кэш-хит на /transits/event/interpret не должен списывать AI-квоту.

main.py:1696 (до правки) вызывал tier_limiter.commit_transit_ai в ветке
кэш-хита — модель не вызывается, платить не за что. Ключ кэша без
user_id и держится 30 суток, поэтому повторное открытие того же
транзита в пределах месяца списывало у Веги единицу из трёх ни за что.

Тест гоняет один и тот же транзит дважды: первый запрос — MISS,
реальная генерация (мокнутый движок), квота списывается; второй —
HIT из кэша, квота остаётся прежней.
"""

import pytest

from backend.tests.test_chart_access import _make_chart


TRANSIT_PLANET = "Mars"
NATAL_PLANET = "Sun"
ASPECT_TYPE = "conjunction"
PEAK_DATE = "2026-09-01"


class _FakeEngine:
    name = "fake"

    async def stream(self, request):
        for chunk in ("Разбор ", "готов."):
            yield chunk


class _FakeRouter:
    def __init__(self):
        self._engines = [_FakeEngine()]

    def _check_budget(self, name):
        return True

    def _track_spend(self, name, tokens):
        pass


@pytest.fixture
def fake_router(monkeypatch):
    router = _FakeRouter()
    monkeypatch.setattr(
        "backend.interpretation.router.get_router", lambda: router
    )
    return router


@pytest.fixture(autouse=True)
def clear_transit_interp_cache():
    from backend.cache import transit_interp_cache
    transit_interp_cache.clear()
    yield
    transit_interp_cache.clear()


@pytest.fixture
def user_lite(db, user_free):
    """Вега: частичный доступ — transits_ai_per_month = 3."""
    user_free.tier = "lite"
    db.commit()
    return user_free


def _post_event(client, chart_id, headers):
    return client.post(
        f"/api/v1/chart/{chart_id}/transits/event/interpret",
        json={
            "transit_planet": TRANSIT_PLANET,
            "natal_planet": NATAL_PLANET,
            "aspect_type": ASPECT_TYPE,
            "peak_date": PEAK_DATE,
        },
        headers=headers,
    )


class TestCacheHitDoesNotSpendQuota:
    def test_two_requests_for_the_same_transit_spend_quota_once(
        self, client, db, user_lite, auth_headers_free, fake_router
    ):
        from backend.auth.rate_limits import get_monthly_usage

        chart = _make_chart(db, user_id=user_lite.id)

        resp1 = _post_event(client, chart.id, auth_headers_free)
        assert resp1.status_code == 200
        # Тянем поток до конца — commit_transit_ai стоит после yield [DONE].
        resp1.read()

        db.expire_all()
        used_after_first = get_monthly_usage(db, str(user_lite.id), "transit_ai")
        assert used_after_first == 1, "первый запрос — реальная генерация, квота списывается"

        resp2 = _post_event(client, chart.id, auth_headers_free)
        assert resp2.status_code == 200
        resp2.read()

        db.expire_all()
        used_after_second = get_monthly_usage(db, str(user_lite.id), "transit_ai")
        assert used_after_second == 1, "второй запрос — кэш-хит, квота не должна расти"
