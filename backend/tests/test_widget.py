"""Виджет «День» (флаг widget, backend/widget.py)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pytest
import pytz

from backend import day_event as de
from backend import flags
from backend import story_card as sc
from backend import widget as wg
from backend.models import FeatureFlag
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура

TZ = pytz.timezone("Europe/Moscow")
CTX = ("Europe/Moscow", "08:00", "22:00")


def _ev(transit="Moon", natal="Venus", aspect="trine"):
    return de.DayEvent(key="k", at_local=TZ.localize(datetime(2026, 10, 2, 15, 1)),
                       transit=transit, natal=natal, aspect=aspect, score=6, timed=True)


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def flag_on(db, user_free):
    db.add(FeatureFlag(key=wg.FLAG, mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


class TestPhaseAdvice:
    """Согласовано владельцем таблицей (docs/widget_phase_texts.md)."""

    def test_every_phase(self):
        assert set(wg.PHASE_ADVICE) == set(sc.PHASES)

    def test_short_and_unique(self):
        texts = list(wg.PHASE_ADVICE.values())
        assert max(map(len, texts)) <= 60
        assert len(texts) == len(set(texts))


class TestDay:
    def test_event_same_as_push(self, chart):
        ev = _ev()
        with patch.object(de, "main_event", return_value=ev):
            got = wg.day(chart, date(2026, 10, 2), *CTX)
        assert got["title"] == de.title(ev) == "15:01 · Луна к твоей Венере"
        assert got["advice"] == de.advice(ev)
        assert got["day"] == "2 октября"
        assert got["date"] == "2026-10-02"

    def test_no_event_phase(self, chart):
        with patch.object(de, "main_event", return_value=None):
            got = wg.day(chart, date(2026, 10, 1), *CTX)
        assert got["phase"] == "убывающая Луна"
        assert got["title"] == "Убывающая Луна"
        assert got["advice"] == wg.PHASE_ADVICE["waning_gibbous"]
        assert 90 < got["elong"] < 270

    def test_lunation_names_the_day(self, chart):
        ev = de.DayEvent(key="n", at_local=TZ.localize(datetime(2026, 10, 10, 9, 50)),
                         transit="new_moon", natal=None, aspect=None, score=12, timed=True)
        with patch.object(de, "main_event", return_value=ev):
            got = wg.day(chart, date(2026, 10, 10), *CTX)
        assert got["phase"] == "новолуние"
        assert got["title"] == "09:50 · Новолуние"

    def test_days_count(self, chart, user_free):
        with patch.object(de, "main_event", return_value=None):
            got = wg.days(user_free, chart, date(2026, 10, 2))
        assert len(got) == wg.DAYS
        assert got[-1]["date"] == "2026-10-15"


class TestEndpoint:
    def test_flag_off_404(self, client, auth_headers_free, chart):
        assert client.get("/api/v1/widget", headers=auth_headers_free).status_code == 404

    def test_days(self, client, auth_headers_free, chart, flag_on):
        with patch.object(de, "main_event", return_value=None):
            r = client.get("/api/v1/widget", headers=auth_headers_free)
        assert r.status_code == 200
        days = r.json()["days"]
        assert len(days) == wg.DAYS
        assert set(days[0]) == {"date", "day", "phase", "elong", "title", "advice"}
        assert r.json()["first_week"] is False   # флага first_week нет

    def test_no_chart_empty(self, client, auth_headers_free, flag_on):
        r = client.get("/api/v1/widget", headers=auth_headers_free)
        assert r.json() == {"days": [], "first_week": False}

    def test_event(self, client, db, auth_headers_free, flag_on):
        from backend.metrics import _widget_line
        from backend.models import WidgetEvent
        post = lambda body: client.post("/api/v1/widget/event", json=body, headers=auth_headers_free)
        assert post({"kind": "shown", "source": "card"}).status_code == 204
        assert post({"kind": "added", "source": "first_week"}).status_code == 204
        assert post({"kind": "x", "source": "card"}).status_code == 422
        assert db.query(WidgetEvent).count() == 2
        assert _widget_line(db) == ("Виджет за 7 дней: показы — первая неделя 0, карточка 1; "
                                    "добавления — первая неделя 1, карточка 0, сами 0.")

    def test_event_flag_off_404(self, client, auth_headers_free):
        assert client.post("/api/v1/widget/event", json={"kind": "shown", "source": "card"},
                           headers=auth_headers_free).status_code == 404


class TestJavaCopy:
    """Без флага виджет считает фазу на телефоне (WidgetData.java) — советы
    там копией. Расходиться с таблицей владельца им нельзя."""

    def test_phase_advice_same_as_java(self):
        import re
        from pathlib import Path
        java = (Path(__file__).resolve().parents[2] / "frontend/plugins/widget/android/src/main/"
                "java/ru/aristeatime/widget/WidgetData.java").read_text(encoding="utf-8")
        block = re.search(r"PHASE_ADVICE = \{(.*?)\};", java, re.S).group(1)
        assert re.findall(r'"([^"]+)"', block) == [wg.PHASE_ADVICE[k] for k in sc.PHASES]

    def test_phase_labels_same_as_java(self):
        import re
        from pathlib import Path
        java = (Path(__file__).resolve().parents[2] / "frontend/plugins/widget/android/src/main/"
                "java/ru/aristeatime/widget/WidgetData.java").read_text(encoding="utf-8")
        block = re.search(r"String\[\] PHASES = \{(.*?)\};", java, re.S).group(1)
        assert re.findall(r'"([^"]+)"', block) == [label for label, _ in sc.PHASES.values()]
