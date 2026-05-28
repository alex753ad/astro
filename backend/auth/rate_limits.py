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
        "interpretations_per_month": 0,        # только превью (блюр)
        "charts_per_month": None,              # 1/день — отдельный лимит
        "charts_per_day": 1,
        "transits_months": 0,
        "transits_ai": False,
        "profiles_limit": 1,
        "lunar_months": 1,                     # текущий месяц
        "planner_months": 0,
        "synastry": False,
        "pdf_export": False,
        "ai_engine": "template",
    },
    "lite": {
        "interpretation_word_limit": 800,
        "interpretations_per_month": 3,
        "charts_per_month": 5,
        "charts_per_day": None,
        "transits_months": 12,
        "transits_ai": False,                  # просмотр без AI
        "profiles_limit": 5,
        "lunar_months": 12,                    # на год
        "planner_months": 1,                   # только текущий месяц
        "synastry": False,
        "pdf_export": False,
        "ai_engine": "deepseek",
    },
    "pro": {
        "interpretation_word_limit": 2500,
        "interpretations_per_month": 15,
        "charts_per_month": 20,
        "charts_per_day": None,
        "transits_months": 6,
        "transits_ai": True,
        "profiles_limit": 20,
        "lunar_months": 12,
        "planner_months": 12,
        "synastry": False,
        "pdf_export": True,
        "pdf_per_month": 5,
        "ai_engine": "gpt4o",
    },
    "premium": {
        "interpretation_word_limit": 5000,
        "interpretations_per_month": 100,
        "charts_per_month": None,
        "charts_per_day": None,
        "transits_months": 12,
        "transits_ai": True,
        "profiles_limit": None,
        "lunar_months": 12,
        "planner_months": 12,
        "synastry": True,
        "pdf_export": True,
        "pdf_per_month": 50,
        "ai_engine": "gpt4o_exclusive",
    },
}


def get_feature_flags(user: Optional[User]) -> dict:
    tier = user.tier if user else "free"
    flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
    return {
        "tier": tier,
        **flags,
        "transits": flags["transits_months"] > 0,
        "transits_ai": flags["transits_ai"],
        # pro и premium считаются "безлимитными" относительно free/lite
        "unlimited_interpretations": tier in ("pro", "premium"),
        "unlimited_charts": flags["charts_per_month"] is None and flags.get("charts_per_day") is None,
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

def chart_premium_key(request: Request) -> str:
    return f"chart:premium:{_base_id(request)}"


# /interpret — два ключа, два декоратора в main.py
def interpret_free_key(request: Request) -> str:
    return f"interp:free:{_base_id(request)}"

def interpret_pro_key(request: Request) -> str:
    return f"interp:pro:{_base_id(request)}"

def interpret_premium_key(request: Request) -> str:
    return f"interp:premium:{_base_id(request)}"


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
        if user is None:
            # анонимы — только превью, блокируем на уровне эндпоинта
            return
        tier = user.tier
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        limit = flags["interpretations_per_month"]
        if limit is None:
            return
        if limit == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI-интерпретации недоступны на Free плане. Оформите Lite.",
            )
        counter = self._get_counter(str(user.id))
        if counter.count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Лимит {limit} интерпретаций в месяц исчерпан для тарифа {tier.capitalize()}. "
                    "Оформите более высокий тариф."
                ),
            )
        with self._lock:
            counter.count += 1

    def check_transit_access(self, user: Optional[User]) -> None:
        tier = user.tier if user else "free"
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        if flags["transits_months"] == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Транзиты недоступны на Free плане. Оформите Lite.",
            )

    def check_transit_ai_access(self, user: Optional[User]) -> None:
        tier = user.tier if user else "free"
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        if not flags["transits_ai"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI-расшифровка транзитов доступна только на Pro и выше.",
            )

    def check_premium_ip(self, user: Optional[User], request: Request) -> None:
        """Для Premium: сброс сессии при 3+ уникальных IP за 30 минут."""
        if user is None or user.tier != "premium":
            return
        from backend.cache import ip_monitor
        from slowapi.util import get_remote_address
        ip = get_remote_address(request)
        if ip_monitor.record_and_check(str(user.id), ip):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Обнаружен вход с нескольких устройств. Пожалуйста, войдите заново.",
                headers={"WWW-Authenticate": "Bearer"},
            )


tier_limiter = TierRateLimiter()

# Алиасы для совместимости с задачей 2
TIER_LIMITS = TIER_FLAGS

def get_tier_limits(tier: str) -> dict:
    return TIER_FLAGS.get(tier, TIER_FLAGS["free"])
