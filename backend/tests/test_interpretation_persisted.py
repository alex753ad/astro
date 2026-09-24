"""SSE-разбор карты сохраняется в Interpretation и отдаётся повторно.

До 30.08.2026 строку в Interpretation писали ТОЛЬКО PDF-пути (main.py и
tasks.py). SSE-путь не писал ничего, поэтому прочитанный на экране разбор
нигде не оставался: закрыл вкладку — текст исчез, а право на него сгорело
(chart.free_interpretation_used). Перечитать свой разбор было нельзя ни на
одном тарифе.

Следствие, из-за которого это и вскрылось: бесплатный PDF был недостижим.
Free читал разбор, жал «Скачать PDF», PDF-путь не находил строки в базе,
шёл генерировать заново и упирался в уже потраченное право.
"""

import pytest

from backend.auth.rate_limits import get_monthly_usage
from backend.interpretation.router import IncompleteInterpretation
from backend.models import Interpretation
from backend.tests.test_chart_access import _make_chart


def _sse_url(chart_id):
    return f"/api/v1/chart/{chart_id}/interpret"


def _rows(db, chart_id):
    return db.query(Interpretation).filter(Interpretation.chart_id == chart_id).all()


@pytest.fixture
def full_stream(monkeypatch):
    """Штатно завершённый поток: роутер называет движок, как в проде."""
    async def _stream(self, request):
        yield "Первая часть. "
        yield "Вторая часть."
        request.engine_used = "deepseek"

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.stream", _stream
    )


@pytest.fixture
def broken_stream(monkeypatch):
    """Поток оборвался после части текста — ровно тот случай, когда
    router.stream() поднимает IncompleteInterpretation."""
    async def _stream(self, request):
        yield "Начало разбора, "
        raise IncompleteInterpretation("connection_lost")

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.stream", _stream
    )


class TestSaved:
    def test_completed_stream_is_persisted(
        self, client, db, user_pro, auth_headers_pro, full_stream
    ):
        chart = _make_chart(db, user_id=user_pro.id)

        client.get(_sse_url(chart.id), headers=auth_headers_pro)

        rows = _rows(db, chart.id)
        assert len(rows) == 1
        assert rows[0].content == "Первая часть. Вторая часть."

    def test_engine_is_the_real_one(
        self, client, db, user_pro, auth_headers_pro, full_stream
    ):
        """Не «pdf» и не заглушка — иначе учёт разъедется."""
        chart = _make_chart(db, user_id=user_pro.id)

        client.get(_sse_url(chart.id), headers=auth_headers_pro)

        assert _rows(db, chart.id)[0].engine == "deepseek"

    def test_broken_stream_leaves_no_row(
        self, client, db, user_pro, auth_headers_pro, broken_stream
    ):
        """Половина разбора в базе хуже его отсутствия: человек откроет
        обрубок, а право будет потрачено."""
        chart = _make_chart(db, user_id=user_pro.id)

        client.get(_sse_url(chart.id), headers=auth_headers_pro)

        assert _rows(db, chart.id) == []

    def test_no_duplicate_on_second_read(
        self, client, db, user_pro, auth_headers_pro, full_stream
    ):
        chart = _make_chart(db, user_id=user_pro.id)

        client.get(_sse_url(chart.id), headers=auth_headers_pro)
        client.get(_sse_url(chart.id), headers=auth_headers_pro)

        assert len(_rows(db, chart.id)) == 1


