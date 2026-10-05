"""Дайджест Лиры и Ориона — главные события по общему правилу
(day_event.pick_week), как у «Недели вперёд» (решение владельца 01.10.2026).
С 05.10.2026 (шаг 5) из тех же главных событий дней — и «Лучшие дни»;
«Совета недели» нет."""
from __future__ import annotations

import asyncio

from backend import day_event as de
from backend import email_service
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура
from backend.tests.test_week_ahead import WEEK, _ev


def _run(db, user, monkeypatch, events):
    """main_event по дням недели письма: события по порядку, дальше — пусто."""
    calls, got = [], {}
    queue = list(events)

    def fake_main(c, d, *a):
        calls.append(d)
        return queue.pop(0) if queue else None
    monkeypatch.setattr(de, "main_event", fake_main)

    async def fake(to, subject, title, preview, body, *, unsubscribe_url):
        got.update(subject=subject, body=body)
        return True
    monkeypatch.setattr(email_service, "_send_info", fake)
    assert asyncio.run(email_service.send_weekly_digest(user, db))
    return calls, got


def test_same_events_as_week_ahead(db, user_free, chart, monkeypatch):
    calls, got = _run(db, user_free, monkeypatch, WEEK)
    assert len(calls) == 7  # семь дней письма, с сегодня
    for text in ("Ср, 7 октября · 16:49", "Сатурн к твоей Луне", "Новолуние",
                 "Выслушай другого до конца, прежде чем отвечать."):
        assert text in got["body"]


def test_subject_a_names_strongest_planet(db, user_free, chart, monkeypatch):
    monkeypatch.setattr("random.choice", lambda seq: "A")
    _, got = _run(db, user_free, monkeypatch, WEEK)
    assert got["subject"].startswith("Сатурн открывает окно")
    _, got = _run(db, user_free, monkeypatch, [WEEK[2]])  # только новолуние — тема B
    assert got["subject"].startswith("Твоя неделя")


def test_best_days_from_main_events_no_tip(db, user_free, chart, monkeypatch):
    """«Лучшие дни» — главные события с тоном «Гармония» и баллом ≥ 6;
    соединение (Начало) туда не попадает; «Совета недели» нет."""
    week = [_ev(7, "Venus", "Sun", "trine", 12.0), _ev(8, "Jupiter", "Venus", "conjunction", 24.0),
            _ev(9, "Moon", "Venus", "sextile", 2.0)]
    _, got = _run(db, user_free, monkeypatch, week)
    body = got["body"]
    assert "Лучшие дни недели" in body and "7 октября — Венера к твоему Солнцу" in body
    assert "8 октября — Юпитер" not in body and "9 октября — Луна" not in body
    assert "Совет недели" not in body
