"""Дайджест Лиры и Ориона — главные события по общему правилу
(day_event.week_events), как у «Недели вперёд» (решение владельца 01.10.2026)."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from backend import day_event as de
from backend import email_service
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура
from backend.tests.test_week_ahead import WEEK


def _run(db, user, monkeypatch, events):
    calls, got = [], {}
    monkeypatch.setattr(de, "week_events", lambda c, d, *a: calls.append(d) or events)

    async def fake(to, subject, title, preview, body, *, unsubscribe_url):
        got.update(subject=subject, body=body)
        return True
    monkeypatch.setattr(email_service, "_send_info", fake)
    assert asyncio.run(email_service.send_weekly_digest(user, db))
    return calls, got


def test_same_events_as_week_ahead(db, user_free, chart, monkeypatch):
    calls, got = _run(db, user_free, monkeypatch, WEEK)
    assert calls == [date.today() - timedelta(days=1)]  # неделя письма — с сегодня
    for text in ("Ср, 7 октября · 16:49", "Сатурн к твоей Луне", "Новолуние",
                 "Выслушай другого до конца, прежде чем отвечать."):
        assert text in got["body"]


def test_subject_a_names_strongest_planet(db, user_free, chart, monkeypatch):
    monkeypatch.setattr("random.choice", lambda seq: "A")
    _, got = _run(db, user_free, monkeypatch, WEEK)
    assert got["subject"].startswith("Сатурн открывает окно")
    _, got = _run(db, user_free, monkeypatch, [WEEK[2]])  # только новолуние — тема B
    assert got["subject"].startswith("Твоя неделя")
