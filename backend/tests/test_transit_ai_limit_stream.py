"""Отказ по лимиту AI-транзитов доезжает до пользователя (SSE).

GET /chart/{id}/transits/interpret читается через EventSource
(streamTransitInterpretation → _connectSSE в frontend/src/api/client.js), а тот
не даёт JS доступа ни к коду ответа, ни к телу. Пока check_transit_ai_limit
отдавал HTTP 403 до открытия StreamingResponse, текст «AI-расшифровка транзитов
доступна на Лире и выше» до человека не доезжал вовсе: клиент делал три
реконнекта и показывал «Соединение прервалось».

Та же болезнь и то же лечение, что у /chart/{id}/interpret (коммит 4de1bc6).
Путь тоже не был покрыт тестами.

Соседний POST /transits/event/interpret сюда НЕ входит, и это не забывчивость:
он читается через fetch + ReadableStream (streamTransitEventInterpretation,
api/client.js:317), где resp.status и тело доступны JS. Там 403 не теряется
транспортом — его просто никто не читает: клиент идёт в resp.body.getReader()
без проверки resp.ok. Лечится на клиенте, а не переводом рабочего статуса в
200.
"""

import pytest

from backend.auth.rate_limits import increment_monthly_usage
from backend.tests.test_chart_access import _make_chart
from backend.tests.test_free_interpretation import _error_of, _events


def _url(chart_id):
    return (
        f"/api/v1/chart/{chart_id}/transits/interpret"
        "?from_date=2026-09-01&to_date=2026-09-30"
    )


def _interpret(client, chart_id, headers=None):
    return client.get(_url(chart_id), headers=headers or {})


@pytest.fixture
def no_engines(monkeypatch):
    """Ни один AI-движок не проходит проверку бюджета — эндпоинт уходит в
    шаблонный фолбэк. Нужен только для случаев, где гейт ПРОПУСКАЕТ: иначе
    тест полез бы в сеть за живой моделью."""
    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter._check_budget",
        lambda self, name: False,
    )


@pytest.fixture
def user_lite(db, user_free):
    """Вега: частичный доступ — transits_ai_per_month = 3."""
    user_free.tier = "lite"
    db.commit()
    return user_free


class TestFreeRefusalReachesTheUser:
    """Free: AI-разбор транзитов закрыт целиком. Отказ обязан быть виден."""

    def test_returns_200_not_403(self, client, db, user_free, auth_headers_free):
        chart = _make_chart(db, user_id=user_free.id)
        resp = _interpret(client, chart.id, auth_headers_free)
        assert resp.status_code == 200, "403 не доезжает через EventSource"

    def test_error_event_carries_the_backend_text(
        self, client, db, user_free, auth_headers_free
    ):
        chart = _make_chart(db, user_id=user_free.id)
        text = _error_of(_interpret(client, chart.id, auth_headers_free))
        assert text, "в потоке обязано быть событие с текстом отказа"
        # Формулировку дословно не проверяем — тексты живут в rate_limits.py и
        # меняются отдельно. Проверяем, что это объяснение, а не заглушка.
        assert len(text) > 20

    def test_no_done_and_no_content_on_refusal(
        self, client, db, user_free, auth_headers_free
    ):
        """[DONE] клиент считает успехом; текста разбора при отказе быть не должно."""
        chart = _make_chart(db, user_id=user_free.id)
        events = _events(_interpret(client, chart.id, auth_headers_free))
        assert not any(e.get("done") for e in events)
        assert not any("text" in e for e in events)


class TestLiteQuotaExhausted:
    """Вега: квота 3 в месяц. Исчерпание — 429, оно так же не доезжало."""

    def _exhaust(self, db, user):
        for _ in range(3):
            increment_monthly_usage(db, str(user.id), "transit_ai")

    def test_exhausted_quota_returns_200_with_error_event(
        self, client, db, user_lite, auth_headers_free
    ):
        chart = _make_chart(db, user_id=user_lite.id)
        self._exhaust(db, user_lite)

        resp = _interpret(client, chart.id, auth_headers_free)
        assert resp.status_code == 200
        assert _error_of(resp), "причина отказа обязана быть в потоке"

    def test_refusal_does_not_spend_quota(
        self, client, db, user_lite, auth_headers_free
    ):
        """До commit_transit_ai не доходим — счётчик не растёт."""
        from backend.auth.rate_limits import get_monthly_usage

        chart = _make_chart(db, user_id=user_lite.id)
        self._exhaust(db, user_lite)
        before = get_monthly_usage(db, str(user_lite.id), "transit_ai")

        _interpret(client, chart.id, auth_headers_free)

        db.expire_all()
        assert get_monthly_usage(db, str(user_lite.id), "transit_ai") == before


class TestGateStillLetsPaidThrough:
    """Приём не должен ломать разрешённый путь."""

    def test_pro_gets_content_and_done(
        self, client, db, user_pro, auth_headers_pro, no_engines
    ):
        chart = _make_chart(db, user_id=user_pro.id)
        resp = _interpret(client, chart.id, auth_headers_pro)

        assert resp.status_code == 200
        assert _error_of(resp) is None, "у Лиры отказа быть не должно"
        events = _events(resp)
        assert any("text" in e for e in events), "разрешённый путь обязан отдать текст"
        assert any(e.get("done") for e in events), "и завершиться [DONE]"


class TestAnonymousAndAccessOrder:
    """Аноним сохраняет настоящий 403; доступ к карте проверяется раньше лимита."""

    def test_anonymous_on_reachable_chart_gets_403(self, client, db):
        """Карта анонимная и доступ к ней есть — отказ приходит от лимита.

        Конвертировать этот 403 в 200 нельзя: для SSE он работает ещё и как
        отказ по аутентификации, на нём держится одноразовость тикета
        (test_sse_tickets.py).
        """
        chart = _make_chart(db, user_id=None, access_token="tok-anon-transits")
        resp = _interpret(client, chart.id, {"X-Chart-Token": "tok-anon-transits"})
        assert resp.status_code == 403
        assert _error_of(resp) is None, "аноним не должен получать событие в потоке"

    def test_foreign_chart_gives_404(self, client, db, user_free):
        """Проверка лимита переехала после resolve_chart_access, поэтому чужая
        карта закрывается раньше. Утечки нет — 404 одинаков на «нет карты» и
        «нет доступа»."""
        chart = _make_chart(db, user_id=user_free.id)
        assert _interpret(client, chart.id).status_code == 404
