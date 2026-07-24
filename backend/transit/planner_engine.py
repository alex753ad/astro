"""backend/transit/planner_engine.py

Планер без ИИ — все интерпретации берутся из словарей.
Принимает precomputed_periods из house_passages.compute_planner_periods()
и возвращает готовую структуру для фронтенда.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from backend.transit.house_passages import (
    compute_planner_periods,
    PLANET_NAMES_RU,
)

# Методичка «планета × дом» — единственный источник текстов планера.
# Грузится один раз при импорте модуля (модульный кэш), диск больше не трогаем.
_METHODOLOGY_PATH = Path(__file__).parent / "methodology.json"
with open(_METHODOLOGY_PATH, encoding="utf-8") as _f:
    METHODOLOGY: dict = json.load(_f)


def _house_entry(planet_eng: str, house: int) -> dict:
    return METHODOLOGY.get(planet_eng, {}).get("houses", {}).get(str(int(house)), {})


def _planet_lead(planet_eng: str) -> str:
    return METHODOLOGY.get(planet_eng, {}).get("meta", {}).get("lead", "")


def _locked_payload() -> dict:
    """Заблокированный период — на клиент не уходит ни одной строки методички."""
    return {"theme": "", "groups": []}


def _unlocked_payload(planet_eng: str, house: int) -> dict:
    """Полный набор текстов дома дословно из methodology.json.

    theme/groups — всегда. subtitle/notes — только если есть в файле
    (Уран/Нептун/Плутон), для остальных планет ключи не добавляются.
    """
    entry = _house_entry(planet_eng, house)
    payload = {
        "theme": entry.get("theme", ""),
        "groups": [
            {"heading": g.get("heading", ""), "items": list(g.get("items", []))}
            for g in entry.get("groups", [])
        ],
    }
    if "subtitle" in entry:
        payload["subtitle"] = entry["subtitle"]
    if "notes" in entry:
        payload["notes"] = list(entry["notes"])
    return payload


# Маппинг planet_key (lowercase) → английское название (ключи methodology.json)
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


def build_planner(
    natal_profile: dict,
    from_date: date,
    to_date: date,
    today: Optional[date] = None,
    user_timezone: Optional[str] = None,
    tier: Optional[str] = None,
) -> dict:
    """Собрать планер полностью в Python без ИИ.

    Возвращает структуру совместимую с PlannerPage.jsx:
    {
      month_title, month_sections, week_title, week_days,
      longterm_title, longterm
    }

    E1 (Free-витрина): при tier="free" полный разбор (items) остаётся только
    у текущего периода Солнца. Все прочие периоды/планеты и Луна возвращаются
    с items=[] и locked=true (текст на клиент не уходит).

    Тарифная сетка по разделам:
      Месяц/Неделя — открыты с Lite и выше (locked только на Free).
      Долгосрочно  — открыт только с Pro и выше (locked на Free и Lite).
    """
    if today is None:
        today = date.today()

    free = (tier == "free")
    is_pro = tier in ("pro", "premium")

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
        is_sun = p["planet_key"] == "sun"
        sections_periods = []
        for period in p.get("periods", []):
            house = period.get("house")
            if not house:
                continue
            # E1: у Free разблокирован только текущий период Солнца
            locked = free and not (is_sun and period.get("is_current", False))
            sections_periods.append({
                "period": period["period"],
                "house":  house,
                "locked": locked,
                **(_locked_payload() if locked else _unlocked_payload(eng, house)),
            })
        month_sections.append({
            "planet":          p["planet_key"],
            "planet_name":     p["planet_name"],
            "emoji":           p["emoji"],
            "planet_subtitle": _planet_lead(eng),
            "periods":         sections_periods,
        })

    # ── week_days: луна ───────────────────────────────────────────────────────
    # moon_week теперь содержит периоды нахождения Луны в доме (не дни недели).
    # date  = "21.05 Чт 03:22"  (момент входа в дом)
    # time  = "до 25.05 Пн 01:03"  (момент выхода из дома)
    # house = номер дома
    week_days = []
    for passage in periods.get("moon_week", []):
        house = passage.get("house", 0)
        week_days.append({
            "date":  passage["date"],
            "time":  passage.get("time", ""),
            "house": house,
            "locked": free,
            **(_locked_payload() if (free or not house) else _unlocked_payload("Moon", house)),
        })

    # ── longterm: медленные планеты — открыто только с Pro (сетка тарифов) ────
    longterm = []
    for p in periods.get("slow_planets", []):
        eng = _KEY_TO_ENG.get(p["planet_key"], "")
        house = p.get("house", 0)
        locked = not is_pro
        longterm.append({
            "planet":          p["planet_key"],
            "planet_name":     p["planet_name"],
            "emoji":           p["emoji"],
            "planet_subtitle": _planet_lead(eng),
            "house":           house,
            "period":          p.get("period_label", ""),
            "locked":          locked,
            **(_locked_payload() if locked else _unlocked_payload(eng, house)),
        })

    return {
        "month_title":    month_title,
        "month_sections": month_sections,
        "week_title":     "Транзитная Луна по домам",
        "week_days":      week_days,
        "longterm_title": "Долгосрочные транзиты",
        "longterm":       longterm,
        "retrogrades":    periods.get("retrogrades", []),
    }


_MONTHS_RU = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

def _month_name(d: date) -> str:
    return f"{_MONTHS_RU[d.month]} {d.year}"
