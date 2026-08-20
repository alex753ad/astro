"""Регрессия к инциденту 20.08.2026: DeepSeek вернул 200 без единого байта
текста (reasoning_content съел весь max_tokens, "thinking" не был отключён),
клиент получил тихий [DONE] и завис. Покрывает:
- оба вызова DeepSeek в чате шлют thinking: disabled и подняли max_tokens;
- пустой ответ (нет delta.content) превращается в явную SSE-ошибку, а не в
  тихий [DONE], и не пишется в историю Redis;
- обычный ответ по-прежнему стримится и пишется в Redis как раньше.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import User, NatalChart
from backend.auth.passwords import hash_password
from backend.auth.jwt import create_token_pair
from backend.interpretation import rag_router


def make_pro_user(db: Session, email: str = "chat_pro@example.com") -> User:
    user = User(
        email=email,
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


@pytest.fixture(autouse=True)
def default_topic_astrology():
    """Классификатор темы делает свой (реальный) сетевой вызов к DeepSeek —
    без мока каждый тест в этом файле молча ждал бы реального (провального)
    запроса. По умолчанию — на тему карты, тесты про офф-топик переопределяют
    точечно в своей области действия."""
    with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="astrology")):
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


class _FakeHangingStreamResp:
    """Отдаёт chunks_before_hang строк, затем «висит» — трикл-имитация:
    httpx read-timeout сбрасывался бы на каждую строку, iter_with_deadline —
    нет."""

    def __init__(self, lines_before_hang, hang_seconds):
        self._lines = lines_before_hang
        self._hang_seconds = hang_seconds

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line
        await asyncio.sleep(self._hang_seconds)
        yield "data: [DONE]"  # pragma: no cover — дедлайн должен сработать раньше


class _FakeHangingStreamCtx:
    def __init__(self, lines_before_hang, hang_seconds):
        self._lines = lines_before_hang
        self._hang_seconds = hang_seconds

    async def __aenter__(self):
        return _FakeHangingStreamResp(self._lines, self._hang_seconds)

    async def __aexit__(self, *exc):
        return False


def _fake_hanging_async_client(lines_before_hang, hang_seconds):
    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url, headers=None, json=None):
            return _FakeHangingStreamCtx(lines_before_hang, hang_seconds)

    return _FakeAsyncClient


class TestStreamDeadline:
    """20.08.2026: httpx read-timeout сбрасывается на каждый чанк — трикл
    держит соединение сколько угодно. CHAT_STREAM_TIMEOUT — общий, не
    сбрасываемый дедлайн (backend/async_utils.py)."""

    @pytest.mark.asyncio
    async def test_deadline_exceeded_with_no_text_yields_explicit_timeout_error(
        self, client: TestClient, db: Session, fake_redis,
    ):
        user = make_pro_user(db)
        chart = make_chart(db, user.id)

        with patch.object(rag_router, "CHAT_STREAM_TIMEOUT", 0.05), \
             patch.object(rag_router.httpx, "AsyncClient", _fake_hanging_async_client([], 10)):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Прогноз на сегодня?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert '"timeout"' in resp.text
        assert "[DONE]" in resp.text

        key = rag_router._history_key(user.id, chart.id)
        assert await fake_redis.get(key) is None

    @pytest.mark.asyncio
    async def test_deadline_exceeded_after_partial_text_still_errors(
        self, client: TestClient, db: Session, fake_redis,
    ):
        """Часть текста уже ушла клиенту до обрыва — не должно тихо
        превратиться в [DONE] без объяснения."""
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        partial = [_sse({"choices": [{"delta": {"content": "Начало ответа"}}]})]

        with patch.object(rag_router, "CHAT_STREAM_TIMEOUT", 0.05), \
             patch.object(rag_router.httpx, "AsyncClient", _fake_hanging_async_client(partial, 10)):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Прогноз на сегодня?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert "Начало ответа" in resp.text
        assert '"timeout"' in resp.text

        key = rag_router._history_key(user.id, chart.id)
        assert await fake_redis.get(key) is None


class TestTopicRestriction:
    """20.08.2026: офф-топик вопрос не должен доходить до основной модели с
    полным контекстом карты и базой знаний — отдельный классификатор, не
    только инструкция в system prompt (промпт обходится уговорами)."""

    def test_off_topic_returns_fixed_reply_without_calling_main_model(
        self, client: TestClient, db: Session,
    ):
        user = make_pro_user(db)
        chart = make_chart(db, user.id)

        # Основной DeepSeek-клиент не подставлен вообще — если код всё же
        # попробует его вызвать, тест упадёт с AttributeError/сетевой ошибкой,
        # а не тихо пройдёт.
        with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="off_topic")):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Что будет с рублём в этом году?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert rag_router.OFF_TOPIC_REPLY in resp.text
        assert '"error"' not in resp.text

    @pytest.mark.asyncio
    async def test_off_topic_reply_is_persisted_to_history(
        self, client: TestClient, db: Session, fake_redis,
    ):
        user = make_pro_user(db)
        chart = make_chart(db, user.id)

        with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="off_topic")):
            client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Какие акции покупать?"},
                headers=auth_headers(user),
            )

        key = rag_router._history_key(user.id, chart.id)
        raw = await fake_redis.get(key)
        assert raw is not None
        history = json.loads(raw)
        assert history[-1]["role"] == "assistant"
        assert history[-1]["content"] == rag_router.OFF_TOPIC_REPLY

    def test_off_topic_does_not_bypass_chart_ownership_check(
        self, client: TestClient, db: Session,
    ):
        """Классификация темы не должна идти раньше проверки владения
        картой — иначе можно писать в историю чата под чужим chart_id."""
        owner = make_pro_user(db)
        other = make_pro_user(db, email="other_pro@example.com")
        chart = make_chart(db, owner.id)

        with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="off_topic")):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Курс доллара?"},
                headers=auth_headers(other),
            )

        assert resp.status_code == 404

    def test_astrology_topic_reaches_main_model_as_before(
        self, client: TestClient, db: Session,
    ):
        """Классификатор не должен ломать штатный путь — уже покрыто другими
        тестами через autouse-фикстуру, здесь — явная проверка на всякий случай."""
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        lines = [_sse({"choices": [{"delta": {"content": "Ответ по карте"}}]}), "data: [DONE]"]

        with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="astrology")), \
             patch.object(rag_router.httpx, "AsyncClient", _fake_async_client(lines, [])):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Что моя карта говорит про карьеру?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert "Ответ по карте" in resp.text
