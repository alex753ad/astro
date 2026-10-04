"""Подписи ретроградной петли (решение владельца 04.10.2026).

Карта ленты (test_feed._chart), Венера: во 2 дом 20.09.2026, назад в 1 —
15.10 (ретроградность 03.10–14.11), снова во 2 — 12.12, в 3 — 12.01.2027.
Полоса «сейчас» — frontend/src/mobile/lib/feedNow.test.js."""

from __future__ import annotations

from datetime import date

import pytest

from backend.feed.builder import build_feed, feed_cache
from backend.tests.test_feed import _chart
from backend.transit.house_passages import compute_upcoming
from backend.transit.planner_engine import build_planner

TZ = "Europe/Moscow"


@pytest.fixture(autouse=True)
def _clean():
    feed_cache.clear()
    yield
    feed_cache.clear()


def _profile():
    c = _chart()
    return {"planets": c.planets, "houses": c.houses, "ascendant": c.ascendant, "midheaven": c.midheaven}


def test_both_planner_blocks_explain_the_loop():
    p = build_planner(_profile(), date(2026, 10, 1), date(2026, 10, 31), today=date(2026, 10, 10),
                      user_timezone=TZ, tier="premium")
    venus = next(s for s in p["month_sections"] if s["planet"] == "venus")
    notes = {x["house"]: (x["period"], x["loop_note"]) for x in venus["periods"]}
    assert notes[1] == ("12.08 — 12.12", "с 20.09 по 15.10 Венера заходит во 2 дом")
    assert notes[2][1] == "с 15.10 по 12.12 Венера возвращается в 1 дом"
    assert notes[2][0].startswith("20.09") and notes[2][0].endswith("12.01")


def _venus_upcoming(d):
    return [u for u in compute_upcoming(_profile(), d, user_timezone=TZ) if u["planet"] == "venus"]


def test_upcoming_rows_for_each_loop_crossing():
    up = _venus_upcoming(date(2026, 10, 1))
    assert {"date": "2026-10-15", "kind": "loop", "house": 1, "direction": "back"}.items() <= next(
        u for u in up if u["kind"] == "loop").items()
    up = _venus_upcoming(date(2026, 11, 25))
    assert {"date": "2026-12-12", "kind": "loop", "house": 2, "direction": "again"}.items() <= next(
        u for u in up if u["kind"] == "loop").items()
    # Вход во 2 дом — один переход «до 12 января», с заходом петли внутри.
    passage = next(u for u in _venus_upcoming(date(2026, 9, 15)) if u["kind"] == "passage")
    assert (passage["date"], passage["house"], passage["until"]) == ("2026-09-20", 2, "2027-01-12")
    assert passage["loops"] == [{"house": 1, "from": "2026-10-15", "to": "2026-12-12", "direction": "back"}]


def test_feed_cards_for_loop_crossings_and_notes():
    ev = build_feed(chart=_chart(), from_date=date(2026, 8, 1), to_date=date(2027, 2, 1),
                    today=date(2026, 9, 4), tier="pro")["events"]
    loops = [(e["at"][:10], e["text"]) for e in ev if e["kind"] == "house_loop" and e["meta"]["planet"] == "venus"]
    assert loops == [("2026-10-15", "Венера возвращается в 1 дом"),
                     ("2026-12-12", "Венера снова переходит во 2 дом")]
    periods = {e["meta"]["house"]: e for e in ev if e["kind"] == "planner_period" and e["meta"]["planet"] == "venus"}
    assert periods[1]["meta"]["loop_note"] == "с 20.09 по 15.10 Венера заходит во 2 дом"
    assert [(x["at"][:10], x["ends_at"][:10]) for x in periods[2]["meta"]["loops"]] == [("2026-10-15", "2026-12-12")]
