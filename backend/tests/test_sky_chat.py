"""Блок транзитов чата из ядра (задание 4.6, флаг sky_event). Карта
вымышленная, как в test_sky.py; у каждого теста свой id карты (чанки sky:v1
кэшируются по id)."""
from datetime import date

from backend.interpretation.rag import build_transits_block
from backend.tests.test_sky import CHART

TZ = "Europe/Moscow"


def _block(cid, day, sky=True):
    return build_transits_block(CHART, 10, day, cid, TZ, sky)


def _facts(block, transit_ru, natal_ru):
    """Факты одного транзита из блока — от его «Транзитная планета» до пустой строки."""
    for part in block.split("\n\n"):
        if f"Транзитная планета: {transit_ru}" in part and f"Натальная планета: {natal_ru}" in part:
            return part
    raise AssertionError(f"{transit_ru} → {natal_ru} нет в блоке:\n{block}")


def test_when_does_it_end_is_core_end():
    """«Когда кончится Юпитер оппозиция ASC?» 15.12.2026 — конец события
    ядра 18.07.2027, а не конец текущего прохода (24.01.2027 по Москве), как давал
    compute_exact_facts."""
    f = _facts(_block("test-sky-chat-end", date(2026, 12, 15)), "Юпитер", "Асцендент")
    assert "Период влияния: 1 ноября 2026 — 18 июля 2027" in f
    assert "орб" not in f


def test_loop_all_touches_and_gap():
    f = _facts(_block("test-sky-chat-loop", date(2026, 12, 15)), "Юпитер", "Асцендент")
    assert "Точные касания: 22 ноября 2026, 2 января и 7 июля 2027" in f
    assert "с перерывом с 24 января по 26 июня" in f


def test_several_gaps():
    """Плутон соединение Сатурн: пять касаний, три перерыва — «с перерывами
    …, … и …» (решение владельца 06.10.2026)."""
    f = _facts(_block("test-sky-chat-gaps", date(2027, 1, 15)), "Плутон", "Сатурн")
    assert "с перерывами с " in f and f.count(" по ") == 3


def test_in_gap_not_active():
    """В перерыве петли (Нептун секстиль Сатурн, 15.12.2026) событие сегодня
    не активно — в блоке его нет."""
    block = _block("test-sky-chat-gapday", date(2026, 12, 15))
    assert not any("Транзитная планета: Нептун" in p and "Натальная планета: Сатурн" in p
                   for p in block.split("\n\n"))
