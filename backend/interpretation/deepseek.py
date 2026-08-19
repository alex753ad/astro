"""DeepSeek V3 interpretation engine.

Fallback AI provider — cheaper, good quality.
API is OpenAI-compatible, so reuses most GPT-4o logic.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from backend.config import get_settings
from backend.interpretation.base import (
    InterpretationEngine,
    InterpretationRequest,
    InterpretationResult,
)
from backend.interpretation.gpt4o import _parse_sections, _calc_max_tokens
from backend.interpretation.prompts import build_system_prompt

logger = logging.getLogger("astro.deepseek")


class DeepSeekEngine(InterpretationEngine):
    name = "deepseek"

    def __init__(self):
        self._settings = get_settings()
        self._base_url = "https://api.deepseek.com/v1"

    @staticmethod
    def _model_for_tier(tier: str) -> str:
        """deepseek-chat/deepseek-reasoner были отключены DeepSeek 2026-07-24 —
        текущие модели различаются по тарифу (TIER_FLAGS.ai_engine, заведено
        под config.deepseek_model_flash/_pro, а не зашито строкой здесь)."""
        from backend.auth.rate_limits import TIER_FLAGS
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["lite"])
        return flags["ai_engine"]

    def model_for(self, request: InterpretationRequest) -> str:
        return self._model_for_tier(request.tier)

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, request: InterpretationRequest, stream: bool = False) -> dict:
        if request.custom_prompt:
            messages = [{"role": "user", "content": request.custom_prompt}]
        else:
            system_prompt = build_system_prompt(request)
            if getattr(request, "author_context", None):
                system_prompt = system_prompt + "\n\n" + request.author_context
            user_msg = (
                "Напиши интерпретацию натальной карты по указанным сферам."
                if request.language == "ru"
                else "Write a natal chart interpretation for the specified spheres."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]
        payload = {
            "model": self._model_for_tier(request.tier),
            "messages": messages,
            "max_tokens": _calc_max_tokens(request),
            "temperature": 0.2,
            "stream": stream,
            # DeepSeek V4 — reasoning-модель по умолчанию (thinking.reasoning_effort
            # = "high", если не задано явно) и тратит max_tokens на reasoning_content
            # ДО финального ответа. Проверено эмпирически: без этого короткие
            # max_tokens дают finish_reason=length с ПУСТЫМ content, не просто
            # обрезанным текстом. Reasoning нам не нужен — натальная интерпретация
            # не логическая задача, а связный текст по уже посчитанным фактам.
            "thinking": {"type": "disabled"},
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def generate(self, request: InterpretationRequest) -> InterpretationResult:
        payload = self._build_payload(request, stream=False)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        sections = _parse_sections(content)

        return InterpretationResult(
            content=content,
            sections=sections,
            engine=self.name,
            tokens_used=tokens,
        )

    async def stream(self, request: InterpretationRequest) -> AsyncIterator[str]:
        payload = self._build_payload(request, stream=True)
        self._last_stream_tokens = 0
        # None до первого чанка с непустым finish_reason. Остаётся None, если
        # соединение оборвалось раньше, чем провайдер прислал финальный чанк —
        # это отличает разрыв связи от штатного "stop"/"length" для router.stream().
        self._last_finish_reason = None

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        if "usage" in chunk and chunk["usage"] is not None:
                            self._last_stream_tokens = chunk["usage"].get("total_tokens", 0)
                        choice = chunk.get("choices", [{}])[0]
                        finish_reason = choice.get("finish_reason")
                        if finish_reason:
                            self._last_finish_reason = finish_reason
                        delta = choice.get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def health_check(self) -> bool:
        if not self._settings.deepseek_api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers=self._headers,
                )
                return resp.status_code == 200
        except Exception:
            return False
