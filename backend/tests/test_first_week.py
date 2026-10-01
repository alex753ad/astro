"""Первая неделя по сценарию (флаг first_week, backend/first_week.py)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytz

from backend import first_week as fw
from backend import flags
from backend.models import DeviceToken, FeatureFlag, FirstWeekMark, PushSentLog
from backend.push import cron
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура
from backend.time_utils import utcnow

TZ = pytz.timezone("Europe/Moscow")


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def flag_on(db, user_free):
    db.add(FeatureFlag(key="first_week", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


def _registered(db, user, days_ago):
    user.created_at = utcnow() - timedelta(days=days_ago)
    db.commit()


class TestCardRule:
    @pytest.mark.parametrize("day, done, key", [
        (1, set(), "chart"),
        (3, {"chart"}, "forecast"),                       # раньше пропущенное — первым
        (3, {"chart", "forecast", "interpret"}, None),    # вперёд не забегаем
        (4, {"transit"}, "chart"),                        # открытое раньше своего дня
        (7, set(), "summary"),                            # в день 7 итог — первым
        (7, {"summary"}, "chart"),
        (7, set(fw.KEYS), None),
    ])
    def test_card_key(self, day, done, key):
        assert fw.card_key(day, done) == key

    def test_texts_fit_and_trial_only_for_free(self):
        assert fw._trial_tail("chat", "free") == " Три сообщения — на пробу."
        assert fw._trial_tail("transit", "free") == " Два разбора — на пробу."
        assert fw._trial_tail("chat", "lite") == ""
        for _, _, _, _, push in fw.STEPS:
            assert push is None or len(push) <= 60


class TestEndpoints:
    def test_flag_off_404(self, client, auth_headers_free):
        assert client.get("/api/v1/first-week", headers=auth_headers_free).status_code == 404
        assert client.post("/api/v1/first-week/seen", json={"key": "chart"},
                           headers=auth_headers_free).status_code == 404

    def test_day_one_card_then_seen(self, client, db, user_free, chart, flag_on, auth_headers_free):
        card = client.get("/api/v1/first-week", headers=auth_headers_free).json()["card"]
        assert (card["day"], card["key"], card["title"]) == (1, "chart", "Сегодня: твоя карта")
        assert client.post("/api/v1/first-week/seen", json={"key": "chart"},
                           headers=auth_headers_free).status_code == 200
        assert client.get("/api/v1/first-week", headers=auth_headers_free).json()["card"] is None

    def test_unknown_key(self, client, user_free, flag_on, auth_headers_free):
        assert client.post("/api/v1/first-week/seen", json={"key": "x"},
                           headers=auth_headers_free).status_code == 422

    def test_after_week_no_card(self, client, db, user_free, chart, flag_on, auth_headers_free):
        _registered(db, user_free, 8)
        assert client.get("/api/v1/first-week", headers=auth_headers_free).json()["card"] is None


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(cron, "send_to_user", lambda db_, uid, payload: out.append(payload) or 1)
    return out


class TestEveningPush:
    def _now(self, db, user, chart_):
        today = fw.local_today(user, chart_)
        return TZ.localize(datetime(today.year, today.month, today.day, 20, 30))

    def test_replaces_tomorrow_when_not_opened(self, db, user_free, chart, flag_on, sent):
        _registered(db, user_free, 2)  # день 3 — разбор карты
        db.add(DeviceToken(user_id=user_free.id, token="t", platform="android"))
        db.commit()
        assert cron._send_evening(db, user_free, chart, self._now(db, user_free, chart)) == 1
        assert sent[0]["title"] == "Разбор карты" and sent[0]["target"] == "feed_today"
        kinds = {r.kind for r in db.query(PushSentLog).all()}
        assert {"first_week", "tomorrow"} <= kinds

    def test_opened_today_keeps_tomorrow(self, db, user_free, chart, flag_on, sent):
        _registered(db, user_free, 2)
        db.add(DeviceToken(user_id=user_free.id, token="t", platform="android"))
        db.add(FirstWeekMark(user_id=user_free.id, key="interpret"))
        db.commit()
        cron._send_evening(db, user_free, chart, self._now(db, user_free, chart))
        assert sent[0]["title"] == "Прогноз на завтра"

    def test_web_only_keeps_tomorrow(self, db, user_free, chart, flag_on, sent):
        _registered(db, user_free, 2)
        cron._send_evening(db, user_free, chart, self._now(db, user_free, chart))
        assert sent[0]["title"] == "Прогноз на завтра"

    def test_flag_off_keeps_tomorrow(self, db, user_free, chart, sent):
        _registered(db, user_free, 2)
        db.add(DeviceToken(user_id=user_free.id, token="t", platform="android"))
        db.commit()
        cron._send_evening(db, user_free, chart, self._now(db, user_free, chart))
        assert sent[0]["title"] == "Прогноз на завтра"


def test_summary_wording_without_gender(db, user_free, chart):
    _registered(db, user_free, 6)
    s = fw.summary(db, user_free, chart)
    assert s["visits"] == "7 дней — 0 заходов"
    assert [t["key"] for t in s["tried"]] == list(fw.TRIED_KEYS)
    assert s["free"] is True
