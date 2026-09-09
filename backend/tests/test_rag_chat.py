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
         patch.object(rag_router, "_get_transits_block_cached", AsyncMock(return_value="")):
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


# ═══════════════════════════════════════════════════════════
# GET /rag-chat/history — чтение диалога, который помнит сервер
# ═══════════════════════════════════════════════════════════
class TestHistoryEndpoint:
    """История живёт на сервере и подмешивается в промпт, а прочитать её
    клиенту было нечем: у чата был ровно один маршрут, POST. В приложении
    шторку чата закрывают и открывают постоянно — человек видел пустое окно
    у модели, которая продолжает помнить разговор.
    """

    def test_returns_persisted_dialogue(self, client: TestClient, db: Session):
        """Главный кейс: что записал POST — то и отдаёт GET."""
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        lines = [_sse({"choices": [{"delta": {"content": "Ответ по карте"}}]}), "data: [DONE]"]

        with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="astrology")), \
             patch.object(rag_router.httpx, "AsyncClient", _fake_async_client(lines, [])):
            client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": "Что про карьеру?"},
                headers=auth_headers(user),
            )

        resp = client.get(
            f"/api/v1/chart/{chart.id}/rag-chat/history",
            headers=auth_headers(user),
        )

        assert resp.status_code == 200
        assert resp.json()["messages"] == [
            {"role": "user", "content": "Что про карьеру?"},
            {"role": "assistant", "content": "Ответ по карте"},
        ]

    def test_empty_history_is_empty_list_not_error(self, client: TestClient, db: Session):
        """Пустой чат — штатное состояние (первый вопрос по карте), а не сбой."""
        user = make_pro_user(db)
        chart = make_chart(db, user.id)

        resp = client.get(
            f"/api/v1/chart/{chart.id}/rag-chat/history",
            headers=auth_headers(user),
        )

        assert resp.status_code == 200
        assert resp.json() == {"messages": []}

    def test_foreign_chart_is_404(self, client: TestClient, db: Session):
        """Та же проверка владения, что в POST: иначе ручка стала бы оракулом
        чужих chart_id — 200 с пустым списком там, где карты нет вовсе.

        ⚠️ Владелец на том же URL проверяется здесь же, и это не украшение.
        Без него тест зелёный и на коде БЕЗ маршрута: 404 отдал бы сам
        FastAPI, ничего не проверив. Пара «чужой 404 / свой 200» отличает
        отказ по владению от отсутствия ручки.
        """
        owner = make_pro_user(db)
        other = make_pro_user(db, email="other_hist@example.com")
        chart = make_chart(db, owner.id)
        url = f"/api/v1/chart/{chart.id}/rag-chat/history"

        assert client.get(url, headers=auth_headers(other)).status_code == 404
        assert client.get(url, headers=auth_headers(owner)).status_code == 200

    def test_free_tier_is_403(self, client: TestClient, db: Session, user_free, auth_headers_free):
        """Тариф — тот же require_tier("pro"), что у самого чата."""
        chart = make_chart(db, user_free.id)

        resp = client.get(
            f"/api/v1/chart/{chart.id}/rag-chat/history",
            headers=auth_headers_free,
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_leaks_neither_system_prompt_nor_knowledge_nor_memory(
        self, client: TestClient, db: Session, fake_redis,
    ):
        """⚠️ Главный инвариант ручки, ради него она и написана осторожно.

        Наружу уходят ТОЛЬКО реплики человека и ответы модели. Ровно эти три
        вещи — системный промпт, база знаний и память Аристеи — уже
        вытаскивали через поданную клиентом историю с role="assistant" (см.
        докстринг RagChatRequest), из-за чего история и переехала на сервер.

        Проверка идёт от противного: кладём в Redis запись с ролью system и
        секретом внутри — такую, какую туда положил бы будущий неосторожный
        писатель, — и требуем, чтобы ручка её не отдала.
        """
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        await fake_redis.set(
            rag_router._history_key(user.id, chart.id),
            json.dumps([
                {"role": "system", "content": "СЕКРЕТНЫЙ СИСТЕМНЫЙ ПРОМПТ"},
                {"role": "user", "content": "Вопрос"},
                {"role": "assistant", "content": "Ответ"},
            ], ensure_ascii=False),
        )

        resp = client.get(
            f"/api/v1/chart/{chart.id}/rag-chat/history",
            headers=auth_headers(user),
        )

        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert {m["role"] for m in messages} <= {"user", "assistant"}
        assert "СЕКРЕТНЫЙ" not in resp.text

    @pytest.mark.asyncio
    async def test_caps_at_max_history(self, client: TestClient, db: Session, fake_redis):
        """Отдаём столько же, сколько уходит в промпт, — не всю ленту Redis."""
        user = make_pro_user(db)
        chart = make_chart(db, user.id)
        await fake_redis.set(
            rag_router._history_key(user.id, chart.id),
            json.dumps(
                [{"role": "user", "content": f"q{i}"} for i in range(rag_router.MAX_HISTORY + 6)],
                ensure_ascii=False,
            ),
        )

        resp = client.get(
            f"/api/v1/chart/{chart.id}/rag-chat/history",
            headers=auth_headers(user),
        )

        assert len(resp.json()["messages"]) == rag_router.MAX_HISTORY


# ═══════════════════════════════════════════════════════════
# Чужая тема: предложить, а не отбить (09.09.2026)
# ═══════════════════════════════════════════════════════════
class TestOffTopicOffersInstead:
    """До 09.09.2026 на любую чужую тему уходил ОДИН текст «Это не моя тема…
    Спроси что-нибудь о карте». Он закрывает разговор, ничего не открывая:
    человек уже спросил, ему ответили «спроси другое», а что именно — неясно.
    """

    def test_each_label_has_its_own_reply(self, client: TestClient, db: Session):
        """Ответ зависит от РАЗНОВИДНОСТИ темы, а не один на все."""
        texts = set(rag_router.OFF_TOPIC_REPLIES.values())
        assert len(texts) == len(rag_router.OFF_TOPIC_REPLIES) >= 3

    def test_every_reply_offers_a_choice(self):
        """⚠️ Инвариант, ради которого правка и делалась: каждый ответ обязан
        не только отказать, но и предложить — и закончиться вопросом, чтобы
        человеку было что выбрать. Отказ без предложения этот тест роняет."""
        for label, reply in rag_router.OFF_TOPIC_REPLIES.items():
            assert reply.rstrip().endswith("?"), f"{label}: не предлагает выбрать"
            assert "карт" in reply.lower(), f"{label}: не сказано, что она может"

    def test_reply_never_echoes_the_question(self, client: TestClient, db: Session):
        """Тексты фиксированные: пользовательская строка в ответ не попадает
        ни при каком входе. Иначе через отказ можно было бы печатать в чат
        что угодно."""
        user = make_pro_user(db, email="offtopic_echo@example.com")
        chart = make_chart(db, user.id)
        marker = "МАРКЕР-ЭХА-12345"

        with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="money")):
            resp = client.post(
                f"/api/v1/chart/{chart.id}/rag-chat",
                json={"question": f"Курс доллара {marker}?"},
                headers=auth_headers(user),
            )

        assert resp.status_code == 200
        assert marker not in resp.text
        assert rag_router.OFF_TOPIC_REPLIES["money"] in resp.text

    def test_money_and_world_give_different_answers(self, client: TestClient, db: Session):
        """Метка доезжает до текста, а не теряется по дороге."""
        user = make_pro_user(db, email="offtopic_labels@example.com")
        chart = make_chart(db, user.id)
        seen = {}
        for label in ("money", "world", "life"):
            with patch.object(rag_router, "_classify_topic", AsyncMock(return_value=label)):
                resp = client.post(
                    f"/api/v1/chart/{chart.id}/rag-chat",
                    json={"question": "вопрос"},
                    headers=auth_headers(user),
                )
            seen[label] = resp.text
        assert len(set(seen.values())) == 3


