"""Per-tier rate limiting helpers.

Tracks daily usage of charts and interpretations per user.
Uses in-memory counters that reset on server restart (acceptable for MVP).
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException, status

from backend.config import get_settings
from backend.models import User

settings = get_settings()


@dataclass
class _DailyCounter:
    count: int = 0
    reset_at: float = 0.0


class TierRateLimiter:
    """Track daily usage per user for charts and interpretations.

    Free tier:  5 charts/day, 2 interpretations/day
    Pro / Premium: unlimited
    """

    def __init__(self):
        self._charts: dict[str, _DailyCounter] = {}
        self._interpretations: dict[str, _DailyCounter] = {}
        self._lock = threading.Lock()

    def _get_counter(
        self, store: dict[str, _DailyCounter], user_id: str
    ) -> _DailyCounter:
        now = time.time()
        with self._lock:
            counter = store.get(user_id)
            if counter is None or now >= counter.reset_at:
                # Start of new day window (midnight UTC-aligned would be better,
                # but 24-hour rolling window is simpler and good enough for MVP)
                counter = _DailyCounter(count=0, reset_at=now + 86400)
                store[user_id] = counter
            return counter

    def check_chart_limit(self, user: Optional[User]) -> None:
        """Raise 429 if free-tier user exceeded daily chart limit."""
        if user is None:
            # Anonymous users are handled by slowapi global rate limiter
            return
        if user.tier in ("pro", "premium"):
            return

        counter = self._get_counter(self._charts, user.id)
        if counter.count >= settings.rate_limit_free_charts_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Free plan allows {settings.rate_limit_free_charts_per_day} "
                    f"charts per day. Upgrade to Pro for unlimited access."
                ),
            )
        with self._lock:
            counter.count += 1

    def check_interpretation_limit(self, user: Optional[User]) -> None:
        """Raise 429 if free-tier user exceeded daily interpretation limit."""
        if user is None:
            return
        if user.tier in ("pro", "premium"):
            return

        counter = self._get_counter(self._interpretations, user.id)
        if counter.count >= settings.rate_limit_free_interpretations_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Free plan allows {settings.rate_limit_free_interpretations_per_day} "
                    f"interpretations per day. Upgrade to Pro for unlimited access."
                ),
            )
        with self._lock:
            counter.count += 1


# Global instance
tier_limiter = TierRateLimiter()
