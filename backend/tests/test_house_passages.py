"""tests/test_house_passages.py — регресс на баг с истёкшими периодами планера.

compute_planner_periods() должна:
  - для медленных планет (longterm) выбирать период, который реально
    содержит "сегодня" — а не самый длинный по продолжительности среди
    пересекающихся с месяцем (старая логика показывала уже завершившийся
    транзит, если новый дом короче предыдущего по времени пребывания);
  - для быстрых планет (месяц) не показывать в текущем/будущем месяце
    период, который уже полностью закончился к сегодняшнему дню; но не
    трогать эту логику при просмотре ПРОШЛОГО месяца (Pro-навигация назад).

Запуск: pytest backend/tests/test_house_passages.py -v
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

from backend.transit.house_passages import compute_planner_periods

_NATAL = {
    "houses": [{"number": i + 1, "sign": "Овен", "degree": i * 30} for i in range(12)],
}

_FALLBACK_PASSAGE = [{"house": 1, "start_dt": datetime(2020, 1, 1), "end_dt": datetime(2030, 1, 1)}]


def _passages_for(overrides: dict):
    def _fake(planet_name, cusps, from_dt, to_dt, step_hours=None):
        return overrides.get(planet_name, _FALLBACK_PASSAGE)
    return _fake


def test_slow_planet_picks_period_containing_today_not_longest():
    """Юпитер: старый дом длинный (~411 дней, уже закончился), новый — короткий
    (28 дней), но именно в нём находится "сегодня". Должен выбраться новый."""
    overrides = {
        "Jupiter": [
            {"house": 4, "start_dt": datetime(2025, 5, 17), "end_dt": datetime(2026, 7, 2)},
            {"house": 5, "start_dt": datetime(2026, 7, 2), "end_dt": datetime(2026, 7, 30)},
        ],
    }
    with patch("backend.transit.house_passages.calculate_house_passages", side_effect=_passages_for(overrides)):
        periods = compute_planner_periods(
            natal_profile=_NATAL,
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            today=date(2026, 7, 24),
        )
    jupiter = next(p for p in periods["slow_planets"] if p["planet_key"] == "jupiter")
    assert jupiter["house"] == 5, "выбран истёкший дом вместо актуального"
    assert jupiter["period_label"] == "02.07.2026 — 30.07.2026"


def test_fast_planet_hides_fully_expired_period_in_current_month():
    """Солнце: период 08.06—12.07 уже полностью в прошлом относительно today=24.07 —
    в текущем месяце показываться не должен, остаётся только актуальный 12.07—14.08."""
    overrides = {
        "Sun": [
            {"house": 3, "start_dt": datetime(2026, 6, 8), "end_dt": datetime(2026, 7, 12)},
            {"house": 4, "start_dt": datetime(2026, 7, 12), "end_dt": datetime(2026, 8, 14)},
        ],
    }
    with patch("backend.transit.house_passages.calculate_house_passages", side_effect=_passages_for(overrides)):
        periods = compute_planner_periods(
            natal_profile=_NATAL,
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            today=date(2026, 7, 24),
        )
    sun = next(p for p in periods["fast_planets"] if p["planet_key"] == "sun")
    houses = [pp["house"] for pp in sun["periods"]]
    assert houses == [4], f"истёкший период должен быть скрыт в текущем месяце, получили {houses}"


def test_fast_planet_keeps_expired_period_when_browsing_past_month():
    """Та же пара периодов, но при просмотре ПРОШЛОГО месяца (июнь) — истёкший
    период не должен прятаться, это Pro-навигация назад по календарю."""
    overrides = {
        "Sun": [
            {"house": 3, "start_dt": datetime(2026, 6, 8), "end_dt": datetime(2026, 7, 12)},
            {"house": 4, "start_dt": datetime(2026, 7, 12), "end_dt": datetime(2026, 8, 14)},
        ],
    }
    with patch("backend.transit.house_passages.calculate_house_passages", side_effect=_passages_for(overrides)):
        periods = compute_planner_periods(
            natal_profile=_NATAL,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            today=date(2026, 7, 24),
        )
    sun = next(p for p in periods["fast_planets"] if p["planet_key"] == "sun")
    houses = [pp["house"] for pp in sun["periods"]]
    assert houses == [3], f"просмотр прошлого месяца не должен фильтроваться по today, получили {houses}"
