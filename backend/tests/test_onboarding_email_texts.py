"""Тексты писем онбординга дней 2, 7, 14 — без неправды (01.10.2026).

* день 2 называл «сегодняшним» транзит из недели вперёд; с 05.10.2026 —
  главное событие дня (day_event), дата в тексте — его местная дата;
* день 7 говорил «мимо тебя проходят N транзитов … закрыты» и звал на Лиру —
  список транзитов бесплатный видит, первый платный шаг — Вега;
* день 14 обещал «разбор карты (Вега и выше)», хотя один есть и бесплатно.
"""
from types import SimpleNamespace

import pytest

from backend import email_service
from backend.auth.rate_limits import TIER_FLAGS
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.day_event import DayEvent
from backend.lifecycle_emails import _day2_text


def test_day2_main_event_with_date_and_advice():
    """Формат таблицы владельца 05.10.2026: «дата · событие», затем совет."""
    ev = DayEvent(key="k", at_local=datetime(2026, 10, 8, 14, 0, tzinfo=ZoneInfo("Europe/Moscow")),
                  transit="Venus", natal="Jupiter", aspect="square", score=5, timed=True)
    assert _day2_text(ev) == ("8 октября · <strong>Венера к твоему Юпитеру</strong><br><br>"
                              "Знай меру в покупках и обещаниях.")


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


async def test_day2_calm_fallback(captured):
    """Запасной день 2 — таблица владельца 05.10.2026, тема без «🌙»."""
    await email_service.send_retention_day2_calm("a@b.c", unsubscribe_url="u")
    assert captured["subject"] == "Твоя неделя"
    assert "🌙 Твоя неделя" in captured["body"]
    assert "Каждое утро тебя ждёт прогноз на день по твоей карте." in captured["body"]
