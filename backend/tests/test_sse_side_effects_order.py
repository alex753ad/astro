"""Побочные действия SSE выполняются ДО последнего чанка, а не после.

Почему обычный тест этого не ловит
──────────────────────────────────
`TestClient` не рвёт соединение. Его транспорт (starlette/testclient.py,
`_TestClientTransport.handle_request`) складывает весь ответ в io.BytesIO и
только потом отдаёт его тесту, а `receive()` ждёт `response_complete`, прежде
чем вернуть `http.disconnect`. То есть приложение ВСЕГДА досматривается до
конца, и код после `yield "data: [DONE]"` там исполняется.

Браузер ведёт себя иначе: `_connectSSE` (frontend/src/api/client.js) на
событии `[DONE]` немедленно зовёт `eventSource.close()`. Starlette на
`http.disconnect` отменяет группу задач вместе с итератором тела
(starlette/responses.py, `StreamingResponse.__call__`), генератор снимается
прямо на `yield`, и всё, что написано ниже, не выполняется никогда.

Из-за этого расхождения на проде молча не работали: сохранение разбора,
списание бесплатного права, месячные счётчики и кэш разбора транзита — при
зелёных тестах.

Что делает этот файл
────────────────────
Гоняет ASGI-приложение напрямую, мимо TestClient, с собственными receive/send:
как только в `send` приходит чанк с `[DONE]`, receive отдаёт
`http.disconnect`. Это ровно то, что делает браузер.

Проверяется не «функция сохранения работает, если её вызвать», а «к моменту
последнего чанка работа уже сделана».
"""

from __future__ import annotations

import anyio
import pytest

from backend.main import app
from backend.models import Interpretation, NatalChart
from backend.tests.test_chart_access import _make_chart


async def _drive_until_done(scope) -> list[bytes]:
    """Прогнать ASGI-запрос, оборвав соединение сразу после [DONE].

    Возвращает отданные чанки. Отмена итератора тела — не ошибка теста, а
    воспроизведение браузера, поэтому anyio.CancelledError гасится.
    """
    chunks: list[bytes] = []
    disconnect = anyio.Event()
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        # Держим соединение открытым, пока не увидим [DONE].
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            body = message.get("body", b"")
            if body:
                chunks.append(body)
            if b"[DONE]" in body:
                disconnect.set()
                # Пауза, а не sleep(0): нужно, чтобы listen_for_disconnect
                # ГАРАНТИРОВАННО успел проснуться, вернуться из receive() и
                # отменить группу задач, пока stream_response ждёт здесь.
                # С sleep(0) исход зависел бы от планировщика, и на сломанном
                # порядке тест мог бы позеленеть — то есть снова проверять не
                # то. Отмена приходит прямо в этот await, и генератор больше
                # не возобновляется — как при eventSource.close() в браузере.
                await anyio.sleep(0.05)

    with anyio.move_on_after(20):
        try:
            await app(scope, receive, send)
        except anyio.get_cancelled_exc_class():
            pass

    return chunks


def _scope(path: str, headers: dict[str, str]):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in headers.items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }


@pytest.fixture
def full_stream(monkeypatch):
    async def _stream(self, request):
        yield "Разбор карты, "
        yield "доставленный целиком."
        request.engine_used = "deepseek"

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.stream", _stream
    )


class TestNatalInterpretationOrder:
    """Разбор натальной карты — путь, на котором дефект и обнаружился."""

    async def test_row_exists_by_the_time_done_is_sent(
        self, client, db, user_pro, auth_headers_pro, full_stream
    ):
        """Главный тест. На прежнем порядке строки не будет: генератор
        снимается на [DONE], и сохранение не успевает выполниться."""
        chart = _make_chart(db, user_id=user_pro.id)

        chunks = await _drive_until_done(
            _scope(f"/api/v1/chart/{chart.id}/interpret", auth_headers_pro)
        )

        body = b"".join(chunks).decode("utf-8")
        assert "[DONE]" in body, "поток не дошёл до конца — тест проверяет не то"
        assert "доставленный целиком." in body

        db.expire_all()
        rows = db.query(Interpretation).filter(
            Interpretation.chart_id == chart.id
        ).all()
        assert len(rows) == 1, (
            "разбор не сохранён к моменту последнего чанка — побочное действие "
            "стоит ПОСЛЕ yield [DONE] и снимается вместе с генератором"
        )

    async def test_free_right_is_spent_by_the_time_done_is_sent(
        self, client, db, user_free, auth_headers_free, full_stream
    ):
        """Тот же дефект гасил и списание права: на проде
        free_interpretation_used не выставлялся никогда."""
        chart = _make_chart(db, user_id=user_free.id)

        await _drive_until_done(
            _scope(f"/api/v1/chart/{chart.id}/interpret", auth_headers_free)
        )

        db.expire_all()
        assert db.get(NatalChart, chart.id).free_interpretation_used is True


class TestBrokenStreamStillSavesNothing:
    """Перенос выше [DONE] не должен превратить обрыв в сохранение."""

    async def test_incomplete_stream_leaves_no_row(
        self, client, db, user_pro, auth_headers_pro, monkeypatch
    ):
        from backend.interpretation.router import IncompleteInterpretation

        async def _broken(self, request):
            yield "Начало разбора, "
            raise IncompleteInterpretation("connection_lost")

        monkeypatch.setattr(
            "backend.interpretation.router.InterpretationRouter.stream", _broken
        )
        chart = _make_chart(db, user_id=user_pro.id)

        await _drive_until_done(
            _scope(f"/api/v1/chart/{chart.id}/interpret", auth_headers_pro)
        )

        db.expire_all()
        assert db.query(Interpretation).filter(
            Interpretation.chart_id == chart.id
        ).all() == [], "половина разбора не должна попадать в базу"
