"""tests/test_ai_cascade.py — тест каскада AI fallback.

Каскад: GPT4oEngine → DeepSeekEngine → TemplateEngine

Патчим инстансы напрямую через router._engines[i],
т.к. роутер создаёт инстансы в __init__.

Запуск: pytest backend/tests/test_ai_cascade.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.interpretation.router import InterpretationRouter
from backend.interpretation.base import InterpretationRequest, InterpretationResult
from backend.interpretation.template import TemplateEngine
from backend.cache import budget_tracker


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
    return InterpretationResult(
        content=(
            "### Личность\n"
            "Солнце в Козероге говорит о целеустремлённости и дисциплине. "
            "Вы методичны и практичны в достижении карьерных целей. "
            "Луна в Тельце добавляет эмоциональную стабильность.\n\n"
            "### Карьера\n"
            "Профессиональная сфера — главный приоритет. Успех через терпение."
        ),
        engine=engine,
        tokens_used=150,
    )


def _router_with_mocks(gpt_result=None, gpt_error=None,
                        ds_result=None, ds_error=None,
                        tmpl_result=None):
    """Создать роутер с замоканными engine-инстансами."""
    router = InterpretationRouter()

    if gpt_error:
        router._engines[0].generate = AsyncMock(side_effect=gpt_error)
    else:
        router._engines[0].generate = AsyncMock(
            return_value=gpt_result or _good_result("gpt4o")
        )

    if ds_error:
        router._engines[1].generate = AsyncMock(side_effect=ds_error)
    else:
        router._engines[1].generate = AsyncMock(
            return_value=ds_result or _good_result("deepseek")
        )

    router._engines[2].generate = AsyncMock(
        return_value=tmpl_result or _good_result("template")
    )

    return router


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Фикстуры ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_budget():
    budget_tracker._local.clear()
    yield
    budget_tracker._local.clear()


@pytest.fixture(autouse=True)
def clear_cache():
    from backend.cache import interpretation_cache
    if hasattr(interpretation_cache, "clear"):
        interpretation_cache.clear()
    yield


@pytest.fixture(autouse=True)
def single_retry():
    """max_retries=1 — тесты видят ['gpt4o','deepseek','template'], а не ретраи.

    Патчим self._settings на каждом новом инстансе через монкей-патч
    InterpretationRouter.__init__, т.к. lru_cache не позволяет подменить get_settings.
    """
    original_init = InterpretationRouter.__init__

    def patched_init(self_router, *args, **kwargs):
        original_init(self_router, *args, **kwargs)
        self_router._settings = MagicMock()
        self_router._settings.ai_max_retries = 1
        self_router._settings.ai_daily_budget_usd = 10.0

    with patch.object(InterpretationRouter, "__init__", patched_init):
        yield


# ═══════════════════════════════════════════════════════════
# GPT-4o — успешный путь
# ═══════════════════════════════════════════════════════════

class TestGenerateGPT4oSuccess:
    def test_gpt4o_called_first(self):
        router = _router_with_mocks()
        _run(router.generate(_request()))
        router._engines[0].generate.assert_called_once()

    def test_gpt4o_result_returned_directly(self):
        router = _router_with_mocks()
        result = _run(router.generate(_request()))
        router._engines[1].generate.assert_not_called()
        assert result.engine == "gpt4o"

    def test_result_is_cached_after_gpt4o(self):
        router = _router_with_mocks()
        _run(router.generate(_request()))
        result2 = _run(router.generate(_request()))
        assert result2.cached is True
        assert router._engines[0].generate.call_count == 1


# ═══════════════════════════════════════════════════════════
# GPT-4o падает → DeepSeek
# ═══════════════════════════════════════════════════════════

class TestFallbackToDeepSeek:
    def test_gpt4o_exception_falls_back_to_deepseek(self):
        router = _router_with_mocks(gpt_error=Exception("OpenAI down"))
        result = _run(router.generate(_request()))
        router._engines[1].generate.assert_called()
        assert result.engine == "deepseek"

    def test_gpt4o_timeout_falls_back_to_deepseek(self):
        router = _router_with_mocks(gpt_error=asyncio.TimeoutError())
        result = _run(router.generate(_request()))
        assert result.engine == "deepseek"

    def test_deepseek_called_after_gpt4o_failure(self):
        call_order = []

        async def _fail(*a, **kw):
            call_order.append("gpt4o")
            raise Exception("fail")

        async def _ok(*a, **kw):
            call_order.append("deepseek")
            return _good_result("deepseek")

        router = InterpretationRouter()
        router._engines[0].generate = _fail
        router._engines[1].generate = _ok
        router._engines[2].generate = AsyncMock(return_value=_good_result("template"))

        _run(router.generate(_request()))
        assert "gpt4o" in call_order
        assert "deepseek" in call_order
        assert call_order.index("gpt4o") < call_order.index("deepseek")


# ═══════════════════════════════════════════════════════════
# Оба AI падают → Template
# ═══════════════════════════════════════════════════════════

class TestFallbackToTemplate:
    def test_both_ai_fail_uses_template(self):
        router = _router_with_mocks(
            gpt_error=Exception("GPT fail"),
            ds_error=Exception("DS fail"),
        )
        result = _run(router.generate(_request()))
        router._engines[2].generate.assert_called()
        assert result.engine == "template"

    def test_template_engine_always_returns_content(self):
        engine = TemplateEngine()
        result = _run(engine.generate(_request()))
        assert isinstance(result, InterpretationResult)
        assert len(result.content) > 0

    def test_cascade_order_strict(self):
        call_order = []

        async def _fail_gpt(*a, **kw):
            call_order.append("gpt4o")
            raise Exception("fail")

        async def _fail_ds(*a, **kw):
            call_order.append("deepseek")
            raise Exception("fail")

        async def _tmpl(*a, **kw):
            call_order.append("template")
            return _good_result("template")

        router = InterpretationRouter()
        router._engines[0].generate = _fail_gpt
        router._engines[1].generate = _fail_ds
        router._engines[2].generate = _tmpl

        _run(router.generate(_request()))
        assert call_order == ["gpt4o", "deepseek", "template"]


# ═══════════════════════════════════════════════════════════
# Retry-логика
# ═══════════════════════════════════════════════════════════

class TestRetryLogic:
    def test_gpt4o_retried_3_times_before_fallback(self):
        call_count = 0

        async def _fail(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise Exception("transient")

        router = InterpretationRouter()
        router._settings.ai_max_retries = 3
        router._engines[0].generate = _fail
        router._engines[1].generate = AsyncMock(return_value=_good_result("deepseek"))
        router._engines[2].generate = AsyncMock(return_value=_good_result("template"))

        sleep_calls = []

        async def _fake_sleep(s):
            sleep_calls.append(s)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("backend.interpretation.router.asyncio.sleep", _fake_sleep)
            _run(router.generate(_request()))

        assert call_count == 3

    def test_retry_uses_exponential_backoff(self):
        async def _fail(*a, **kw):
            raise Exception("fail")

        router = InterpretationRouter()
        router._settings.ai_max_retries = 3
        router._engines[0].generate = _fail
        router._engines[1].generate = AsyncMock(return_value=_good_result("deepseek"))
        router._engines[2].generate = AsyncMock(return_value=_good_result("template"))

        sleep_calls = []

        async def _fake_sleep(s):
            sleep_calls.append(s)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("backend.interpretation.router.asyncio.sleep", _fake_sleep)
            _run(router.generate(_request()))

        assert len(sleep_calls) >= 2
        assert sleep_calls[0] == pytest.approx(1.0)
        assert sleep_calls[1] == pytest.approx(3.0)


# ═══════════════════════════════════════════════════════════
# Budget guard
# ═══════════════════════════════════════════════════════════

class TestBudgetGuard:
    def test_exceeded_budget_skips_gpt4o(self):
        router = _router_with_mocks(ds_error=Exception("also over budget"))

        with patch.object(budget_tracker, "get_spent", return_value=9999.0):
            _run(router.generate(_request()))

        router._engines[0].generate.assert_not_called()

    def test_template_not_blocked_by_budget(self):
        router = InterpretationRouter()
        assert router._check_budget("template") is True

    def test_budget_ok_allows_ai_engines(self):
        router = _router_with_mocks()
        _run(router.generate(_request()))
        router._engines[0].generate.assert_called_once()

    def test_spend_tracked_after_successful_call(self):
        import time
        router = _router_with_mocks(
            gpt_result=InterpretationResult(
                content="### Личность\n" + "x" * 300 + "\n### Карьера\n" + "y" * 100,
                engine="gpt4o",
                tokens_used=1000,
            )
        )
        _run(router.generate(_request()))
        assert budget_tracker.get_spent() > 0


# ═══════════════════════════════════════════════════════════
# Cache
# ═══════════════════════════════════════════════════════════

class TestCache:
    def test_cache_hit_skips_all_engines(self):
        router = _router_with_mocks()
        _run(router.generate(_request()))
        result2 = _run(router.generate(_request()))
        assert result2.cached is True
        assert router._engines[0].generate.call_count == 1

    def test_cache_miss_calls_engine(self):
        router = _router_with_mocks()
        result = _run(router.generate(_request()))
        router._engines[0].generate.assert_called_once()
        assert result.cached is False


# ═══════════════════════════════════════════════════════════
# stream()
# ═══════════════════════════════════════════════════════════

class TestStream:
    def test_stream_yields_chunks(self):
        router = InterpretationRouter()

        async def _fake_stream(req):
            for chunk in ["Солнце ", "в Козероге."]:
                yield chunk

        router._engines[0].stream = _fake_stream

        async def _collect():
            chunks = []
            async for c in router.stream(_request()):
                chunks.append(c)
            return "".join(chunks)

        result = _run(_collect())
        assert "Козероге" in result

    def test_stream_always_returns_something(self):
        router = InterpretationRouter()

        async def _empty(req):
            return
            yield

        router._engines[0].stream = _empty
        router._engines[1].stream = _empty

        async def _collect():
            chunks = []
            async for c in router.stream(_request()):
                chunks.append(c)
            return "".join(chunks)

        result = _run(_collect())
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════
# Валидация ответа
# ═══════════════════════════════════════════════════════════

class TestResponseValidation:
    def test_validate_response_empty_fails(self):
        router = InterpretationRouter()
        assert router._validate_response("", []) is False

    def test_validate_response_short_fails(self):
        router = InterpretationRouter()
        assert router._validate_response("x" * 199, []) is False

    def test_validate_response_with_sections_passes(self):
        router = InterpretationRouter()
        content = "### Личность\n" + "x" * 300
        assert router._validate_response(content, []) is True

    def test_short_response_triggers_fallback(self):
        router = InterpretationRouter()
        router._engines[0].generate = AsyncMock(return_value=InterpretationResult(
            content="Слишком короткий.",
            engine="gpt4o",
            tokens_used=5,
        ))
        router._engines[1].generate = AsyncMock(return_value=_good_result("deepseek"))
        router._engines[2].generate = AsyncMock(return_value=_good_result("template"))

        result = _run(router.generate(_request()))
        assert result.engine == "deepseek"
