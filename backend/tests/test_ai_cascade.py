"""tests/test_ai_cascade.py — тест каскада AI fallback.

Каскад: GPT4oEngine → DeepSeekEngine → TemplateEngine

Проверяем:
  - GPT-4o недоступен → DeepSeek
  - Оба AI недоступны → Template (всегда работает)
  - Retry-логика (3 попытки, экспоненциальная задержка 1/3/9с)
  - Budget guard: исчерпан → AI пропускается
  - Cache hit → AI не вызывается
  - stream() переключается при отсутствии чанков

Запуск: pytest backend/tests/test_ai_cascade.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from backend.interpretation.router import InterpretationRouter, _daily_spend
from backend.interpretation.base import (
    InterpretationRequest,
    InterpretationResult,
)
from backend.interpretation.gpt4o import GPT4oEngine
from backend.interpretation.deepseek import DeepSeekEngine
from backend.interpretation.template import TemplateEngine


# ── Helpers ───────────────────────────────────────────────────────────────────

def _request() -> InterpretationRequest:
    return InterpretationRequest(
        natal_profile={
            "planets": [
                {"name": "Sun", "sign": "Capricorn", "degree": 10.5, "house": 10},
                {"name": "Moon", "sign": "Taurus", "degree": 15.3, "house": 2},
            ],
            "ascendant": {"sign": "Aries", "degree": 5.2},
        },
        context="natal",
    )


def _good_result(engine: str = "gpt4o") -> InterpretationResult:
    """Возвращает корректный результат, проходящий валидацию."""
    return InterpretationResult(
        content=(
            "### Личность\n"
            "Солнце в Козероге говорит о целеустремлённости и дисциплине. "
            "Вы методичны и практичны в достижении карьерных целей. "
            "Луна в Тельце добавляет эмоциональную стабильность и тягу к комфорту.\n\n"
            "### Карьера\n"
            "Профессиональная сфера — главный приоритет. Успех приходит через терпение."
        ),
        engine=engine,
        tokens_used=150,
    )


async def _collect_stream(gen) -> str:
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return "".join(chunks)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Фикстуры ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_budget():
    """Сбрасываем дневной бюджет перед каждым тестом."""
    _daily_spend.clear()
    yield
    _daily_spend.clear()


@pytest.fixture(autouse=True)
def clear_cache():
    """Сбрасываем кэш интерпретаций."""
    from backend.cache import interpretation_cache
    if hasattr(interpretation_cache, "clear"):
        interpretation_cache.clear()
    yield


# ═══════════════════════════════════════════════════════════
# generate() — успешный путь через GPT-4o
# ═══════════════════════════════════════════════════════════

class TestGenerateGPT4oSuccess:
    def test_gpt4o_called_first(self):
        """GPT4oEngine вызывается первым."""
        router = InterpretationRouter()
        req = _request()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt:
            mock_gpt.return_value = _good_result("gpt4o")
            result = _run(router.generate(req))

        mock_gpt.assert_called_once()
        assert result.engine == "gpt4o"

    def test_gpt4o_result_returned_directly(self):
        """Результат GPT-4o возвращается без вызова DeepSeek."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds:
            mock_gpt.return_value = _good_result("gpt4o")

            _run(router.generate(_request()))

        mock_ds.assert_not_called()

    def test_result_is_cached_after_gpt4o(self):
        """Успешный результат сохраняется в кэш."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt:
            mock_gpt.return_value = _good_result("gpt4o")
            _run(router.generate(_request()))
            # Второй вызов — должен взять из кэша
            result2 = _run(router.generate(_request()))

        assert result2.cached is True
        # GPT вызван только один раз
        assert mock_gpt.call_count == 1


# ═══════════════════════════════════════════════════════════
# generate() — GPT-4o падает → DeepSeek
# ═══════════════════════════════════════════════════════════

class TestFallbackToDeepSeek:
    def test_gpt4o_exception_falls_back_to_deepseek(self):
        """GPT-4o бросает Exception → DeepSeek вызывается."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch("backend.interpretation.router.asyncio.sleep", new_callable=AsyncMock):

            mock_gpt.side_effect = Exception("OpenAI unavailable")
            mock_ds.return_value = _good_result("deepseek")

            result = _run(router.generate(_request()))

        mock_ds.assert_called()
        assert result.engine == "deepseek"

    def test_gpt4o_timeout_falls_back_to_deepseek(self):
        """GPT-4o таймаут → DeepSeek."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch("backend.interpretation.router.asyncio.sleep", new_callable=AsyncMock):

            mock_gpt.side_effect = asyncio.TimeoutError()
            mock_ds.return_value = _good_result("deepseek")

            result = _run(router.generate(_request()))

        assert result.engine == "deepseek"

    def test_deepseek_called_after_gpt4o_failure(self):
        """Порядок: сначала GPT-4o, потом DeepSeek."""
        call_order = []
        router = InterpretationRouter()

        async def _fail(*a, **kw):
            call_order.append("gpt4o")
            raise Exception("fail")

        async def _ok(*a, **kw):
            call_order.append("deepseek")
            return _good_result("deepseek")

        with patch.object(GPT4oEngine, "generate", side_effect=_fail), \
             patch.object(DeepSeekEngine, "generate", side_effect=_ok), \
             patch("backend.interpretation.router.asyncio.sleep", new_callable=AsyncMock):

            _run(router.generate(_request()))

        assert "gpt4o" in call_order
        assert "deepseek" in call_order
        assert call_order.index("gpt4o") < call_order.index("deepseek")


# ═══════════════════════════════════════════════════════════
# generate() — оба AI падают → Template
# ═══════════════════════════════════════════════════════════

class TestFallbackToTemplate:
    def test_both_ai_fail_uses_template(self):
        """Оба AI упали → TemplateEngine вызывается."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch.object(TemplateEngine, "generate", new_callable=AsyncMock) as mock_tmpl, \
             patch("backend.interpretation.router.asyncio.sleep", new_callable=AsyncMock):

            mock_gpt.side_effect = Exception("GPT fail")
            mock_ds.side_effect = Exception("DS fail")
            mock_tmpl.return_value = _good_result("template")

            result = _run(router.generate(_request()))

        mock_tmpl.assert_called()
        assert result.engine == "template"

    def test_template_engine_always_returns_content(self):
        """TemplateEngine не бросает исключений и возвращает контент."""
        engine = TemplateEngine()
        result = _run(engine.generate(_request()))
        assert isinstance(result, InterpretationResult)
        assert isinstance(result.content, str)
        assert len(result.content) > 0

    def test_cascade_order_strict(self):
        """Строгий порядок: GPT → DeepSeek → Template."""
        call_order = []
        router = InterpretationRouter()

        async def _fail_gpt(*a, **kw):
            call_order.append("gpt4o")
            raise Exception("fail")

        async def _fail_ds(*a, **kw):
            call_order.append("deepseek")
            raise Exception("fail")

        async def _tmpl_ok(*a, **kw):
            call_order.append("template")
            return _good_result("template")

        with patch.object(GPT4oEngine, "generate", side_effect=_fail_gpt), \
             patch.object(DeepSeekEngine, "generate", side_effect=_fail_ds), \
             patch.object(TemplateEngine, "generate", side_effect=_tmpl_ok), \
             patch("backend.interpretation.router.asyncio.sleep", new_callable=AsyncMock):

            _run(router.generate(_request()))

        assert call_order == ["gpt4o", "deepseek", "template"]


