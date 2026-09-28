"""Ставка DeepSeek в суточном бюджете — цена V4 Pro и удвоение в часы пик.

До 28.09.2026 стояло $0.30 за миллион — в 4–9 раз ниже реальной цены, и
бюджет считал расход заниженным.
"""
from datetime import datetime, timezone

from backend.interpretation.router import _deepseek_cost_per_1k


def _at(weekday_date: str, hour: int) -> datetime:
    return datetime.fromisoformat(f"{weekday_date}T{hour:02d}:30:00").replace(tzinfo=timezone.utc)


def test_offpeak_is_average_of_pro_in_and_out():
    # понедельник 28.09.2026, 12:00 UTC — не пик
    assert _deepseek_cost_per_1k(_at("2026-09-28", 12)) == (0.66 + 1.98) / 2 / 1000


def test_peak_hours_double():
    base = _deepseek_cost_per_1k(_at("2026-09-28", 12))
    for hour in (1, 3, 6, 9):
        assert _deepseek_cost_per_1k(_at("2026-09-28", hour)) == 2 * base
    for hour in (0, 4, 5, 10, 23):
        assert _deepseek_cost_per_1k(_at("2026-09-28", hour)) == base


def test_weekend_is_never_peak():
    # суббота 03.10.2026, 07:00 UTC
    assert _deepseek_cost_per_1k(_at("2026-10-03", 7)) == _deepseek_cost_per_1k(_at("2026-09-28", 12))
