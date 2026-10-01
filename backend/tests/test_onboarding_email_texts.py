"""Тексты писем онбординга дней 2, 7, 14 — без неправды (01.10.2026).

* день 2 называл «сегодняшним» транзит из недели вперёд;
* день 7 говорил «мимо тебя проходят N транзитов … закрыты» и звал на Лиру —
  список транзитов бесплатный видит, первый платный шаг — Вега;
* день 14 обещал «разбор карты (Вега и выше)», хотя один есть и бесплатно.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from backend import email_service
from backend.auth.rate_limits import TIER_FLAGS
from backend.lifecycle_emails import _build_transit_text

TODAY = date(2026, 10, 1)


def _ev(start, exact=None):
    return SimpleNamespace(transit_planet="Venus", natal_planet="Sun", aspect_type="trine",
                           start_date=start, exact_date=exact)


@pytest.mark.parametrize("ev, head", [
    (_ev("2026-09-28", "2026-10-04T10:00"), "4 октября "),
    (_ev("2026-09-28", "2026-09-30T10:00"), "Сейчас "),
    (_ev("2026-10-05", None), "С 5 октября "),
])
def test_day2_names_real_date(ev, head):
    text = _build_transit_text(ev, TODAY)
    assert text.startswith(head)
    assert not text.startswith("Сегодня")


@pytest.fixture
def captured(monkeypatch):
    out = {}

    async def fake(to, subject, title, preview, body, **kw):
        out.update(subject=subject, body=body)
        return True

    monkeypatch.setattr(email_service, "_send_info", fake)
    return out


async def test_day7_offers_vega_with_real_numbers(captured):
    await email_service.send_retention_day7("a@b.c", 12, unsubscribe_url="u")
    text = captured["subject"] + captured["body"]
    lite = email_service.TIER_NAMES["lite"]
    assert lite in text and email_service.TIER_NAMES["pro"] not in text
    assert "закрыт" not in text and "Мимо тебя" not in text
    assert f"{TIER_FLAGS['lite']['transits_ai_per_month']} разборов" in text
    assert "12 транзитов" in captured["subject"]


async def test_day14_numbers_from_tier_flags(captured):
    await email_service.send_retention_day14("a@b.c", unsubscribe_url="u")
    body = captured["body"]
    assert "разбор карты, " not in body
    assert f"{TIER_FLAGS['lite']['transits_months']} месяцев вперёд" in body
    assert email_service.ACCESS_TERM in body
