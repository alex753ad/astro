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


def _parse_frontend_prices() -> dict[str, int]:
    """Вытащить TIER_PRICES из constants.js.

    Разбор регуляркой, а не исполнением JS: тянуть node в бэкенд-тесты ради
    одного объекта не стоит. Если формат объявления изменится, тест упадёт
    на разборе — это лучше, чем молча пропустить сверку.
    """
    src = CONSTANTS_JS.read_text(encoding="utf-8")
    match = re.search(r"export\s+const\s+TIER_PRICES\s*=\s*\{(.*?)\}", src, re.S)
    assert match, f"TIER_PRICES не найден в {CONSTANTS_JS} — изменился формат объявления?"

    body = match.group(1)
    # Убираем комментарии и висячие запятые, чтобы получился валидный JSON.
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r",\s*$", "", body.strip())
    pairs = re.sub(r"(\w+)\s*:", r'"\1":', body)
    return json.loads("{" + pairs + "}")


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
