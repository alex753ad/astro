"""Interpretation router — цепочка движков интерпретации.

⚠️ Заголовок этого модуля до 23.08.2026 гласил «GPT-4o → DeepSeek → Template
fallback chain». Это неверно и вводило в заблуждение: реальный порядок строит
`_engines_for_tier` ниже, и **DeepSeek стоит первым всегда**, включая pro и
premium. GPT-4o вообще попадает в список только для pro/premium и только как
запасной вариант, если DeepSeek упал или не прошёл валидацию ответа:

    DeepSeek v4-pro → [GPT-4o, если pro/premium] → Template

`select_model` возвращает «предпочтительный» движок, но им определяется лишь,
попадёт ли GPT-4o в очередь, — первым он не становится никогда. Модель DeepSeek
одна на все тарифы (`TIER_FLAGS[*]["ai_engine"]` == `deepseek_model_pro`),
тариф регулирует глубину через `interpretation_word_limit`, а не выбор модели
(решение владельца 19.08.2026, см. CLAUDE.md, раздел «AI-контуры»).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from typing import AsyncIterator

from backend.async_utils import iter_with_deadline
from backend.cache import interpretation_cache, make_profile_hash, budget_tracker
from backend.interpretation.base import (
    InterpretationEngine,
    InterpretationRequest,
    InterpretationResult,
)
from backend.interpretation.deepseek import DeepSeekEngine
from backend.interpretation.gpt4o import GPT4oEngine, _TOKENS_PER_WORD
from backend.interpretation.prompts import resolve_word_limit
from backend.interpretation.template import TemplateEngine
from backend.config import get_settings

logger = logging.getLogger("astro.router")

# 20.08.2026: тот же изъян, что и в чате (rag_router.py) — httpx read-timeout
# в deepseek.py/gpt4o.py сбрасывается на каждый успешный чанк и не даёт
# реального потолка на весь стрим (trickle-байты держат соединение сколько
# угодно). _try_stream ниже вообще не имел общего таймаута — в отличие от
# нестримингового _try_engine (asyncio.wait_for(..., timeout=30.0) чуть выше).
#
# Фиксированное число сюда не подходит: интерпретации сильно длиннее чата
# (до 5000 слов на Orion), нужен предел, растущий вместе с целевым объёмом.
# Считаем той же формулой, что и max_tokens (_TOKENS_PER_WORD в gpt4o.py), с
# консервативной (намеренно заниженной) оценкой скорости генерации — реальной
# телеметрии нет (боевого ключа DeepSeek нет в dev-окружении), а резать
# легитимный длинный текст премиум-тарифа хуже, чем подождать лишнее.
_STREAM_TOKENS_PER_SEC = 20.0
_STREAM_TIMEOUT_BUFFER_SEC = 20.0


def _stream_deadline_seconds(request: InterpretationRequest) -> float:
    target_tokens = resolve_word_limit(request) * _TOKENS_PER_WORD
    return target_tokens / _STREAM_TOKENS_PER_SEC + _STREAM_TIMEOUT_BUFFER_SEC


class IncompleteInterpretation(Exception):
    """Стрим оборвался или был обрезан по длине — не полный ответ.

    Поднимается из InterpretationRouter.stream(), когда finish_reason
    провайдера не "stop" (например "length") или соединение разорвалось после
    того, как часть текста уже ушла. Вызывающая сторона (SSE-эндпоинт) должна
    поймать это отдельно от прочих ошибок: не засчитывать интерпретацию как
    использованную и показать пользователю явную ошибку вместо [DONE].
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


_COST_PER_1K_TOKENS = {
    "gpt4o": 0.005,
    "deepseek": 0.0003,
    "template": 0.0,
}


def select_model(tier: str, is_cached: bool = False) -> str:
    """Return engine name based on user tier and cache state."""
    if tier == "free":
        return "deepseek"
    if tier == "premium":
        return "gpt4o"
    if tier == "pro":
        return "deepseek" if is_cached else "gpt4o"
    return "deepseek"  # lite


