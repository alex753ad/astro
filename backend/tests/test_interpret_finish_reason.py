"""finish_reason уезжает клиенту фактом, а не выводится из наличия [DONE].

До 09.09.2026 настоящий finish_reason провайдера наружу не выходил вовсе.
Клиент мог заключить «текст полон» только из того, что пришёл маркер [DONE]:
рассуждение верное (при finish_reason != "stop" роутер поднимает
IncompleteInterpretation и до [DONE] дело не доходит), но это вывод по чужому
коду, а не прочитанный факт. Любая будущая правка, начавшая отдавать [DONE] на
новом пути, сломала бы его молча.

⚠️ Главное, что стерегут эти тесты, — совместимость. Поле необязательное, и
старые клиенты обязаны его пережить: `_connectSSE` (`frontend/src/api/client.js`)
разбирает события по наличию `type`, `text` и `error`, а событие без всех трёх
молча отбрасывает. Поэтому событие ОТДЕЛЬНОЕ, а не поле внутри [DONE]: сам
[DONE] клиент сравнивает со строкой целиком, и любая добавка в него сломала бы
и веб, и мобильный разом.
"""

import json

import pytest

from backend.interpretation.router import IncompleteInterpretation
from backend.tests.test_chart_access import _make_chart


def _sse_url(chart_id):
    return f"/api/v1/chart/{chart_id}/interpret"


def _events(body: str) -> list:
    """Все data-события потока в порядке прихода, [DONE] отдельной строкой."""
    out = []
    for line in body.split("\n"):
        if line.startswith("data: "):
            out.append(line[6:].strip())
    return out


def _finish_values(body: str) -> list:
    vals = []
    for raw in _events(body):
        if raw == "[DONE]":
            continue
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        if isinstance(payload, dict) and "finish_reason" in payload:
            vals.append(payload["finish_reason"])
    return vals


@pytest.fixture
def stream_with_reason(monkeypatch):
    """Штатный поток, называющий и движок, и причину завершения — как в проде."""
    async def _stream(self, request):
        yield "Первая часть. "
        yield "Вторая часть."
        request.engine_used = "deepseek"
        request.finish_reason = "stop"

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.stream", _stream
    )


@pytest.fixture
def stream_without_reason(monkeypatch):
    """Роутер причину не выставил. Так ведёт себя любой путь, не знающий о
    новом поле, — событие всё равно обязано прийти, со значением null."""
    async def _stream(self, request):
        yield "Текст."
        request.engine_used = "template"

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.stream", _stream
    )


@pytest.fixture
def broken_stream(monkeypatch):
    async def _stream(self, request):
        yield "Начало, "
        raise IncompleteInterpretation("length")

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.stream", _stream
    )


class TestLiveStream:
    def test_reason_is_sent_and_is_the_real_one(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        assert _finish_values(body) == ["stop"]

    def test_reason_comes_before_done(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """Порядок важен: клиент закрывает соединение по [DONE], и событие,
        пришедшее после него, он уже не прочитает."""
        chart = _make_chart(db, user_id=user_pro.id)
        events = _events(client.get(_sse_url(chart.id), headers=auth_headers_pro).text)
        assert "[DONE]" in events
        reason_idx = next(i for i, e in enumerate(events) if "finish_reason" in e)
        assert reason_idx < events.index("[DONE]")

    def test_unknown_reason_is_null_not_missing(
        self, client, db, user_pro, auth_headers_pro, stream_without_reason
    ):
        """Причина неизвестна — событие всё равно приходит. Молча пропускать
        нельзя: клиент не отличил бы «не знаем» от «сломался транспорт»."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        assert _finish_values(body) == [None]

    def test_incomplete_stream_sends_no_reason_and_no_done(
        self, client, db, user_pro, auth_headers_pro, broken_stream
    ):
        """Оборванный поток не должен выглядеть завершённым ни по одному из
        двух признаков — ни [DONE], ни finish_reason."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        assert _finish_values(body) == []
        assert "[DONE]" not in _events(body)
        assert any("error" in e for e in _events(body))


class TestSavedInterpretation:
    def test_saved_text_also_reports_stop(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """Второй заход отдаёт сохранённый текст — и тоже называет причину.

        "stop" здесь факт, а не догадка: запись в БД делает
        _save_chart_interpretation после успешно завершённого цикла.
        """
        chart = _make_chart(db, user_id=user_pro.id)
        client.get(_sse_url(chart.id), headers=auth_headers_pro)  # первый — живой

        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        assert _finish_values(body) == ["stop"]


class TestOldClientsSurvive:
    """Поле необязательное. Эти тесты описывают ровно то, на что смотрит
    существующий разборщик клиента, — чтобы правка события не сломала его
    незаметно."""

    def test_event_has_no_type_text_or_error(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """Три ключа, по которым _connectSSE ветвится. Появись любой из них в
        этом событии — старый клиент принял бы служебное сообщение за часть
        разбора или за ошибку."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        payload = next(
            json.loads(e) for e in _events(body)
            if e != "[DONE]" and "finish_reason" in e
        )
        assert set(payload) == {"finish_reason"}

    def test_done_marker_is_untouched(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """[DONE] сравнивается клиентом со строкой целиком — он обязан
        остаться ровно таким же."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        assert "data: [DONE]\n\n" in body

    def test_text_events_unchanged(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """Сам разбор приходит теми же событиями, что и раньше."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        texts = [
            json.loads(e).get("text") for e in _events(body)
            if e != "[DONE]" and "text" in e
        ]
        assert "".join(t for t in texts if t) == "Первая часть. Вторая часть."