class TestServedBack:
    def test_saved_text_is_returned_again(
        self, client, db, user_pro, auth_headers_pro, full_stream
    ):
        chart = _make_chart(db, user_id=user_pro.id)
        first = client.get(_sse_url(chart.id), headers=auth_headers_pro)
        assert "Вторая часть." in first.text

        second = client.get(_sse_url(chart.id), headers=auth_headers_pro)

        assert second.status_code == 200
        assert "Вторая часть." in second.text
        assert "[DONE]" in second.text

    def test_second_read_costs_no_quota(
        self, client, db, user_pro, auth_headers_pro, full_stream
    ):
        """Перечитать своё можно бесплатно — за этот текст уже заплачено."""
        chart = _make_chart(db, user_id=user_pro.id)
        client.get(_sse_url(chart.id), headers=auth_headers_pro)

        db.expire_all()
        after_first = get_monthly_usage(db, str(user_pro.id), "interpretation")

        client.get(_sse_url(chart.id), headers=auth_headers_pro)

        db.expire_all()
        assert get_monthly_usage(db, str(user_pro.id), "interpretation") == after_first

    def test_free_can_reread_after_right_is_spent(
        self, client, db, user_free, auth_headers_free, full_stream
    ):
        """Главное следствие правки: право потрачено, но текст свой — отдаём.

        Раньше здесь приходил отказ «Вы использовали бесплатную
        интерпретацию», то есть человек не мог перечитать то, что уже
        получил.
        """
        chart = _make_chart(db, user_id=user_free.id)
        client.get(_sse_url(chart.id), headers=auth_headers_free)

        db.expire_all()
        assert db.get(type(chart), chart.id).free_interpretation_used is True

        again = client.get(_sse_url(chart.id), headers=auth_headers_free)

        assert "Вторая часть." in again.text
        assert "error" not in again.text


class TestChartResponseExposesState:
    """Фронт должен знать, израсходует ли PDF бесплатный разбор.

    Вычислить это на клиенте нечем: ни строки interpretations, ни флага карты
    он не видит. Предупреждение показывается строго при
    has_interpretation == False и free_interpretation_used == False, поэтому
    оба поля обязаны приходить с бэкенда.
    """

    def _get(self, client, chart_id, headers):
        return client.get(f"/api/v1/chart/{chart_id}", headers=headers).json()

    def test_fresh_chart_reports_no_interpretation(
        self, client, db, user_free, auth_headers_free
    ):
        chart = _make_chart(db, user_id=user_free.id)

        data = self._get(client, chart.id, auth_headers_free)

        assert data["has_interpretation"] is False
        assert data["free_interpretation_used"] is False

    def test_after_reading_both_flags_flip(
        self, client, db, user_free, auth_headers_free, full_stream
    ):
        chart = _make_chart(db, user_id=user_free.id)
        client.get(_sse_url(chart.id), headers=auth_headers_free)

        data = self._get(client, chart.id, auth_headers_free)

        assert data["has_interpretation"] is True
        assert data["free_interpretation_used"] is True


class TestClientDisconnect:
    """Клиент отвалился посреди потока (24.09.2026): ни строки в БД, ни
    записи в кэше Redis. Обрыв на стороне клиента не должен оставлять на
    сервере обрубок, который потом отдадут как готовый разбор.

    TestClient тело дочитывает всегда, поэтому приложение зовётся напрямую
    по ASGI: после первого куска текста `receive` отдаёт `http.disconnect`.
    Поток после первого куска ждёт вечно — дойти до конца он может только
    если сервер НЕ прервал его на отключении, и тогда тест повиснет, а не
    пройдёт.
    """

    def _call_and_disconnect(self, app, chart_id, headers):
        import asyncio

        got_body = asyncio.Event()
        sent = []

        async def receive():
            if not sent:
                sent.append("req")
                return {"type": "http.request", "body": b"", "more_body": False}
            await got_body.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                got_body.set()

        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": _sse_url(chart_id), "raw_path": _sse_url(chart_id).encode(),
            "query_string": b"", "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("127.0.0.1", 5000), "server": ("testserver", 80),
        }

        async def run():
            await asyncio.wait_for(app(scope, receive, send), timeout=10)

        asyncio.run(run())
        start = next(m for m in sent if isinstance(m, dict) and m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if isinstance(m, dict) and m["type"] == "http.response.body")
        return start["status"], body.decode("utf-8")

    def test_disconnect_mid_stream_saves_nothing(
        self, client, db, user_pro, auth_headers_pro, monkeypatch
    ):
        import asyncio

        async def _stream(self, request):
            yield "Начало разбора, "
            await asyncio.Event().wait()  # дальше — только отключение
            yield "не дойдёт"
            request.engine_used = "deepseek"

        monkeypatch.setattr(
            "backend.interpretation.router.InterpretationRouter.stream", _stream
        )
        chart = _make_chart(db, user_id=user_pro.id)

        status, body = self._call_and_disconnect(client.app, chart.id, auth_headers_pro)
        # Поток и правда начался — иначе проверка ниже была бы пустой.
        assert status == 200
        assert "Начало разбора" in body
        assert "[DONE]" not in body

        db.expire_all()
        assert _rows(db, chart.id) == []