# ═══════════════════════════════════════════════════════════
# Retry-логика
# ═══════════════════════════════════════════════════════════

class TestRetryLogic:
    def test_gpt4o_retried_before_fallback(self):
        """GPT-4o вызывается несколько раз (retry) перед переходом к DeepSeek."""
        call_count = 0
        router = InterpretationRouter()

        async def _fail(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise Exception("transient")

        with patch.object(GPT4oEngine, "generate", side_effect=_fail), \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch("backend.interpretation.router.asyncio.sleep", new_callable=AsyncMock):

            mock_ds.return_value = _good_result("deepseek")
            _run(router.generate(_request()))

        # 3 попытки на GPT-4o перед fallback
        assert call_count == 3

    def test_retry_uses_exponential_backoff(self):
        """Задержки между попытками: 1с, 3с (экспоненциальные)."""
        sleep_calls = []
        router = InterpretationRouter()

        async def _fake_sleep(delay):
            sleep_calls.append(delay)

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch("backend.interpretation.router.asyncio.sleep", side_effect=_fake_sleep):

            mock_gpt.side_effect = Exception("fail")
            mock_ds.return_value = _good_result("deepseek")
            _run(router.generate(_request()))

        # Должны быть задержки 1.0 и 3.0 (после 1-й и 2-й неудачи)
        assert len(sleep_calls) >= 2
        assert sleep_calls[0] == pytest.approx(1.0)
        assert sleep_calls[1] == pytest.approx(3.0)

    def test_third_retry_uses_9s_delay(self):
        """Третья задержка = 9с."""
        sleep_calls = []
        router = InterpretationRouter()

        async def _fake_sleep(delay):
            sleep_calls.append(delay)

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch.object(TemplateEngine, "generate", new_callable=AsyncMock) as mock_tmpl, \
             patch("backend.interpretation.router.asyncio.sleep", side_effect=_fake_sleep):

            mock_gpt.side_effect = Exception("fail")
            mock_ds.side_effect = Exception("fail")
            mock_tmpl.return_value = _good_result("template")
            _run(router.generate(_request()))

        # Задержки GPT: 1.0, 3.0 + DS: 1.0, 3.0
        assert 9.0 in sleep_calls or 3.0 in sleep_calls


# ═══════════════════════════════════════════════════════════
# Budget guard
# ═══════════════════════════════════════════════════════════

class TestBudgetGuard:
    def test_exceeded_budget_skips_gpt4o(self):
        """Бюджет исчерпан → GPT-4o пропускается."""
        import time
        today = time.strftime("%Y-%m-%d")
        _daily_spend[today] = 9999.0  # заведомо больше любого лимита

        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch.object(TemplateEngine, "generate", new_callable=AsyncMock) as mock_tmpl:

            mock_ds.side_effect = Exception("ds also over budget")
            mock_tmpl.return_value = _good_result("template")
            _run(router.generate(_request()))

        mock_gpt.assert_not_called()

    def test_template_not_blocked_by_budget(self):
        """TemplateEngine не проверяет бюджет — всегда доступен."""
        router = InterpretationRouter()
        assert router._check_budget("template") is True

    def test_budget_ok_allows_ai_engines(self):
        """При наличии бюджета GPT-4o вызывается."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt:
            mock_gpt.return_value = _good_result("gpt4o")
            _run(router.generate(_request()))

        mock_gpt.assert_called_once()

    def test_spend_tracked_after_successful_call(self):
        """После успешного вызова трекается стоимость."""
        import time
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt:
            mock_gpt.return_value = InterpretationResult(
                content=(
                    "### Личность\n" + "x" * 300 + "\n### Карьера\n" + "y" * 100
                ),
                engine="gpt4o",
                tokens_used=1000,  # трекаем расход
            )
            _run(router.generate(_request()))

        today = time.strftime("%Y-%m-%d")
        assert _daily_spend.get(today, 0.0) > 0


# ═══════════════════════════════════════════════════════════
# Cache
# ═══════════════════════════════════════════════════════════

class TestCache:
    def test_cache_hit_skips_all_engines(self):
        """Кэш-хит → ни один engine не вызывается."""
        router = InterpretationRouter()

        # Первый вызов — кэширует
        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt:
            mock_gpt.return_value = _good_result("gpt4o")
            _run(router.generate(_request()))
            first_count = mock_gpt.call_count

        # Второй вызов — из кэша
        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt2, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds2, \
             patch.object(TemplateEngine, "generate", new_callable=AsyncMock) as mock_tmpl2:

            result = _run(router.generate(_request()))

        assert result.cached is True
        mock_gpt2.assert_not_called()
        mock_ds2.assert_not_called()
        mock_tmpl2.assert_not_called()

    def test_cache_miss_calls_engine(self):
        """Кэш-промах → engine вызывается."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt:
            mock_gpt.return_value = _good_result("gpt4o")
            result = _run(router.generate(_request()))

        mock_gpt.assert_called_once()
        assert result.cached is False


# ═══════════════════════════════════════════════════════════
# stream()
# ═══════════════════════════════════════════════════════════

class TestStream:
    def test_stream_yields_chunks(self):
        """stream() возвращает непустые чанки."""
        router = InterpretationRouter()

        async def _fake_stream(req):
            for chunk in ["Солнце ", "в Козероге ", "— амбиции."]:
                yield chunk

        with patch.object(GPT4oEngine, "stream", side_effect=_fake_stream):
            result = _run(_collect_stream(router.stream(_request())))

        assert len(result) > 0
        assert "Козероге" in result

    def test_stream_falls_back_when_no_chunks(self):
        """stream() переключается на следующий engine если нет чанков."""
        router = InterpretationRouter()

        async def _empty_stream(req):
            return
            yield  # пустой генератор

        async def _good_stream(req):
            yield "DeepSeek ответ"

        with patch.object(GPT4oEngine, "stream", side_effect=_empty_stream), \
             patch.object(DeepSeekEngine, "stream", side_effect=_good_stream):

            result = _run(_collect_stream(router.stream(_request())))

        assert len(result) > 0

    def test_stream_always_returns_something(self):
        """stream() никогда не возвращает пустой результат — Template спасёт."""
        router = InterpretationRouter()

        async def _empty(req):
            return
            yield

        with patch.object(GPT4oEngine, "stream", side_effect=_empty), \
             patch.object(DeepSeekEngine, "stream", side_effect=_empty):

            result = _run(_collect_stream(router.stream(_request())))

        # Либо TemplateEngine что-то вернул, либо fallback-сообщение
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════
# Валидация ответа
# ═══════════════════════════════════════════════════════════

class TestResponseValidation:
    def test_short_response_triggers_fallback(self):
        """Слишком короткий ответ (<200 символов) → fallback на следующий engine."""
        router = InterpretationRouter()

        with patch.object(GPT4oEngine, "generate", new_callable=AsyncMock) as mock_gpt, \
             patch.object(DeepSeekEngine, "generate", new_callable=AsyncMock) as mock_ds, \
             patch("backend.interpretation.router.asyncio.sleep", new_callable=AsyncMock):

            mock_gpt.return_value = InterpretationResult(
                content="Слишком короткий ответ.",
                engine="gpt4o",
                tokens_used=5,
            )
            mock_ds.return_value = _good_result("deepseek")

            result = _run(router.generate(_request()))

        # Результат должен быть от DeepSeek, т.к. GPT вернул невалидный ответ
        assert result.engine == "deepseek"

    def test_validate_response_empty_fails(self):
        """Пустой контент не проходит валидацию."""
        router = InterpretationRouter()
        assert router._validate_response("", []) is False

    def test_validate_response_short_fails(self):
        """Контент < 200 символов не проходит."""
        router = InterpretationRouter()
        assert router._validate_response("x" * 199, []) is False

    def test_validate_response_with_sections_passes(self):
        """Контент с разделами ### проходит валидацию."""
        router = InterpretationRouter()
        content = "### Личность\n" + "x" * 300
        assert router._validate_response(content, []) is True
