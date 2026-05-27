"""Per-tier rate limiting helpers.

SlowAPI-лимиты реализованы через ДВА декоратора на каждый эндпоинт:
  @limiter.limit("10/minute", key_func=chart_free_key)   # считает только free-запросы
  @limiter.limit("60/minute", key_func=chart_pro_key)    # считает только pro/premium

Ключи строятся так:
  free:    "chart:free:token:<...>" или "chart:free:ip:<...>"
  pro:     "chart:pro:token:<...>"  или "chart:pro:ip:<...>"

Поскольку ключи разные — счётчики независимы.
Free-пользователь попадает под лимит 10/min (ключ chart:free:...).
Pro-пользователь попадает под лимит 60/min (ключ chart:pro:...).
TierMiddleware кладёт tier в request.state.user_tier до декораторов.
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
        "interpretations_per_day": None,
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
# SLOWAPI — базовый ключ и tier-specific ключи
# ═══════════════════════════════════════════════════════════

def _base_id(request: Request) -> str:
    """Возвращает токен (первые 60 символов) или IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return f"token:{auth[7:67]}"
    return f"ip:{get_remote_address(request)}"


# /chart/calculate — два ключа, два декоратора в main.py
def chart_free_key(request: Request) -> str:
    return f"chart:free:{_base_id(request)}"

def chart_pro_key(request: Request) -> str:
    return f"chart:pro:{_base_id(request)}"


# /interpret — два ключа, два декоратора в main.py
def interpret_free_key(request: Request) -> str:
    return f"interp:free:{_base_id(request)}"

def interpret_pro_key(request: Request) -> str:
    return f"interp:pro:{_base_id(request)}"


# Глобальный лимитер
limiter = Limiter(key_func=_base_id)


# ═══════════════════════════════════════════════════════════
# DAILY INTERPRETATION COUNTER
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
        tier = user.tier if user else "free"
        if TIER_FLAGS.get(tier, TIER_FLAGS["free"])["transits_months"] == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Транзиты недоступны на Free плане. Оформите Pro.",
            )


tier_limiter = TierRateLimiter()
