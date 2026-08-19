"""GPT-4o interpretation engine.

Primary AI provider. Supports streaming via SSE.
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
from backend.interpretation.prompts import build_system_prompt, resolve_word_limit

logger = logging.getLogger("astro.gpt4o")

# Раньше здесь было ≈1 ток/слово плоским числом на тир — для кириллицы в
# BPE-токенизации это в 2-3 раза ниже реальности, из-за чего free/lite
# (плоские 2000 max_tokens) обрывались по длине раньше, чем добирали и
# половину запрошенного объёма.
#
# Проверено реальными запросами к deepseek-v4-flash/-pro на боевом промпте
# (thinking выключен), max_tokens намеренно завышен, чтобы поймать
# естественную точку остановки (finish_reason=stop) для каждого тира:
#   free    (цель  500 слов) → 1016 слов,  2125 токенов на выходе
#   lite    (цель  800 слов) → 1153 слова,  2413 токенов
#   pro     (цель 2500 слов) → 2511 слов,   5466 токенов
#   premium (цель 5000 слов) → 3938 слов,   8330 токенов
# ~2.1 ток/слово на выходе — близко к оценке, но короткие тиры модель
# систематически ПЕРЕВЫПОЛНЯЕТ (free — почти вдвое): 6 секций всё равно
# получают связные абзацы, даже если попросили меньше. Плоское
# «слова × ток/слово» этого не покрывает — отсюда аддитивный запас ниже,
# а не просто выросший коэффициент.
_TOKENS_PER_WORD = 2.5
_OVERSHOOT_AND_TAG_BUFFER = 1500


def _calc_max_tokens(request) -> int:
    """max_tokens — из целевого объёма слов (resolve_word_limit), не плоское
    число на тир. Единственный источник цели — TIER_FLAGS.interpretation_word_limit
    (через resolve_word_limit, см. prompts.py) — тот же, что и у инструкции
    модели в промпте, поэтому prompt и лимит токенов больше не расходятся."""
    words = resolve_word_limit(request)
    return int(words * _TOKENS_PER_WORD) + _OVERSHOOT_AND_TAG_BUFFER

class GPT4oEngine(InterpretationEngine):
    name = "gpt4o"

    def __init__(self):
        self._settings = get_settings()
        self._base_url = "https://api.openai.com/v1"
        self._model = "gpt-4o"

    def model_for(self, request: InterpretationRequest) -> str:
        return self._model

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
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
            "model": self._model,
            "messages": messages,
            "max_tokens": _calc_max_tokens(request),
            "temperature": 0.2,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def generate(self, request: InterpretationRequest) -> InterpretationResult:
        """Generate a complete interpretation (non-streaming)."""
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
        """Stream interpretation token by token."""
        payload = self._build_payload(request, stream=True)
        self._last_stream_tokens = 0
        # None до первого чанка с непустым finish_reason — остаётся None, если
        # соединение оборвалось раньше финального чанка (см. deepseek.py).
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
        if not self._settings.openai_api_key:
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


def _parse_sections(content: str) -> dict[str, str]:
    """Parse markdown-formatted sections from AI response."""
    sections: dict[str, str] = {}
    current_section = "general"
    current_text: list[str] = []

    for line in content.split("\n"):
        if line.startswith("### "):
            if current_text:
                sections[current_section] = "\n".join(current_text).strip()
            current_section = _normalize_section_name(line[4:].strip())
            current_text = []
        else:
            current_text.append(line)

    if current_text:
        sections[current_section] = "\n".join(current_text).strip()

    return sections


def _normalize_section_name(title: str) -> str:
    """Map section title to canonical key."""
    title_lower = title.lower()
    mappings = {
        "общий": "general", "портрет": "general", "личност": "general",
        "overview": "general", "personality": "general",
        "карьер": "career", "професс": "career", "career": "career",
        "отношен": "relationships", "партнёр": "relationships", "relationship": "relationships",
        "здоров": "health", "энерг": "health", "health": "health",
        "финанс": "finance", "материал": "finance", "finance": "finance",
        "духовн": "spirituality", "внутренн": "spirituality", "spiritual": "spirituality",
    }
    for key, val in mappings.items():
        if key in title_lower:
            return val
    return title_lower.replace(" ", "_")[:30]
