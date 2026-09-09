"""Память Аристеи: что попадает в свёртку и что в неё не попадает.

Отдельный файл, а не хвост test_rag_chat.py: тот про поток ответа, этот про
второй, фоновый контур — свёртку диалога в `astrea_memory`. Общего у них
только помощники, они и импортируются.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.interpretation import rag_router
from backend.models import AstreaMemory
from backend.tests.test_rag_chat import make_pro_user, make_chart, auth_headers, _sse


def _fold_client(fold_reply, captured, finish_reason="stop"):
    """Клиент DeepSeek на оба вызова: `stream` отдаёт ответ чата, `post` —
    свёртку памяти. Промпт свёртки записывается в `captured`."""

    class _StreamResp:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            yield _sse({"choices": [{"delta": {"content": captured["answer"]}}]})
            yield "data: [DONE]"

    class _StreamCtx:
        async def __aenter__(self):
            return _StreamResp()

        async def __aexit__(self, *exc):
            return False

    class _PostResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": fold_reply}, "finish_reason": finish_reason}
                ]
            }

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, *a, **kw):
            return _StreamCtx()

        async def post(self, url, headers=None, json=None):
            captured["fold_prompt"] = json["messages"][0]["content"]
            return _PostResp()

    return _Client


@pytest.fixture(autouse=True)
def _quiet_context():
    """Классификатор и сборка контекста в этих тестах не участвуют."""
    with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="astrology")), \
         patch.object(rag_router, "retrieve", return_value=[]), \
         patch.object(rag_router, "build_chart_summary", return_value="Карта: тест"), \
         patch.object(rag_router, "_get_transits_block_cached", AsyncMock(return_value="")):
        yield


class TestFoldSeesTheAnswer:
    """⚠️ `BackgroundTask` связывает аргументы в момент СОЗДАНИЯ — то есть до
    того, как ответ модели существует. Пока в свёртку передавали только
    `question`, туда уходил вопрос человека БЕЗ ответа на него: ответ попадал
    в память лишь ходом позже, когда становился частью `history`, а последний
    ответ разговора — никогда.
    """

    @pytest.mark.asyncio
    async def test_one_exchange_folds_both_question_and_answer(
        self, client: TestClient, db: Session,
    ):
        """Главный кейс: ОДИН обмен, и в свёртке обе реплики.

        Раньше здесь была ровно одна строка — вопрос: на первом ходу `history`
        пуста, а ответа в аргументах не было вовсе.
        """
        user = make_pro_user(db, email="memfold1@example.com")
        chart = make_chart(db, user.id)
        answer = "Юпитер идёт по десятому дому — окно для смены работы открыто."
        captured = {"answer": answer}

        with patch.object(rag_router, "SessionLocal", lambda: db), \
             patch.object(rag_router.httpx, "AsyncClient",
                          _fold_client("Лена меняет работу.", captured)):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Хочу сменить работу"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        prompt = captured.get("fold_prompt", "")
        assert prompt, "свёртка памяти не вызывалась вовсе"
        assert "Хочу сменить работу" in prompt, "вопроса нет в свёртке"
        assert answer in prompt, "ОТВЕТА нет в свёртке — тот самый дефект"

    @pytest.mark.asyncio
    async def test_answer_is_attributed_to_aristea(self, client: TestClient, db: Session):
        """Ответ подписан именно как реплика Аристеи.

        Промпт свёртки просит запомнить, «что советовала Аристея», — без
        подписи свёртка не отличит совет от того, что сказал человек.
        """
        user = make_pro_user(db, email="memfold2@example.com")
        chart = make_chart(db, user.id)
        answer = "Ждите выхода Меркурия из ретроградности."
        captured = {"answer": answer}

        with patch.object(rag_router, "SessionLocal", lambda: db), \
             patch.object(rag_router.httpx, "AsyncClient", _fold_client("сводка", captured)):
            client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Когда подавать резюме?"},
                headers=auth_headers(user),
            )

        assert f"Аристея: {answer}" in captured["fold_prompt"]

    @pytest.mark.asyncio
    async def test_no_answer_no_fold(self, db: Session):
        """Ход не состоялся — сворачивать нечего.

        `_persist_turn` его тоже не записал, и памяти нечего запоминать, кроме
        вопроса в пустоту.
        """
        user = make_pro_user(db, email="memfold3@example.com")
        uid = user.id
        calls = {"n": 0}

        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, *a, **kw):
                calls["n"] += 1
                raise AssertionError("свёртка не должна вызываться без ответа")

        with patch.object(rag_router, "SessionLocal", lambda: db), \
             patch.object(rag_router.httpx, "AsyncClient", _Client):
            await rag_router._update_memory(uid, "вопрос", [], {})      # держатель пуст
            await rag_router._update_memory(uid, "вопрос", [], None)    # держателя нет

        assert calls["n"] == 0


class TestFoldRejectsTruncated:
    """`finish_reason != "stop"` — сводка обрезана на полуслове. Не сохраняем,
    оставляем прежнюю: тот же приём, что в натальном разборе.

    `MEMORY_MAX_TOKENS = 400` — это ~130-160 русских слов при просимых в
    промпте 120, то есть модель, перевыполнившая объём, упирается в потолок
    штатно, а не в исключительном случае.
    """

    @pytest.mark.asyncio
    async def test_truncated_summary_does_not_overwrite(self, db: Session):
        user = make_pro_user(db, email="memtrunc@example.com")
        uid = user.id   # ⚠️ до вызова: _update_memory закрывает сессию (db.close())
        db.add(AstreaMemory(user_id=uid, summary="Прежняя сводка."))
        db.commit()
        captured = {"answer": "ответ"}

        with patch.object(rag_router, "SessionLocal", lambda: db), \
             patch.object(rag_router.httpx, "AsyncClient",
                          _fold_client("Обрывок на полусло", captured, finish_reason="length")):
            await rag_router._update_memory(uid, "вопрос", [], {"answer": "ответ"})

        row = db.get(AstreaMemory, uid)
        assert row.summary == "Прежняя сводка.", "обрезанная сводка затёрла прежнюю"

    @pytest.mark.asyncio
    async def test_truncated_summary_does_not_create_a_row(self, db: Session):
        """Памяти ещё не было — обрывок не должен стать первой записью."""
        user = make_pro_user(db, email="memtrunc2@example.com")
        uid = user.id
        captured = {"answer": "ответ"}

        with patch.object(rag_router, "SessionLocal", lambda: db), \
             patch.object(rag_router.httpx, "AsyncClient",
                          _fold_client("Обрывок", captured, finish_reason="length")):
            await rag_router._update_memory(uid, "вопрос", [], {"answer": "ответ"})

        assert db.get(AstreaMemory, uid) is None

    @pytest.mark.asyncio
    async def test_complete_summary_is_saved(self, db: Session):
        """Штатный путь не сломан."""
        user = make_pro_user(db, email="memok@example.com")
        uid = user.id
        captured = {"answer": "ответ"}

        with patch.object(rag_router, "SessionLocal", lambda: db), \
             patch.object(rag_router.httpx, "AsyncClient",
                          _fold_client("Новая сводка.", captured, finish_reason="stop")):
            await rag_router._update_memory(uid, "вопрос", [], {"answer": "ответ"})

        assert db.get(AstreaMemory, uid).summary == "Новая сводка."

    @pytest.mark.asyncio
    async def test_missing_finish_reason_is_tolerated(self, db: Session):
        """Провайдер поля не прислал — не повод терять сводку.

        Раньше его не проверяли вовсе; ломать штатный путь из-за отсутствия
        поля было бы регрессом, а не защитой.
        """
        user = make_pro_user(db, email="memnofr@example.com")
        uid = user.id
        captured = {"answer": "ответ"}

        with patch.object(rag_router, "SessionLocal", lambda: db), \
             patch.object(rag_router.httpx, "AsyncClient",
                          _fold_client("Сводка без поля.", captured, finish_reason=None)):
            await rag_router._update_memory(uid, "вопрос", [], {"answer": "ответ"})

        assert db.get(AstreaMemory, uid).summary == "Сводка без поля."


class TestOffTopicDoesNotTouchMemory:
    """Ветка чужой темы намеренно не сворачивается в память.

    Закреплено и комментарием в коде, и этим тестом — чтобы следующая разведка
    не искала заново, задумано так или забыто. Разведка 09.09.2026 нашла эту
    ветку пятой в списке «где свёртка пропускается молча» и ответить на этот
    вопрос не смогла.
    """

    def test_off_topic_response_does_not_fold(self, client: TestClient, db: Session):
        user = make_pro_user(db, email="memofftopic@example.com")
        chart = make_chart(db, user.id)
        fold = AsyncMock()

        with patch.object(rag_router, "_update_memory", fold), \
             patch.object(rag_router, "_classify_topic", AsyncMock(return_value="money")):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "курс доллара"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert fold.call_count == 0
