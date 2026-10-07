"""Шаг 9 (термины): «окно» → «период» в пушах и письмах — только под
флагом sky_event. Без флага текст прежний слово в слово (решение владельца
07.10.2026, docs/decisions.md, «Шаг 9»).
"""
import asyncio

import pytest

from backend import email_service as es
from backend.transit.engine import _build_transit_alert_subject


@pytest.fixture
def sent(monkeypatch):
    """Всё, что ушло бы в `_send_info`: тема, превью и тело одной строкой."""
    out = []

    async def fake(to, subject, title, preview, body, *, unsubscribe_url):
        out.append(" ".join((subject, title, preview, body)))
        return True

    monkeypatch.setattr(es, "_send_info", fake)
    return out


def _letters(sky):
    """Все письма с «окном» в тексте — с флагом `sky`."""
    u = "https://x/unsub"
    return [
        es.send_pilot_farewell("a@b", [], unsubscribe_url=u, sky=sky),
        es.send_dormant("a@b", 5, unsubscribe_url=u, sky=sky),
        es.send_dormant("a@b", 10, unsubscribe_url=u, sky=sky),
        es.send_end_of_month_survey("a@b", "https://x/s", unsubscribe_url=u, sky=sky),
        es.send_transit_alert_email("a@b", "Юпитер", "трин", "Солнце", "2026-10-08",
                                    "текст", "тема", "https://x", unsubscribe_url=u, sky=sky),
    ]


def _run(coros):
    async def go():
        for c in coros:
            await c
    asyncio.run(go())


def test_letters_without_flag_keep_window(sent):
    _run(_letters(False))
    assert all("окн" in s for s in sent), [s[:80] for s in sent if "окн" not in s]


def test_letters_under_flag_have_no_window(sent):
    _run(_letters(True))
    assert len(sent) == 5
    for s in sent:
        assert "окн" not in s, s[:200]
        assert "период" in s, s[:200]


def test_alert_subject_harmonious():
    old = _build_transit_alert_subject("Jupiter", "Sun", "trine", "Юпитер")
    new = _build_transit_alert_subject("Jupiter", "Sun", "trine", "Юпитер", sky=True)
    assert old.startswith("Окно открылось:")
    assert new.startswith("Юпитер открывает период:") and "окн" not in new.lower()
