"""Счётчики прогнозов за скользящие сутки: сколько из модели, сколько запасным
текстом и почему, сколько ответов отбраковано, сколько ошибок DeepSeek.

Зачем: запасной текст спасает человека от пустой карточки, но прячет поломку —
снаружи прогноз «работает». У конкурента прогноз на день был сломан больше года
именно так. Читает эти числа часовая проверка (`backend/selfcheck.py`).

Корзины ЧАСОВЫЕ, сумма — по последним 24. Суточная корзина по календарной дате
обнулялась бы в полночь, и открытый инцидент «много запасных» закрывался бы
сам собой в 03:00 МСК сообщением «починилось», хотя не чинилось ничего.

Запись никогда не поднимает исключение: сбой счётчика не должен ронять
прогноз, за которым он следит (тот же принцип, что у beat_watchdog.mark_success).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from backend.cache import interpretation_cache

logger = logging.getLogger("astro.forecast.stats")

_PREFIX = "astro:forecast:stats:"
_TTL_SEC = 48 * 3600
WINDOW_HOURS = 24

# Служебная карта самопроверки (backend/selfcheck.py) — в счётчики не пишется:
# это не спрос людей, и её ежедневный прогноз смещал бы долю запасных.
SELFCHECK_CHART_ID = "selfcheck"

# Причины запасного текста. Порядок важен только для сообщения владельцу.
FALLBACK_REASONS = ("no_key", "budget", "model_error", "rejected")


def _redis():
    return interpretation_cache._redis


def _bucket(at: datetime) -> str:
    return _PREFIX + at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def incr(field: str, *, now: datetime | None = None) -> None:
    r = _redis()
    if r is None:
        return
    try:
        key = _bucket(now or datetime.now(timezone.utc))
        pipe = r.pipeline()
        pipe.hincrby(key, field, 1)
        pipe.expire(key, _TTL_SEC)
        pipe.execute()
    except Exception as e:
        logger.warning("forecast stats: не удалось записать %s: %s", field, e)


def record_outcome(chart_id, contour: str, source: str, reason: str | None) -> None:
    """`contour` — today|lunation; `source` — model|fallback; `reason` — из FALLBACK_REASONS."""
    if str(chart_id) == SELFCHECK_CHART_ID:
        return
    incr(f"{contour}:model" if source == "model" else f"{contour}:fallback:{reason}")


def read_window(*, now: datetime | None = None, hours: int = WINDOW_HOURS) -> dict[str, int]:
    """Сумма по последним `hours` часовым корзинам. Redis недоступен — пусто."""
    r = _redis()
    if r is None:
        return {}
    now = now or datetime.now(timezone.utc)
    total: dict[str, int] = {}
    try:
        for h in range(hours):
            for k, v in (r.hgetall(_bucket(now - timedelta(hours=h))) or {}).items():
                total[k] = total.get(k, 0) + int(v)
    except Exception as e:
        logger.warning("forecast stats: не удалось прочитать: %s", e)
        return {}
    return total


def summarize(counts: dict[str, int]) -> dict:
    """Свести поля в числа, которые нужны проверке и сообщению."""
    model = sum(v for k, v in counts.items() if k.endswith(":model"))
    by_reason = {
        r: sum(v for k, v in counts.items() if k.endswith(f":fallback:{r}"))
        for r in FALLBACK_REASONS
    }
    fallback = sum(by_reason.values())
    return {
        "model": model,
        "fallback": fallback,
        "by_reason": by_reason,
        "rejected_answers": counts.get("rejected", 0),
        "deepseek_errors": counts.get("deepseek_error", 0),
        "total": model + fallback,
    }
