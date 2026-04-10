"""Interpretation router with retry and fallback chain.

Execution order: GPT-4o → DeepSeek V3 → Template engine.
Each step has retry logic with exponential backoff.
Daily budget tracking prevents overspending on AI APIs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

from backend.cache import interpretation_cache, make_profile_hash
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

# ── Budget tracking ──
_daily_spend: dict[str, float] = {}  # date_str → total_usd
_COST_PER_1K_TOKENS = {
    "gpt4o": 0.005,     # ~$5/M tokens (input+output average)
    "deepseek": 0.0003,  # ~$0.27/M tokens
    "template": 0.0,
}


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

        # Check cache first
        profile_hash = make_profile_hash(request.natal_profile)
        cached = interpretation_cache.get(f"interp:{profile_hash}")
        if cached:
            logger.info("Cache hit for profile %s", profile_hash[:8])
            return InterpretationResult(
                content=cached["content"],
                sections=cached.get("sections"),
                engine=cached["engine"],
                cached=True,
            )

        # Try each engine in order
        last_error = None
        for engine in self._engines:
            if not self._check_budget(engine.name):
                logger.warning("Budget exceeded for %s, skipping", engine.name)
                continue

            try:
                result = await self._try_engine(engine, request)
                if result and self._validate_response(result.content, request.sections):
                    # Cache the result (30 days TTL)
                    interpretation_cache.set(
                        f"interp:{profile_hash}",
                        {"content": result.content, "sections": result.sections, "engine": result.engine},
                        ttl=30 * 24 * 3600,
                    )
                    self._track_spend(engine.name, result.tokens_used)
                    return result
                else:
                    logger.warning("Validation failed for %s response", engine.name)
            except Exception as e:
                last_error = e
                logger.error("Engine %s failed: %s", engine.name, str(e))
                continue

        # All engines failed — this shouldn't happen because TemplateEngine always works
        logger.critical("All interpretation engines failed!")
        return InterpretationResult(
            content="Интерпретация временно недоступна. Пожалуйста, попробуйте позже.",
            engine="none",
        )

    async def stream(self, request: InterpretationRequest) -> AsyncIterator[str]:
        """Stream interpretation with fallback chain."""

        for engine in self._engines:
            if not self._check_budget(engine.name):
                continue
            try:
                async for chunk in self._try_stream(engine, request):
                    yield chunk
                return  # Success — stop trying other engines
            except Exception as e:
                logger.error("Stream from %s failed: %s", engine.name, str(e))
                continue

        # All failed
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
        if engine_name == "template":
            return True  # always free

        today = time.strftime("%Y-%m-%d")
        spent = _daily_spend.get(today, 0.0)
        return spent < self._settings.ai_daily_budget_usd

    def _track_spend(self, engine_name: str, tokens_used: int) -> None:
        """Track API spending."""
        if engine_name == "template" or tokens_used == 0:
            return

        cost = (tokens_used / 1000) * _COST_PER_1K_TOKENS.get(engine_name, 0)
        today = time.strftime("%Y-%m-%d")
        _daily_spend[today] = _daily_spend.get(today, 0.0) + cost
        logger.info("Spent $%.4f on %s (%d tokens). Daily total: $%.4f",
                     cost, engine_name, tokens_used, _daily_spend[today])

    async def get_status(self) -> dict:
        """Return status of all engines."""
        status = {}
        for engine in self._engines:
            status[engine.name] = await engine.health_check()
        today = time.strftime("%Y-%m-%d")
        status["daily_spend_usd"] = round(_daily_spend.get(today, 0.0), 4)
        status["daily_budget_usd"] = self._settings.ai_daily_budget_usd
        return status


# ── Singleton ──
_router: InterpretationRouter | None = None


def get_router() -> InterpretationRouter:
    global _router
    if _router is None:
        _router = InterpretationRouter()
    return _router
