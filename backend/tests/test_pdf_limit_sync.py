"""Число PDF на витрине и число, которым реально отбивает гейт, обязаны совпадать.

Витрина — frontend/src/constants.js (TIER_PDF_PER_MONTH), она рисует пункт
«PDF-экспорт (N карт)» на /pricing и во вкладке «Подписка». Ограничение —
backend/auth/rate_limits.py (TIER_FLAGS[*]["pdf_per_month"]): по нему
check_pdf_limit реально отказывает в скачивании.

До 30.08.2026 эти числа были набраны прозой прямо в features
('PDF-экспорт (5 карт)') и с сеткой не связаны ничем. Два независимых числа,
обязанных совпадать, рано или поздно расходятся — в этом проекте так уже
случилось дважды, причём один из случаев это ровно pdf_per_month
(см. CLAUDE.md, раздел «Тарифы»).

Устроено как test_price_sync.py: свести в один источник нельзя, питон и JS
собираются раздельно, поэтому тест не мешает менять сетку, но требует менять
её в обоих местах одним коммитом.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.auth.rate_limits import TIER_FLAGS

CONSTANTS_JS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants.js"


def _parse_frontend_pdf_limits() -> dict[str, int | None]:
    """Вытащить TIER_PDF_PER_MONTH из constants.js.

    Разбор регуляркой, а не исполнением JS, — по той же причине, что в
    test_price_sync.py: тянуть node в бэкенд-тесты ради одного объекта не
    стоит. Изменится формат объявления — тест упадёт на разборе, и это лучше,
    чем молча пропустить сверку.
    """
    src = CONSTANTS_JS.read_text(encoding="utf-8")
    match = re.search(
        r"export\s+const\s+TIER_PDF_PER_MONTH\s*=\s*\{(.*?)\}", src, re.S
    )
    assert match, (
        f"TIER_PDF_PER_MONTH не найден в {CONSTANTS_JS} — изменился формат объявления?"
    )

    body = match.group(1)
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r",\s*$", "", body.strip())
    pairs = re.sub(r"(\w+)\s*:", r'"\1":', body)
    return json.loads("{" + pairs + "}")


class TestPdfLimitSync:

    def test_constants_js_is_parseable(self):
        limits = _parse_frontend_pdf_limits()
        assert limits, "не удалось разобрать TIER_PDF_PER_MONTH"

    @pytest.mark.parametrize("tier", sorted(TIER_FLAGS))
    def test_backend_limit_matches_frontend(self, tier):
        frontend = _parse_frontend_pdf_limits()
        assert tier in frontend, (
            f"тариф {tier} есть в TIER_FLAGS, но нет в TIER_PDF_PER_MONTH"
        )
        # null в JS → None в Python: безлимит.
        assert frontend[tier] == TIER_FLAGS[tier]["pdf_per_month"], (
            f"лимит PDF для {tier} разошёлся: витрина {frontend[tier]}, "
            f"гейт {TIER_FLAGS[tier]['pdf_per_month']}"
        )

    def test_free_has_one_pdf(self):
        """Решение владельца 30.08.2026: один PDF в месяц бесплатному тарифу.

        Число берём из TIER_FLAGS, а не литералом, — иначе тест разойдётся с
        кодом при следующей правке сетки и будет стеречь вчерашнее решение.
        """
        assert TIER_FLAGS["free"]["pdf_export"] is True
        assert _parse_frontend_pdf_limits()["free"] == TIER_FLAGS["free"]["pdf_per_month"]

    def test_storefront_line_shows_the_flag_number(self):
        """Строка витрины содержит именно то число, что стоит в сетке."""
        src = CONSTANTS_JS.read_text(encoding="utf-8")
        # Прозы с числом PDF в features остаться не должно — только вызов
        # pdfFeatureLabel, иначе смысл правки потерян.
        assert "PDF-экспорт (" not in src, (
            "число PDF снова набрано прозой в features — оно обязано выводиться "
            "из TIER_PDF_PER_MONTH через pdfFeatureLabel"
        )
        for tier in TIER_FLAGS:
            assert f"pdfFeatureLabel('{tier}')" in src, (
                f"пункт PDF для {tier} не выводится из флага"
            )