def _engines_for_tier(
    engines: list,
    tier: str,
    is_cached: bool = False,
) -> list:
    """Return ordered engine list filtered by tier preference."""
    preferred = select_model(tier, is_cached)
    name_map = {e.name: e for e in engines}
    template = name_map.get("template")

    if preferred == "gpt4o":
        order = ["deepseek", "gpt4o", "template"]
    else:
        order = ["deepseek", "template"]

    result = [name_map[n] for n in order if n in name_map]
    if template and template not in result:
        result.append(template)
    return result


def _log_ai_request(
    engine: str,
    latency_ms: int,
    tokens_used: int,
    tokens_cost_usd: float,
    fallback_triggered: bool,
    cache_hit: bool,
) -> None:
    """Log AI request in structured JSON format to stdout."""
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": "ai_request",
        "engine": engine,
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
        "tokens_cost_usd": round(tokens_cost_usd, 6),
        "fallback_triggered": fallback_triggered,
        "cache_hit": cache_hit,
    }
    print(json.dumps(log_entry), file=sys.stdout, flush=True)


class InterpretationRouter:
    """Routes interpretation requests through a fallback chain.

    Chain: GPT-4o → DeepSeek → Templates
    Features:
    - Retry with exponential backoff (3 attempts)
    - Automatic fallback on failure
    - Response validation
    - Daily budget tracking
    - Result caching (keyed by profile_hash + word_limit to avoid cross-contamination)
    """

    def __init__(self):
        self._engines: list[InterpretationEngine] = [
            DeepSeekEngine(),
            GPT4oEngine(),
            TemplateEngine(),
        ]
        self._settings = get_settings()

    async def generate(self, request: InterpretationRequest) -> InterpretationResult:
        """Generate interpretation with full fallback chain."""
        start_time = time.time()

        # Cache key includes word_limit so requests with different limits
        # never share the same cached result. Callers that pass custom_prompt
        # (broadcasts, briefs — same natal profile, different content each
        # time: transits differ month to month) also fold a hash of the
        # prompt in, otherwise they'd all collide on profile_hash alone and
        # a later call would silently get an earlier month's stale text.
        profile_hash = make_profile_hash(request.natal_profile)
        wl_key = str(request.word_limit) if request.word_limit else f"tier_{request.tier}"
        cache_key = f"interp:{profile_hash}:{wl_key}"
        if request.custom_prompt:
            prompt_hash = hashlib.sha256(request.custom_prompt.encode()).hexdigest()[:12]
            cache_key = f"{cache_key}:{prompt_hash}"

        cached = interpretation_cache.get(cache_key)
        if cached:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info("Cache hit for profile %s (wl=%s)", profile_hash[:8], wl_key)
            _log_ai_request(
                engine=cached["engine"],
                latency_ms=latency_ms,
                tokens_used=0,
                tokens_cost_usd=0.0,
                fallback_triggered=False,
                cache_hit=True,
            )
            return InterpretationResult(
                content=cached["content"],
                sections=cached.get("sections"),
                engine=cached["engine"],
                cached=True,
            )

        last_error = None
        fallback_triggered = False

        # If daily budget is exhausted — jump straight to template engine
        budget_ok = budget_tracker.is_within_budget(self._settings.ai_daily_budget_usd, "gpt4o")
        if not budget_ok:
            logger.warning(
                "Daily AI budget exceeded ($%.2f) — forcing template engine",
                budget_tracker.get_spent(),
            )
            fallback_triggered = True
            engines_to_try = [self._engines[-1]]  # TemplateEngine only
        else:
            engines_to_try = _engines_for_tier(
                self._engines, request.tier, is_cached=bool(cached)
            )

        for engine in engines_to_try:
            if not self._check_budget(engine.name):
                logger.warning("Budget exceeded for %s, skipping", engine.name)
                fallback_triggered = True
                continue

            try:
                engine_start = time.time()
                result = await self._try_engine(engine, request)
                latency_ms = int((time.time() - engine_start) * 1000)

                if result and self._validate_response(result.content, request.sections, request.context):
                    interpretation_cache.set(
                        cache_key,
                        {
                            "content": result.content,
                            "sections": result.sections,
                            "engine": result.engine,
                        },
                        ttl=30 * 24 * 3600,
                    )
                    cost = self._track_spend(engine.name, result.tokens_used)
                    _log_ai_request(
                        engine=engine.name,
                        latency_ms=latency_ms,
                        tokens_used=result.tokens_used,
                        tokens_cost_usd=cost,
                        fallback_triggered=fallback_triggered,
                        cache_hit=False,
                    )
                    return result
                else:
                    logger.warning("Validation failed for %s response", engine.name)
                    fallback_triggered = True
            except Exception as e:
                last_error = e
                logger.error("Engine %s failed: %s", engine.name, str(e))
                fallback_triggered = True

        logger.critical("All interpretation engines failed! last_error=%s", last_error)
        latency_ms = int((time.time() - start_time) * 1000)
        _log_ai_request(
            engine="none",
            latency_ms=latency_ms,
            tokens_used=0,
            tokens_cost_usd=0.0,
            fallback_triggered=True,
            cache_hit=False,
        )
        return InterpretationResult(
            content="Интерпретация временно недоступна. Пожалуйста, попробуйте позже.",
            engine="none",
        )

    async def interpret(self, request: InterpretationRequest) -> AsyncIterator[str]:
        """Alias for stream() — used by integration tests and SSE endpoints."""
        async for chunk in self.stream(request):
            yield chunk

    async def stream(self, request: InterpretationRequest) -> AsyncIterator[str]:
        """Stream interpretation with fallback chain, caching, and truncation
        detection.

        Once any chunk has been yielded the SSE channel is open and headers
        have been sent — switching engines would produce duplicate text.

        Кэш — "одна карта, одна интерпретация": ключ включает tier И точную
        модель (model_for), чтобы Flash- и Pro-тексты не смешивались. Кэшируется
        только полный ответ (finish_reason == "stop") — обрезанный по длине или
        оборванный связью поток не сохраняется и поднимает
        IncompleteInterpretation, чтобы вызывающая сторона (SSE-эндпоинт) не
        засчитала интерпретацию как использованную и показала явную ошибку
        вместо тихого [DONE].
        """
        profile_hash = make_profile_hash(request.natal_profile)
        wl_key = str(request.word_limit) if request.word_limit else f"tier_{request.tier}"

        budget_ok = budget_tracker.is_within_budget(self._settings.ai_daily_budget_usd, "gpt4o")
        stream_engines = (
            [self._engines[-1]]
            if not budget_ok
            else _engines_for_tier(self._engines, request.tier)
        )
        if not budget_ok:
            logger.warning("Daily AI budget exceeded — stream forced to template")

        for engine in stream_engines:
            if not self._check_budget(engine.name):
                continue

            # Шаблон детерминирован сам по себе — кэшировать нечего, и у него
            # нет осмысленного finish_reason.
            cache_key = None
            if engine.name != "template":
                model_id = engine.model_for(request)
                cache_key = f"stream:{profile_hash}:{request.tier}:{model_id}:{wl_key}"
                cached = interpretation_cache.get(cache_key)
                if cached:
                    logger.info(
                        "Stream cache hit for profile %s (%s/%s)",
                        profile_hash[:8], request.tier, model_id,
                    )
                    yield cached["content"]
                    return

            collected: list[str] = []
            yielded_any = False
            try:
                async for chunk in self._try_stream(engine, request):
                    yielded_any = True
                    collected.append(chunk)
                    yield chunk

                tokens = getattr(engine, "_last_stream_tokens", 0) or 0
                self._track_spend(engine.name, tokens)

                if cache_key is not None:
                    finish_reason = getattr(engine, "_last_finish_reason", None)
                    if finish_reason == "stop":
                        interpretation_cache.set(
                            cache_key,
                            {"content": "".join(collected), "engine": engine.name},
                            ttl=30 * 24 * 3600,
                        )
                    else:
                        logger.warning(
                            "%s stream ended with finish_reason=%s — not caching",
                            engine.name, finish_reason,
                        )
                        raise IncompleteInterpretation(finish_reason or "connection_lost")
                return  # success

            except IncompleteInterpretation:
                raise  # уже залогировано выше — наверх, пусть эндпоинт не засчитывает попытку
            except Exception as e:
                logger.error("Stream from %s failed: %s", engine.name, str(e))
                if yielded_any:
                    logger.warning(
                        "Engine %s failed mid-stream — aborting to prevent duplicate content.",
                        engine.name,
                    )
                    raise IncompleteInterpretation("connection_lost") from e
                continue  # no chunks yet — try next engine

        yield "Интерпретация временно недоступна. Пожалуйста, попробуйте позже."

    async def _try_engine(
        self,
        engine: InterpretationEngine,
        request: InterpretationRequest,
        max_retries: int | None = None,
    ) -> InterpretationResult | None:
        """Try an engine with exponential backoff retries."""
        if max_retries is None:
            max_retries = self._settings.ai_max_retries
        delays = [1.0, 3.0, 9.0]

        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    engine.generate(request),
                    timeout=30.0,
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(
                    "%s timed out (attempt %d/%d)", engine.name, attempt + 1, max_retries
                )
            except Exception as e:
                logger.warning(
                    "%s error (attempt %d/%d): %s",
                    engine.name, attempt + 1, max_retries, str(e),
                )

            if attempt < max_retries - 1:
                await asyncio.sleep(delays[attempt])

        return None

    async def _try_stream(
        self,
        engine: InterpretationEngine,
        request: InterpretationRequest,
    ) -> AsyncIterator[str]:
        """Try streaming from an engine (single attempt)."""
        chunks_received = 0
        deadline = _stream_deadline_seconds(request)
        async for chunk in iter_with_deadline(engine.stream(request), deadline):
            chunks_received += 1
            yield chunk

        if chunks_received == 0:
            raise RuntimeError(f"No chunks received from {engine.name}")

    def _validate_response(self, content: str, expected_sections: list[str], context: str = "natal") -> bool:
        if not content or len(content) < 100:
            return False
        # Проверка ниже ищет натальные ключевые слова и осмысленна только для
        # натальной интерпретации. Остальные контексты пишут о своём (транзиты,
        # год соляра, совместимость, смена домов) и забраковывались бы зря.
        if context != "natal":
            return True
        return "###" in content or any(
            w in content.lower()
            for w in ["личност", "карьер", "отношен", "personality", "career"]
        )

    def _check_budget(self, engine_name: str) -> bool:
        return budget_tracker.is_within_budget(
            self._settings.ai_daily_budget_usd, engine_name
        )

    def _track_spend(self, engine_name: str, tokens_used: int) -> float:
        if engine_name == "template" or tokens_used == 0:
            return 0.0
        cost = (tokens_used / 1000) * _COST_PER_1K_TOKENS.get(engine_name, 0)
        new_total = budget_tracker.add_spend(cost)
        logger.info(
            "Spent $%.4f on %s (%d tokens). Daily total: $%.4f",
            cost, engine_name, tokens_used, new_total,
        )
        return cost

    async def get_status(self) -> dict:
        status = {}
        for engine in self._engines:
            status[engine.name] = await engine.health_check()
        status["daily_spend_usd"] = round(budget_tracker.get_spent(), 4)
        status["daily_budget_usd"] = self._settings.ai_daily_budget_usd
        return status


# ── Singleton ──
_router: InterpretationRouter | None = None


def get_router() -> InterpretationRouter:
    global _router
    if _router is None:
        _router = InterpretationRouter()
    return _router
