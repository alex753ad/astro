"""Бесплатный разбор Free — по одному на КАЖДУЮ сохранённую карту (048).

Путь до 28.08.2026 не был покрыт ни одним тестом (grep по
free_interpretation / check_interpretation_limit в tests/ не давал ничего),
хотя это единственная бесплатная выдача продукта и первая точка, где человек
упирается в тариф.

Два поведения проверяются здесь вместе, потому что это один путь:

1. Ключ права — карта, а не аккаунт. Раньше users.free_interpretation_used
   гасил разбор на весь аккаунт навсегда: у Free два слота под карты
   (profiles_limit), то есть право построить вторую карту было, а разобрать
   её — нет.

2. Отказ по лимиту доезжает до пользователя. check_interpretation_limit
   отдавал HTTP 403 ДО открытия StreamingResponse, а EventSource не даёт JS
   доступа ни к статусу, ни к телу — текст отказа не доходил вовсе, человек
   после трёх реконнектов видел «Соединение прервалось». Теперь ответ 200, а
   причина — первым событием в потоке.
"""

import json

import pytest

from backend.models import NatalChart
from backend.tests.test_chart_access import _make_chart


def _sse_url(chart_id):
    return f"/api/v1/chart/{chart_id}/interpret"


def _events(resp):
    """События SSE-ответа как список словарей."""
    out = []
    for line in resp.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            out.append({"done": True})
            continue
        try:
            out.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return out


def _error_of(resp):
    """Текст ошибки из потока или None, если поток нормальный."""
    for ev in _events(resp):
        if "error" in ev:
            return ev["error"]
    return None


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

        a = _interpret(client, first.id, auth_headers_free)
        assert a.status_code == 200
        assert _error_of(a) is None, "первый разбор не должен отказывать"

        b = _interpret(client, second.id, auth_headers_free)
        assert b.status_code == 200
        assert _error_of(b) is None, "по второй карте разбор обязан быть доступен"

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
        """Право потрачено и сохранённого текста нет — отказ.

        30.08.2026 смысл теста сузился. Раньше отказ приходил на ЛЮБОЕ
        повторное открытие карты, и это была та самая поломка: человек не мог
        перечитать разбор, который уже получил. Теперь сохранённый текст
        отдаётся без проверки лимита, поэтому гейт срабатывает только когда
        отдавать нечего — карты, разобранные до этой правки, и редкие случаи
        несохранившегося текста. Флаг ставим руками: через эндпоинт такое
        состояние воспроизвести уже нельзя.
        """
        chart = _make_chart(db, user_id=user_free.id)
        chart.free_interpretation_used = True
        db.commit()

        refused = _interpret(client, chart.id, auth_headers_free)
        assert _error_of(refused) is not None, "право потрачено, генерировать нельзя"

    def test_saved_interpretation_is_rereadable(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        """Своё перечитать можно, хотя право уже потрачено."""
        chart = _make_chart(db, user_id=user_free.id)

        assert _error_of(_interpret(client, chart.id, auth_headers_free)) is None

        second = _interpret(client, chart.id, auth_headers_free)
        assert _error_of(second) is None, "за этот текст уже заплачено"
        assert "Текст разбора." in second.text

    def test_refusal_does_not_consume_anything_further(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        """Отказ не трогает соседнюю карту — гасить нечего, до расхода не дошли."""
        chart = _make_chart(db, user_id=user_free.id)
        other = _make_chart(db, user_id=user_free.id)

        _interpret(client, chart.id, auth_headers_free)
        _interpret(client, chart.id, auth_headers_free)  # отдаётся сохранённый

        db.expire_all()
        assert db.get(NatalChart, other.id).free_interpretation_used is False
        assert _error_of(_interpret(client, other.id, auth_headers_free)) is None


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
        assert _error_of(_interpret(client, chart.id, auth_headers_free)) is None
        assert _error_of(_interpret(client, chart.id, auth_headers_free)) is not None

        deleted = client.delete(
            f"/api/v1/profile/charts/{chart.id}", headers=auth_headers_free
        )
        assert deleted.status_code == 200

        fresh = _make_chart(db, user_id=user_free.id)
        assert _error_of(_interpret(client, fresh.id, auth_headers_free)) is None


class TestRefusalReachesTheUser:
    """Блок 2: отказ по лимиту — 200 и событие в потоке, а не 403.

    EventSource не показывает JS ни код ответа, ни тело. Пока это был 403,
    текст «Вы использовали бесплатную интерпретацию…» до человека не доезжал.
    """

    def test_exhausted_limit_returns_200_not_403(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        chart = _make_chart(db, user_id=user_free.id)
        _interpret(client, chart.id, auth_headers_free)

        second = _interpret(client, chart.id, auth_headers_free)
        assert second.status_code == 200, "403 не доезжает через EventSource"

    def test_error_event_carries_the_backend_text(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        chart = _make_chart(db, user_id=user_free.id)
        _interpret(client, chart.id, auth_headers_free)

        text = _error_of(_interpret(client, chart.id, auth_headers_free))
        assert text, "в потоке обязано быть событие с текстом отказа"
        # Формулировку не проверяем дословно — тексты живут в rate_limits.py и
        # меняются отдельно. Проверяем, что это объяснение, а не заглушка.
        assert len(text) > 20

    def test_no_done_event_on_refusal(
        self, client, db, user_free, auth_headers_free, fake_stream
    ):
        """[DONE] клиент считает успехом — при отказе его быть не должно."""
        chart = _make_chart(db, user_id=user_free.id)
        _interpret(client, chart.id, auth_headers_free)

        events = _events(_interpret(client, chart.id, auth_headers_free))
        assert not any(e.get("done") for e in events)
        assert not any("text" in e for e in events), "текста разбора при отказе быть не должно"


class TestAnonymousStillGetsRealForbidden:
    """Аноним — исключение: ему по-прежнему настоящий 403, а не событие в потоке.

    Для SSE этот статус работает ещё и как отказ по аутентификации (ходят по
    одноразовому тикету), и на нём держится одноразовость тикета —
    test_sse_tickets.py::test_ticket_is_single_use ловит именно != 200.
    Конвертировать его в 200 нельзя.
    """

    def test_anonymous_gets_403_on_reachable_chart(self, client, db, fake_stream):
        """Карта анонимная и доступ к ней есть — отказ приходит именно от
        проверки лимита, а не от resolve_chart_access."""
        chart = _make_chart(db, user_id=None, access_token="tok-anon-interpret")
        resp = _interpret(client, chart.id, {"X-Chart-Token": "tok-anon-interpret"})
        assert resp.status_code == 403
        assert _error_of(resp) is None, "аноним не должен получать событие в потоке"

    def test_anonymous_gets_404_on_foreign_chart(self, client, db, user_free, fake_stream):
        """Чужая карта закрывается раньше лимита — 404, а не 403.

        Это следствие перестановки check_interpretation_limit после
        resolve_chart_access (048): до неё лимит отбивал первым и аноним
        получал 403 даже на карту, которой не существует. Утечки нет —
        resolve_chart_access отвечает 404 одинаково на «нет карты» и «нет
        доступа».
        """
        chart = _make_chart(db, user_id=user_free.id)
        assert _interpret(client, chart.id).status_code == 404
