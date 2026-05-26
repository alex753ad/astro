"""Per-tier rate limiting helpers.

Tracks daily usage of interpretations per user.
Uses in-memory counters that reset on server restart (acceptable for MVP).

Tier limits (Phase 1):
  Free:    charts unlimited, 1 interpretation/day (~500 words), no transits
  Pro:     unlimited interpretations (2000 words), transits up to 6 months, 10 profiles
  Premium: unlimited interpretations (5000 words), transits up to 12 months, synastry, PDF
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status

from backend.config import get_settings
from backend.models import User

settings = get_settings()


# Feature flags returned to the frontend via /api/v1/profile/subscription
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
        "pdf_export": True,
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
    """Return feature flags for the given user's tier."""
    tier = user.tier if user else "free"
    flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
    return {
        "tier": tier,
        **flags,
        "transits": flags["transits_months"] > 0,
        "pdf_reports": flags["pdf_export"],
    }


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
        """Raise 429 if free-tier user exceeded daily interpretation limit."""
        if user is None or user.tier in ("pro", "premium"):
            return

        limit = TIER_FLAGS["free"]["interpretations_per_day"]
        counter = self._get_counter(str(user.id))
        if counter.count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Free plan allows {limit} interpretation per day. Upgrade to Pro for unlimited access.",
            )
        with self._lock:
            counter.count += 1

    def check_transit_access(self, user: Optional[User]) -> None:
        """Raise 403 if free-tier user tries to access transits."""
        tier = user.tier if user else "free"
        if TIER_FLAGS.get(tier, TIER_FLAGS["free"])["transits_months"] == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Transits are not available on the Free plan. Upgrade to Pro.",
            )


# Global instance
tier_limiter = TierRateLimiter()