class TestClassifierIsNotTooStrict:
    """«Дом» в астрологии — это дом карты, и отбивать его нельзя. Классификатор
    отбивал: правила для неоднозначного слова у него не было вовсе, а off_topic
    был описан как «любые темы вне астрологии», то есть как catch-all.

    ⚠️ Это проверки ПРОМПТА, а не поведения модели: боевого ключа в тестах нет,
    и что модель послушается, отсюда не следует. Они держат правило от
    молчаливого удаления при следующей правке текста — не больше и не меньше.
    """

    def test_prompt_has_a_tie_breaker(self):
        prompt = rag_router._TOPIC_CLASSIFIER_PROMPT
        assert "Сомневаешься" in prompt, "нет правила для неоднозначного случая"
        assert "astrology" in prompt.split("Сомневаешься")[1][:40]

    def test_prompt_names_the_word_that_broke_it(self):
        # Именно «дом» — тот вход, на котором дефект нашли.
        assert "«дом»" in rag_router._TOPIC_CLASSIFIER_PROMPT

    def test_prompt_covers_single_word_input(self):
        """Одно слово без пояснения — просьба рассказать по карте, а не вопрос
        о внешнем мире. Раньше классификатору об этом не говорили ничего."""
        assert "ОДНО СЛОВО" in rag_router._TOPIC_CLASSIFIER_PROMPT

    def test_unknown_label_falls_open_to_astrology(self):
        """Модель ответила не тем словом — пропускаем к модели, а не отбиваем.
        Цена ошибки несимметрична: лишний вопрос стоит копейки, отбитый
        настоящий вопрос — ушедшего человека."""
        for raw in ("непонятно", "", "   ", "OFF_TOPIC", "не знаю"):
            assert rag_router._label_from_reply(raw) == "astrology", repr(raw)

    def test_known_labels_are_recognised(self):
        for label in rag_router.OFF_TOPIC_REPLIES:
            assert rag_router._label_from_reply(label) == label
            assert rag_router._label_from_reply(f"  {label.upper()}  ") == label

    def test_astrology_answer_passes_through(self):
        assert rag_router._label_from_reply("astrology") == "astrology"
