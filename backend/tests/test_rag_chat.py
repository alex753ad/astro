"""Регрессия к инциденту 20.08.2026: DeepSeek вернул 200 без единого байта
текста (reasoning_content съел весь max_tokens, "thinking" не был отключён),
клиент получил тихий [DONE] и завис. Покрывает:
- оба вызова DeepSeek в чате шлют thinking: disabled и подняли max_tokens;
- пустой ответ (нет delta.content) превращается в явную SSE-ошибку, а не в
  тихий [DONE], и не пишется в историю Redis;
- обычный ответ по-прежнему стримится и пишется в Redis как раньше.
"""

from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import User, NatalChart
from backend.auth.passwords import hash_password
from backend.auth.jwt import create_token_pair
from backend.interpretation import rag_router


def make_pro_user(db: Session) -> User:
    user = User(
        email="chat_pro@example.com",
        hashed_password=hash_password("password123"),
        is_active=True,
        is_email_confirmed=True,
        tier="pro",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_chart(db: Session, user_id: str) -> NatalChart:
    chart = NatalChart(
        user_id=user_id,
        birth_date="1990-01-01",
        birth_time="12:00",
        birth_place="Moscow",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        house_system="placidus",
        planets=[], houses=[], aspects=[],
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return chart


def auth_headers(user: User) -> dict:
    tokens = create_token_pair(user.id, user.email, user.tier)
    return {"Authorization": f"Bearer {tokens.access_token}"}


class _FakeStreamResp:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCtx:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return _FakeStreamResp(self._lines)

    async def __aexit__(self, *exc):
        return False


def _fake_async_client(lines, captured_payloads):
    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url, headers=None, json=None):
            captured_payloads.append(json)
            return _FakeStreamCtx(lines)

    return _FakeAsyncClient


def _sse(obj) -> str:
    return f"data: {json.dumps(obj)}"


@pytest.fixture(autouse=True)
def no_memory_fold():
    """Фоновая свёртка памяти (второй вызов DeepSeek) не участвует в этих
    тестах — она глушит собственные ошибки, но лишний реальный вызов не нужен."""
    with patch.object(rag_router, "_update_memory", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def no_rag_lookup():
    with patch.object(rag_router, "retrieve", return_value=[]), \
         patch.object(rag_router, "build_chart_summary", return_value="Карта: тест"), \
         patch.object(rag_router, "_get_transits_block_cached", return_value=""):
        yield


class TestChatPayload:
    def test_disables_thinking_and_raises_max_tokens(self, client: TestClient, db: Session):
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        lines = [_sse({"choices": [{"delta": {"content": "Привет"}}]}), "data: [DONE]"]
        captured: list = []

        with patch.object(rag_router.httpx, "AsyncClient", _fake_async_client(lines, captured)):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Что говорит моя карта о деньгах?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert len(captured) == 1
        assert captured[0]["thinking"] == {"type": "disabled"}
        assert captured[0]["max_tokens"] == rag_router.CHAT_MAX_TOKENS
        assert captured[0]["max_tokens"] > 800  # было мало — сам инцидент


class TestEmptyResponseSurfacesError:
    def test_empty_content_yields_explicit_error_not_silent_done(
        self, client: TestClient, db: Session, fake_redis,
    ):
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        # Ровно инцидент 20.08.2026: модель отвечает только в reasoning_content,
        # delta.content всегда пуст, finish_reason=length.
        lines = [
            _sse({"choices": [{"delta": {"reasoning_content": "думаю про транзиты..."}}]}),
            _sse({"choices": [{"delta": {}, "finish_reason": "length"}]}),
            "data: [DONE]",
        ]

        with patch.object(rag_router.httpx, "AsyncClient", _fake_async_client(lines, [])):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Прогноз на сегодня?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        body = resp.text
        assert '"error"' in body
        assert "empty_response" in body
        assert "[DONE]" in body

    @pytest.mark.asyncio
    async def test_empty_answer_not_persisted_to_history(
        self, client: TestClient, db: Session, fake_redis,
    ):
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        lines = [
            _sse({"choices": [{"delta": {"reasoning_content": "..."}, "finish_reason": "length"}]}),
            "data: [DONE]",
        ]

        with patch.object(rag_router.httpx, "AsyncClient", _fake_async_client(lines, [])):
            client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Прогноз на сегодня?"},
                headers=auth_headers(user),
            )

        key = rag_router._history_key(user.id, chart.id)
        assert await fake_redis.get(key) is None


class TestNormalResponseUnaffected:
    @pytest.mark.asyncio
    async def test_full_answer_still_streams_and_persists(
        self, client: TestClient, db: Session, fake_redis,
    ):
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        lines = [
            _sse({"choices": [{"delta": {"content": "Юпитер во "}}]}),
            _sse({"choices": [{"delta": {"content": "втором доме."}, "finish_reason": "stop"}]}),
            "data: [DONE]",
        ]

        with patch.object(rag_router.httpx, "AsyncClient", _fake_async_client(lines, [])):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Что моя карта говорит про деньги?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert "Юпитер во" in resp.text
        assert '"error"' not in resp.text

        key = rag_router._history_key(user.id, chart.id)
        raw = await fake_redis.get(key)
        assert raw is not None
        history = json.loads(raw)
        assert history[-1]["role"] == "assistant"
        assert "втором доме" in history[-1]["content"]
