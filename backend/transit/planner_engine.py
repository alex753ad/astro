"""backend/transit/planner_engine.py

Планер без ИИ — все интерпретации берутся из словарей.
Принимает precomputed_periods из house_passages.compute_planner_periods()
и возвращает готовую структуру для фронтенда.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from backend.transit.forecast_prompt import MOON_HOUSE_ACTIONS, PLANET_HOUSE_MEANINGS
from backend.transit.house_passages import (
    compute_planner_periods,
    PLANET_SUBTITLES,
    PLANET_NAMES_RU,
)

# Сколько пунктов показывать для каждой сферы
ITEMS_PER_HOUSE = 3

# Маппинг строки действий → список пунктов (разбиваем по запятой)
def _split_actions(text: str, limit: int = ITEMS_PER_HOUSE) -> list[str]:
    items = [s.strip().capitalize() for s in text.split(",") if s.strip()]
    return items[:limit]


def _moon_items(house: int) -> list[str]:
    text = MOON_HOUSE_ACTIONS.get(int(house), "")
    return _split_actions(text)


def _planet_items(planet_key: str, house: int) -> list[str]:
    # planet_key здесь английское название (Sun, Mercury, ...)
    text = PLANET_HOUSE_MEANINGS.get(planet_key, {}).get(int(house), "")
    return _split_actions(text)


# Маппинг planet_key (lowercase) → английское название для словарей
_KEY_TO_ENG = {
    "sun":     "Sun",
    "mercury": "Mercury",
    "venus":   "Venus",
    "mars":    "Mars",
    "jupiter": "Jupiter",
    "saturn":  "Saturn",
    "uranus":  "Uranus",
    "neptune": "Neptune",
    "pluto":   "Pluto",
}

# Маппинг английского → ключ для PLANET_SUBTITLES
_ENG_TO_PLANET_KEY = {v: k for k, v in {
    "Sun":     "Sun",
    "Mercury": "Mercury",
    "Venus":   "Venus",
    "Mars":    "Mars",
    "Jupiter": "Jupiter",
    "Saturn":  "Saturn",
    "Uranus":  "Uranus",
    "Neptune": "Neptune",
    "Pluto":   "Pluto",
}.items()}


def build_planner(
    natal_profile: dict,
    from_date: date,
    to_date: date,
    today: Optional[date] = None,
    user_timezone: Optional[str] = None,
) -> dict:
    """Собрать планер полностью в Python без ИИ.

    Возвращает структуру совместимую с PlannerPage.jsx:
    {
      month_title, month_sections, week_title, week_days,
      longterm_title, longterm
    }
    """
    if today is None:
        today = date.today()

    periods = compute_planner_periods(
        natal_profile=natal_profile,
        from_date=from_date,
        to_date=to_date,
        today=today,
        user_timezone=user_timezone,
    )

    month_title = f"Планер на {_month_name(from_date)}"

    # ── month_sections: быстрые планеты ──────────────────────────────────────
    month_sections = []
    for p in periods.get("fast_planets", []):
        eng = _KEY_TO_ENG.get(p["planet_key"], "")
        sections_periods = []
        for period in p.get("periods", []):
            house = period.get("house")
            if not house:
                continue
            items = _planet_items(eng, house)
            sections_periods.append({
                "period": period["period"],
                "house":  house,
                "items":  items,
            })
        month_sections.append({
            "planet":          p["planet_key"],
            "planet_name":     p["planet_name"],
            "emoji":           p["emoji"],
            "planet_subtitle": p.get("planet_subtitle", ""),
            "periods":         sections_periods,
        })

    # ── week_days: луна ───────────────────────────────────────────────────────
    week_days = []
    for day in periods.get("moon_week", []):
        house = day.get("house", 0)
        week_days.append({
            "date":  day["date"],
            "time":  day.get("time", ""),
            "house": house,
            "items": _moon_items(house) if house else [],
        })

    # ── longterm: медленные планеты ───────────────────────────────────────────
    longterm = []
    for p in periods.get("slow_planets", []):
        eng = _KEY_TO_ENG.get(p["planet_key"], "")
        house = p.get("house", 0)
        items = _planet_items(eng, house)
        longterm.append({
            "planet":          p["planet_key"],
            "planet_name":     p["planet_name"],
            "emoji":           p["emoji"],
            "planet_subtitle": p.get("planet_subtitle", ""),
            "house":           house,
            "period":          p.get("period_label", ""),
            "items":           items,
        })

    return {
        "month_title":    month_title,
        "month_sections": month_sections,
        "week_title":     "Транзитная Луна по домам",
        "week_days":      week_days,
        "longterm_title": "Долгосрочные транзиты",
        "longterm":       longterm,
    }


_MONTHS_RU = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

def _month_name(d: date) -> str:
    return f"{_MONTHS_RU[d.month]} {d.year}"
