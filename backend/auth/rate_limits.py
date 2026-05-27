"""Per-tier rate limiting helpers.

Уровни доступа:
  Free:    charts unlimited, 1 interpretation/day (~500 слов), без транзитов
  Pro:     unlimited interpretations (2000 слов), транзиты до 6 мес, 10 профилей
  Premium: unlimited interpretations (5000 слов), транзиты до 12 мес, synastry, PDF

SlowAPI-лимиты на эндпоинты:
  POST /chart/calculate  : Free → 10/min, Pro/Premium → 60/min
  GET/POST /interpret    : Free → 1/min,  Pro/Premium → 20/min

Реализация:
  Каждый tier имеет свой ключ в Redis/памяти, поэтому счётчики независимы.
  Ключ строится из tier + идентификатора пользователя (токен или IP).
  Tier определяется middleware ДО вызова лимитера (см. main.py: TierMiddleware).
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import get_settings
from backend.models import User

settings = get_settings()


# ═══════════════════════════════════════════════════════════
# TIER FLAGS
# ═══════════════════════════════════════════════════════════

TIER_FLAGS: dict[str, dict] = {
    "free": {
        "interpretation_word_limit": 500,
        "interpretations_per_day": 1,
        "transits_months": 0,
        "profiles_limit": 1,
        "synastry": False,
        "pdf_export": False,
    },
    "pro": {
        "interpretation_word_limit": 2000,
        "interpretations_per_day": None,  # unlimited
        "transits_months": 6,
        "profiles_limit": 10,
        "synastry": False,
        "pdf_export": False,
    },
    "premium": {
        "interpretation_word_limit": 5000,
        "interpretations_per_day": None,
        "transits_months": 12,
        "profiles_limit": None,
        "synastry": True,
        "pdf_export": True,
    },
}

CHART_LIMIT_FREE     = "10/minute"
CHART_LIMIT_PRO      = "60/minute"
INTERPRET_LIMIT_FREE = "1/minute"
INTERPRET_LIMIT_PRO  = "20/minute"


def get_feature_flags(user: Optional[User]) -> dict:
    tier = user.tier if user else "free"
    flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
    return {
        "tier": tier,
        **flags,
        "transits": flags["transits_months"] > 0,
        "unlimited_interpretations": flags["interpretations_per_day"] is None,
        "pdf_reports": flags["pdf_export"],
    }


# ═══════════════════════════════════════════════════════════
# SLOWAPI — ключ: tier:token_or_ip
# Tier кладётся в request.state.user_tier через TierMiddleware (main.py).
# ═══════════════════════════════════════════════════════════

def _base_key(request: Request) -> str:
    """IP или первые 60 символов Bearer-токена."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return f"token:{auth[7:67]}"
    return f"ip:{get_remote_address(request)}"


def chart_rate_key(request: Request) -> str:
    """Ключ для /chart/calculate — включает tier, счётчики независимы."""
    tier = getattr(request.state, "user_tier", "free")
    return f"chart:{tier}:{_base_key(request)}"


def interpret_rate_key(request: Request) -> str:
    """Ключ для /interpret — включает tier."""
    tier = getattr(request.state, "user_tier", "free")
    return f"interp:{tier}:{_base_key(request)}"


def chart_rate_limit(request: Request) -> str:
    """Возвращает строку лимита в зависимости от tier запроса."""
    tier = getattr(request.state, "user_tier", "free")
    return CHART_LIMIT_PRO if tier in ("pro", "premium") else CHART_LIMIT_FREE


def interpret_rate_limit(request: Request) -> str:
    """Возвращает строку лимита интерпретаций в зависимости от tier."""
    tier = getattr(request.state, "user_tier", "free")
    return INTERPRET_LIMIT_PRO if tier in ("pro", "premium") else INTERPRET_LIMIT_FREE


# Глобальный лимитер — подключается к app в main.py
limiter = Limiter(key_func=_base_key)


# ═══════════════════════════════════════════════════════════
# DAILY INTERPRETATION COUNTER (in-memory, сбрасывается при рестарте)
# ═══════════════════════════════════════════════════════════

@dataclass
class _DailyCounter:
    count: int = 0
    reset_at: float = 0.0


class TierRateLimiter:
    def __init__(self):
        self._interpretations: dict[str, _DailyCounter] = {}
        self._lock = threading.Lock()

    def _get_counter(self, user_id: str) -> _DailyCounter:
        now = time.time()
        with self._lock:
            counter = self._interpretations.get(user_id)
            if counter is None or now >= counter.reset_at:
                counter = _DailyCounter(count=0, reset_at=now + 86400)
                self._interpretations[user_id] = counter
            return counter

    def check_interpretation_limit(self, user: Optional[User]) -> None:
        """Raise 429 если free-пользователь превысил дневной лимит интерпретаций."""
        if user is None or user.tier in ("pro", "premium"):
            return

        limit = TIER_FLAGS["free"]["interpretations_per_day"]
        counter = self._get_counter(str(user.id))
        if counter.count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Free план: {limit} интерпретация в день. "
                    "Оформите Pro для безлимитного доступа."
                ),
            )
        with self._lock:
            counter.count += 1

    def check_transit_access(self, user: Optional[User]) -> None:
        """Raise 403 если free-пользователь пытается получить транзиты."""
        tier = user.tier if user else "free"
        if TIER_FLAGS.get(tier, TIER_FLAGS["free"])["transits_months"] == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Транзиты недоступны на Free плане. Оформите Pro.",
            )


# Глобальный экземпляр
tier_limiter = TierRateLimiter()
