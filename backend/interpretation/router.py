"""Interpretation router with retry and fallback chain.

Execution order: GPT-4o → DeepSeek V3 → Template engine.
Each step has retry logic with exponential backoff.
Daily budget tracking prevents overspending on AI APIs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import AsyncIterator

from backend.cache import interpretation_cache, make_profile_hash, budget_tracker
from backend.interpretation.base import (
    InterpretationEngine,
    InterpretationRequest,
    InterpretationResult,
)
from backend.interpretation.gpt4o import GPT4oEngine
from backend.interpretation.deepseek import DeepSeekEngine
from backend.interpretation.template import TemplateEngine
from backend.config import get_settings

logger = logging.getLogger("astro.router")

_COST_PER_1K_TOKENS = {
    "gpt4o": 0.005,
    "deepseek": 0.0003,
    "template": 0.0,
}


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
    - Result caching
    """

    def __init__(self):
        self._engines: list[InterpretationEngine] = [
            GPT4oEngine(),
            DeepSeekEngine(),
            TemplateEngine(),
        ]
        self._settings = get_settings()

    async def generate(self, request: InterpretationRequest) -> InterpretationResult:
        """Generate interpretation with full fallback chain."""
        start_time = time.time()

        # Check cache first
        profile_hash = make_profile_hash(request.natal_profile)
        cached = interpretation_cache.get(f"interp:{profile_hash}")
        if cached:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info("Cache hit for profile %s", profile_hash[:8])
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

        # Try each engine in order
        last_error = None
        fallback_triggered = False
        engine_index = 0
        
        for engine in self._engines:
            if not self._check_budget(engine.name):
                logger.warning("Budget exceeded for %s, skipping", engine.name)
                fallback_triggered = True
                engine_index += 1
                continue

            try:
                engine_start = time.time()
                result = await self._try_engine(engine, request)
                latency_ms = int((time.time() - engine_start) * 1000)
                
                if result and self._validate_response(result.content, request.sections):
                    # Cache the result (30 days TTL)
                    interpretation_cache.set(
                        f"interp:{profile_hash}",
                        {"content": result.content, "sections": result.sections, "engine": result.engine},
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
            
            engine_index += 1

        # All engines failed — this shouldn't happen because TemplateEngine always works
        logger.critical("All interpretation engines failed!")
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

    async def stream(self, request: InterpretationRequest) -> AsyncIterator[str]:
        """Stream interpretation with fallback chain.

        Once any chunk has been yielded (yielded_any=True) the SSE channel is
        already open and HTTP headers have been sent — switching to a fallback
        engine would produce duplicate/garbled text.  If the active engine
        fails mid-stream we log and close the connection instead of cascading.
        """
        for engine in self._engines:
            if not self._check_budget(engine.name):
                continue

            yielded_any = False
            try:
                async for chunk in self._try_stream(engine, request):
                    yielded_any = True
                    yield chunk

                # Track tokens from stream if engine stored them
                tokens = getattr(engine, "_last_stream_tokens", 0) or 0
                self._track_spend(engine.name, tokens)
                return  # Success

            except Exception as e:
                logger.error("Stream from %s failed: %s", engine.name, str(e))
                if yielded_any:
                    # Stream already started — cannot switch engine safely
                    logger.warning(
                        "Engine %s failed mid-stream after yielding chunks; "
                        "aborting fallback to prevent duplicate content.",
                        engine.name,
                    )
                    return
                # No chunks sent yet — safe to try next engine
                continue

        # All engines failed before yielding anything
        yield "Интерпретация временно недоступна. Пожалуйста, попробуйте позже."

    async def _try_engine(
        self,
        engine: InterpretationEngine,
        request: InterpretationRequest,
        max_retries: int = 3,
    ) -> InterpretationResult | None:
        """Try an engine with exponential backoff retries."""
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
                    engine.name, attempt + 1, max_retries, str(e)
                )

            if attempt < max_retries - 1:
                await asyncio.sleep(delays[attempt])

        return None

    async def _try_stream(
        self,
        engine: InterpretationEngine,
        request: InterpretationRequest,
    ) -> AsyncIterator[str]:
        """Try streaming from an engine (single attempt with timeout)."""
        chunks_received = 0
        async for chunk in engine.stream(request):
            chunks_received += 1
            yield chunk

        if chunks_received == 0:
            raise RuntimeError(f"No chunks received from {engine.name}")

    def _validate_response(self, content: str, expected_sections: list[str]) -> bool:
        """Validate that the AI response is usable.

        Checks:
        - Not empty
        - Minimum length (at least 200 chars)
        - Contains at least some section markers
        """
        if not content or len(content) < 200:
            return False

        # Check for at least one section marker
        has_sections = "###" in content or any(
            section_word in content.lower()
            for section_word in ["личност", "карьер", "отношен", "personality", "career"]
        )

        return has_sections

    def _check_budget(self, engine_name: str) -> bool:
        """Check if daily budget allows using this engine."""
        return budget_tracker.is_within_budget(
            self._settings.ai_daily_budget_usd, engine_name
        )

    def _track_spend(self, engine_name: str, tokens_used: int) -> float:
        """Track API spending in Redis and return cost."""
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
        """Return status of all engines."""
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
