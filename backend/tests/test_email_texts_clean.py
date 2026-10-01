"""Письма: знак со склонением, без ✦ (находки с телефона, 01.10.2026)."""
from pathlib import Path

import pytest

from backend import email_service
from backend.ephemeris.ru_names import SIGN_IN_RU

ROOT = Path(__file__).resolve().parents[2]
# Все модули, которые собирают письма (_send / _send_info / Resend).
EMAIL_SOURCES = [
    "backend/email_service.py", "backend/lifecycle_emails.py", "backend/auth/router.py",
    "backend/crm/dashboard_router.py", "backend/payments/price_notice.py",
]


def test_no_star_in_any_email_source():
    """✦ убран из писем, как из пушей: ни в теме, ни в тексте, ни на кнопке."""
    bad = [p for p in EMAIL_SOURCES if "✦" in (ROOT / p).read_text(encoding="utf-8")]
    assert not bad, bad


@pytest.fixture
def captured(monkeypatch):
    out = {}

    async def fake(to, subject, title, preview, body, **kw):
        out.update(subject=subject, preview=preview, body=body)
        return True

    monkeypatch.setattr(email_service, "_send_info", fake)
    return out


@pytest.mark.parametrize("sign", sorted(SIGN_IN_RU))
async def test_welcome_sign_declined(captured, sign):
    await email_service.send_welcome_email(
        "a@b.c", planets=[{"name": "Sun", "sign": sign}], unsubscribe_url="u")
    assert f"Солнце {SIGN_IN_RU[sign]}," in captured["subject"]
    assert captured["preview"].startswith(f"Солнце {SIGN_IN_RU[sign]}. ")
    assert "::" not in captured["preview"] and ": Твоя" not in captured["preview"]
    assert "✦" not in captured["subject"] + captured["body"]
