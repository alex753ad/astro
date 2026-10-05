"""Касание к ASC/MC в блоке транзитов чата — с фактами (05.10.2026).

До правки build_transits_block отбирал события по day_event.points (с углами),
а факты считал по карте чата, где углов в planets нет: строка «Натальная
планета: MC» шла без знака и градуса, без «Точный аспект» и периода. Тот же
баг, что у разбора транзита (#121, test_transit_angles_facts.py).
"""
from datetime import date, datetime

from backend.ephemeris.calculator import calculate_full_chart
from backend.interpretation.rag import build_transits_block, chat_chart_data

# Вымышленная карта test_exact_touch.py (08.03.1991 03:40, Москва):
# MC — Стрелец 18.94°, Сатурн трин MC — касание 17.04.2027 19:43 UTC.
_FULL, _ = calculate_full_chart(datetime(1991, 3, 8, 3, 40), 55.75, 37.62, house_system="placidus")
MC = {"sign": "Sagittarius", "degree": 18.9395, "longitude": 258.9395}


def _block(time_unknown: bool) -> str:
    chart = chat_chart_data({
        "planets": [{"name": p.name, "longitude": p.longitude, "sign": p.sign,
                     "degree_in_sign": p.longitude % 30} for p in _FULL.planets],
        "midheaven": MC,
    }, time_unknown)
    # Все события дня, а не топ-5: проверяется MC, а не отбор.
    return build_transits_block(chart, 100, date(2027, 4, 17), f"test-chat-mc-{time_unknown}", "UTC")


def test_saturn_trine_mc_has_facts():
    facts = next(b for b in _block(False).split("\n\n")
                 if "Транзитная планета: Сатурн" in b and "Натальная планета: MC" in b)
    assert "18°56' в знаке Стрелец" in facts, facts
    assert "Аспект: трин" in facts, facts
    assert "Точный аспект: 17 апреля 2027" in facts, facts
    assert "Период влияния: 6 апреля 2027 — 29 апреля 2027" in facts, facts


def test_no_birth_time_no_mc():
    assert "MC" not in _block(True)
