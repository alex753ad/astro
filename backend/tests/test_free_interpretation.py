"""Бесплатный разбор Free — по одному на КАЖДУЮ сохранённую карту (048).

Путь до 28.08.2026 не был покрыт ни одним тестом (grep по
free_interpretation / check_interpretation_limit в tests/ не давал ничего),
хотя это единственная бесплатная выдача продукта и первая точка, где человек
упирается в тариф.

Ключ права — карта, а не аккаунт. Раньше users.free_interpretation_used гасил
разбор на весь аккаунт навсегда: у Free два слота под карты (profiles_limit),
то есть право построить вторую карту было, а разобрать её — нет.
"""

import pytest

from backend.models import NatalChart
from backend.tests.test_chart_access import _make_chart


def _sse_url(chart_id):
    return f"/api/v1/chart/{chart_id}/interpret"


@pytest.fixture
def fake_stream(monkeypatch):
    """Движки не дёргаем: проверяется гейт, а не генерация текста."""
    async def _stream(self, request):
        yield "Текст разбора."

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.stream", _stream
    )


def _interpret(client, chart_id, headers=None):
    return client.get(_sse_url(chart_id), headers=headers or {})


class TestFreeGetsOneInterpretationPerChart:
    """Ключ права — карта. Второй картой пользоваться можно."""

    def test_two_charts_get_two_interpretations(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        """Разбор первой карты не закрывает вторую.

        Порядок важен: после первого разбора гаснет и users.free_interpretation_used
        (его продолжают писать ради метрики «разбирал ли хоть раз»). Если бы
        гейтом остался он, второй запрос отказал бы — именно это и было до 048.
        """
        first = _make_chart(db, user_id=user_free.id)
        second = _make_chart(db, user_id=user_free.id)

        assert _interpret(client, first.id, auth_headers_free).status_code == 200
        assert _interpret(client, second.id, auth_headers_free).status_code == 200

    def test_flag_is_set_on_the_chart_that_was_interpreted(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        """Гасится флаг именно разобранной карты, соседняя не затронута."""
        first = _make_chart(db, user_id=user_free.id)
        second = _make_chart(db, user_id=user_free.id)

        assert _interpret(client, first.id, auth_headers_free).status_code == 200

        db.expire_all()
        assert db.get(NatalChart, first.id).free_interpretation_used is True
        assert db.get(NatalChart, second.id).free_interpretation_used is False


class TestSecondInterpretationOfSameChartRefused:
    """Право одно на карту: повторный разбор той же карты — отказ.

    «Третья карта» непроверяема: profiles_limit=2 отбивает создание раньше
    (main.py, POST /chart/calculate), поэтому реально достижимый отказ — именно
    повторный разбор.
    """

    def test_repeat_is_refused(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        chart = _make_chart(db, user_id=user_free.id)

        assert _interpret(client, chart.id, auth_headers_free).status_code == 200
        assert _interpret(client, chart.id, auth_headers_free).status_code == 403

    def test_refusal_does_not_consume_anything_further(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        """Отказ не трогает соседнюю карту — гасить нечего, до расхода не дошли."""
        chart = _make_chart(db, user_id=user_free.id)
        other = _make_chart(db, user_id=user_free.id)

        _interpret(client, chart.id, auth_headers_free)
        _interpret(client, chart.id, auth_headers_free)  # отказ

        db.expire_all()
        assert db.get(NatalChart, other.id).free_interpretation_used is False
        assert _interpret(client, other.id, auth_headers_free).status_code == 200


class TestDeletingChartRestoresTheRight:
    """Удалил карту, создал новую — разбор по новой доступен.

    Держится на cascade="all, delete-orphan" и на том, что флаг живёт в строке
    карты: удаление уносит его вместе с ней. Злоупотребить нечем — слотов всё
    равно profiles_limit.
    """

    def test_new_chart_after_deletion_is_interpretable(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        chart = _make_chart(db, user_id=user_free.id)
        assert _interpret(client, chart.id, auth_headers_free).status_code == 200
        assert _interpret(client, chart.id, auth_headers_free).status_code == 403

        deleted = client.delete(
            f"/api/v1/profile/charts/{chart.id}", headers=auth_headers_free
        )
        assert deleted.status_code == 200

        fresh = _make_chart(db, user_id=user_free.id)
        assert _interpret(client, fresh.id, auth_headers_free).status_code == 200


class TestChartAccessIsCheckedFirst:
    """Проверка лимита переехала ПОСЛЕ resolve_chart_access — карта нужна ей
    самой. Следствие: чужая карта закрывается раньше лимита."""

    def test_foreign_chart_gives_404_not_403(self, client, db, user_free, fake_stream):
        """До 048 лимит отбивал первым, и аноним получал 403 даже на карту,
        которой не существует. Утечки нет — resolve_chart_access отвечает 404
        одинаково на «нет карты» и «нет доступа»."""
        chart = _make_chart(db, user_id=user_free.id)
        assert _interpret(client, chart.id).status_code == 404

    def test_anonymous_on_reachable_chart_gets_403(self, client, db, fake_stream):
        """Карта анонимная и доступ к ней есть — отказ приходит именно от
        проверки лимита."""
        chart = _make_chart(db, user_id=None, access_token="tok-anon-interpret")
        resp = _interpret(client, chart.id, {"X-Chart-Token": "tok-anon-interpret"})
        assert resp.status_code == 403
