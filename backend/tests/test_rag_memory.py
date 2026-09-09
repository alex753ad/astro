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
