"""Цены на витрине и цены, по которым считается платёж, обязаны совпадать.

Витрина — frontend/src/constants.js (TIER_PRICES), она рисует /pricing и
кнопки апгрейда. Деньги — backend/payments/common.py (TIER_PRICES_RUB): по
нему checkout создаёт платёж в ЮKassa и по нему же вебхук сверяет реально
списанную сумму.

Два независимых числа, обязанных совпадать, рано или поздно расходятся —
в этом проекте так уже случилось дважды (charts_per_month и pdf_per_month,
см. CLAUDE.md). Здесь цена расхождения выше обычного: витрина обещала бы одну
сумму, а списывалась другая, и это не тихая рассинхронизация лимитов, а
претензия от покупателя.

Свести в один источник нельзя — питон и JS собираются раздельно, бэкенд не
отдаёт цены наружу. Поэтому тест: он не мешает менять цену, но требует
менять её в обоих местах одним коммитом.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.payments.common import TIER_PRICES_RUB

CONSTANTS_JS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants.js"


def _parse_frontend_schedule() -> list[tuple[str, dict[str, int]]]:
    """TIER_PRICE_SCHEDULE из constants.js → [(from, prices)].

    Разбор регуляркой, а не исполнением JS: тянуть node в бэкенд-тесты ради
    одного массива не стоит. Если формат объявления изменится, тест упадёт
    на разборе — это лучше, чем молча пропустить сверку.
    """
    src = CONSTANTS_JS.read_text(encoding="utf-8")
    match = re.search(r"export\s+const\s+TIER_PRICE_SCHEDULE\s*=\s*\[(.*?)\];", src, re.S)
    assert match, f"TIER_PRICE_SCHEDULE не найден в {CONSTANTS_JS} — изменился формат объявления?"
    body = re.sub(r"//[^\n]*", "", match.group(1))
    body = body.replace("'", '"')
    body = re.sub(r"(\w+)\s*:", r'"\1":', body)
    body = re.sub(r",\s*([}\]])", r"\1", body.strip().rstrip(","))
    rows = json.loads("[" + body + "]")
    return [(r["from"], r["prices"]) for r in rows]


def _parse_frontend_prices() -> dict[str, int]:
    """Цены витрины на сегодня — строка расписания, действующая сегодня."""
    from backend.payments.common import _msk_date
    today = _msk_date(None).isoformat()
    current: dict[str, int] = {}
    for day, prices in _parse_frontend_schedule():
        if day <= today:
            current = prices
    return current


class TestScheduleSync:
    """Смена цены объявляется строкой расписания в ОБОИХ местах — иначе в
    день вступления витрина покажет одну цену, а чекаут спишет другую."""

    def test_schedules_match(self):
        from backend.payments.common import PRICE_SCHEDULE
        front = _parse_frontend_schedule()
        back = [(d.isoformat(), prices) for d, prices in PRICE_SCHEDULE]
        assert [f for f, _ in front] == [b for b, _ in back], "даты смены цен разошлись"
        for (day, fp), (_, bp) in zip(front, back):
            for tier, price in bp.items():
                assert fp.get(tier) == price, f"{day}: {tier} витрина {fp.get(tier)}, платёж {price}"


class TestPriceSync:

    def test_constants_js_is_parseable(self):
        prices = _parse_frontend_prices()
        assert prices, "не удалось разобрать TIER_PRICES"
        assert prices.get("free") == 0, "free должен стоить 0"

    @pytest.mark.parametrize("tier", sorted(TIER_PRICES_RUB))
    def test_backend_price_matches_frontend(self, tier):
        frontend = _parse_frontend_prices()
        assert tier in frontend, (
            f"тариф {tier} есть в backend TIER_PRICES_RUB, но нет в constants.js"
        )
        assert frontend[tier] == TIER_PRICES_RUB[tier], (
            f"цена {tier} разошлась: витрина {frontend[tier]} ₽, "
            f"платёж {TIER_PRICES_RUB[tier]} ₽"
        )

    def test_no_paid_tier_only_on_the_shop_window(self):
        """Обратная сторона: платный тариф на витрине, которого нет в
        источнике цены платежа, — это кнопка, ведущая в 400."""
        frontend = _parse_frontend_prices()
        extra = {
            tier for tier, price in frontend.items()
            if price and tier not in TIER_PRICES_RUB
        }
        assert not extra, f"на витрине есть платные тарифы без цены на бэкенде: {extra}"
