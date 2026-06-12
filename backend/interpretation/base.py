"""Abstract base class for interpretation engines.

All AI providers implement this interface, allowing hot-swap
between GPT-4o, DeepSeek, and template-based fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class InterpretationRequest:
    """Input for interpretation generation."""
    natal_profile: dict          # full chart data (planets, houses, aspects)
    context: str = "natal"       # natal | transit | synastry
    language: str = "ru"         # response language
    sections: list[str] = field(default_factory=lambda: [
        "general", "career", "relationships", "health", "finance", "spirituality"
    ])
    tier: str = "free"           # free | lite | pro | premium
    word_limit: int | None = None  # явный лимит слов (1000-5000), перекрывает tier
    custom_prompt: str | None = None  # если задан — используется вместо стандартного


@dataclass
class InterpretationResult:
    """Output from interpretation generation."""
    content: str                           # full text
    sections: dict[str, str] | None = None # keyed by section name
    engine: str = ""                       # which engine was used
    tokens_used: int = 0
    cached: bool = False


class InterpretationEngine(ABC):
    """Abstract interpretation engine interface.

    Implementations:
    - GPT4oEngine      — OpenAI GPT-4o (primary)
    - DeepSeekEngine    — DeepSeek V3 (fallback)
    - TemplateEngine    — rule-based templates (emergency fallback)
    """

    name: str = "base"

    @abstractmethod
    async def generate(self, request: InterpretationRequest) -> InterpretationResult:
        """Generate a complete interpretation synchronously."""
        ...

    @abstractmethod
    async def stream(self, request: InterpretationRequest) -> AsyncIterator[str]:
        """Stream interpretation token by token via SSE."""
        ...

    async def health_check(self) -> bool:
        """Check if the engine is available."""
        return True
