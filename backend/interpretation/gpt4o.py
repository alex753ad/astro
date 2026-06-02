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
from backend.interpretation.prompts import build_system_prompt

logger = logging.getLogger("astro.gpt4o")


class GPT4oEngine(InterpretationEngine):
    name = "gpt4o"

    def __init__(self):
        self._settings = get_settings()
        self._base_url = "https://api.openai.com/v1"
        self._model = "gpt-4o"

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, request: InterpretationRequest, stream: bool = False) -> dict:
        system_prompt = build_system_prompt(request)
        user_msg = (
            "Напиши интерпретацию натальной карты по указанным сферам."
            if request.language == "ru"
            else "Write a natal chart interpretation for the specified spheres."
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 8000 if request.tier == "premium" else (6000 if request.tier == "pro" else 2000),
            "temperature": 0.7,
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
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
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
