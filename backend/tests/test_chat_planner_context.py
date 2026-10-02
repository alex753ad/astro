"""Чат видит планер (флаг chat_planner_context): замки тарифа и промпт без флага.

Главное, что здесь держится: закрытый в планере период не уходит модели ни
одной строкой методички — иначе чат перескажет человеку то, что планер ему
не показывает.
"""

from datetime import date

import pytest

from backend.flags import FLAGS
from backend.interpretation.address import ADDRESS_RULE
from backend.interpretation.rag import build_planner_block
from backend.interpretation.rag_router import _system_prompt
from backend.transit.planner_engine import build_planner

_NATAL = {
    "planets": [],
    "houses": [{"number": i + 1, "sign": "Овен", "degree": i * 30} for i in range(12)],
    "ascendant": {"sign": "Овен", "degree": 0},
    "midheaven": {"sign": "Козерог", "degree": 270},
}
_TODAY = date(2026, 7, 24)
_TZ = "Europe/Moscow"


def _block(tier):
    return build_planner_block(_NATAL, tier, _TZ, _TODAY)


def _full_planner():
    return build_planner(
        natal_profile=_NATAL, from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
        today=_TODAY, user_timezone=_TZ, tier="premium",
    )


def _items(entry):
    return [i for g in entry.get("groups", []) for i in g.get("items", [])]


@pytest.mark.parametrize("tier", ["free", "lite"])
def test_locked_texts_never_reach_the_prompt(tier):
    gated = build_planner(
        natal_profile=_NATAL, from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
        today=_TODAY, user_timezone=_TZ, tier=tier,
    )
    full = _full_planner()
    block = _block(tier)
    leaked = []
    for g_sec, f_sec in zip(gated["month_sections"], full["month_sections"]):
        for g, f in zip(g_sec["periods"], f_sec["periods"]):
            if g["locked"]:
                leaked += [i for i in _items(f) if i in block]
    for g, f in zip(gated["longterm"], full["longterm"]):
        if g["locked"]:
            leaked += [i for i in _items(f) + f.get("notes", []) if i in block]
    assert not leaked


def test_free_names_where_period_opens():
    block = _block("free")
    assert "открыт на Веге" in block   # месяц: у free открыт только текущий период Солнца
    assert "открыт на Лире" in block   # долгосрочно: закрыто на free и Веге


def test_lite_month_open_longterm_locked():
    block = _block("lite")
    full = _full_planner()
    mars = next(s for s in full["month_sections"] if s["planet"] == "mars")
    assert all(i in block for p in mars["periods"] for i in _items(p))
    assert "открыт на Лире" in block
    assert "открыт на Веге" not in block


def test_premium_longterm_with_full_items():
    block = _block("premium")
    for lt in _full_planner()["longterm"]:
        assert all(i in block for i in _items(lt))
    assert "закрыт" not in block


def test_upcoming_listed():
    assert "### Ближайшие смены (30 дней)" in _block("free")


def test_prompt_without_planner_is_unchanged():
    old = _system_prompt("КАРТА", ["фрагмент"], "", "ТРАНЗИТЫ")
    assert old == _system_prompt("КАРТА", ["фрагмент"], "", "ТРАНЗИТЫ", "")
    assert "Если нужного транзита нет в списке выше — скажи" in old
    assert "Сверяйся с планером" not in old
    assert "ТРАНЗИТЫ\n## Знания из базы" in old


def test_prompt_with_planner_has_block_and_rules():
    text = _system_prompt("КАРТА", [], "", "ТРАНЗИТЫ", "## Планер человека\nБЛОК\n")
    assert "БЛОК" in text
    assert "## Сверяйся с планером" in text
    assert "нет ни в транзитах, ни в планере" in text
    assert "Если это уже было в разговоре, не повторяй." in text
    assert ADDRESS_RULE in text


def test_flag_registered():
    assert "chat_planner_context" in FLAGS
