"""tests/test_consent_versions.py — CURRENT_TERMS_VERSION/CURRENT_PRIVACY_VERSION
должны совпадать с «Дата публикации» на /terms и /privacy.

20.08.2026: версии в backend/auth/consent.py — это то, что записывается в
consent_terms_version/consent_privacy_version при регистрации и попадает в
выгрузку «Скачать мои данные». Если константа разойдётся с датой на самой
странице, доказать, с какой именно редакцией согласился пользователь, будет
нельзя — ради этого константа вообще завели.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.auth.consent import CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION

_MONTHS_RU = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}

_FRONTEND_PAGES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"


def _extract_publication_date(page_file: str) -> str:
    text = (_FRONTEND_PAGES / page_file).read_text(encoding="utf-8")
    m = re.search(r"Дата публикации:\s*(\d{1,2})\s+([а-яёА-ЯЁ]+)\s+(\d{4})\s*г\.", text)
    assert m, f"'Дата публикации: ...' не найдена в {page_file}"
    day, month_ru, year = m.groups()
    month = _MONTHS_RU.get(month_ru.lower())
    assert month, f"Неизвестный месяц {month_ru!r} в {page_file}"
    return f"{year}-{month}-{int(day):02d}"


class TestConsentVersionsMatchPages:
    def test_terms_version_matches_page(self):
        assert CURRENT_TERMS_VERSION == _extract_publication_date("TermsPage.jsx")

    def test_privacy_version_matches_page(self):
        assert CURRENT_PRIVACY_VERSION == _extract_publication_date("PrivacyPage.jsx")
