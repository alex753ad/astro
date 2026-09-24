"""Время — в поясе устройства, пояс карты только запасной (решение 24.09.2026).

Лента, планер и уведомления до этого считали всё в поясе ГЛАВНОЙ КАРТЫ, то
есть места рождения: родившийся в Москве и живущий в Новосибирске видел
события и получал утреннее уведомление по московскому времени.
"""

from __future__ import annotations

import types
from datetime import datetime

import pytest

from backend.push.cron import user_timezone
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура


class TestOrder:
    def _u(self, tz=None):
        return types.SimpleNamespace(device_timezone=tz)

    def test_request_beats_stored_beats_chart(self):
        ch = types.SimpleNamespace(timezone="Europe/Moscow")
        assert user_timezone(self._u("Asia/Novosibirsk"), ch, "Asia/Tokyo") == "Asia/Tokyo"
        assert user_timezone(self._u("Asia/Novosibirsk"), ch) == "Asia/Novosibirsk"
        assert user_timezone(self._u(), ch) == "Europe/Moscow"

    def test_garbage_falls_back(self):
        ch = types.SimpleNamespace(timezone="Europe/Moscow")
        assert user_timezone(self._u("Mars/Olympus"), ch, "не пояс") == "Europe/Moscow"


class TestSettings:
    def test_patch_stores_device_timezone(self, client, auth_headers_free, db, user_free):
        r = client.patch("/api/v1/push/settings", json={"timezone": "Asia/Novosibirsk"},
                         headers=auth_headers_free)
        assert r.status_code == 200, r.text
        assert r.json()["timezone"] == "Asia/Novosibirsk"
        db.refresh(user_free)
        assert user_free.device_timezone == "Asia/Novosibirsk"

    def test_patch_rejects_garbage(self, client, auth_headers_free):
        r = client.patch("/api/v1/push/settings", json={"timezone": "Mars/Olympus"},
                         headers=auth_headers_free)
        assert r.status_code == 422


class TestUpcoming:
    def test_stored_device_timezone_is_used(self, client, auth_headers_free, db, user_free, chart):  # noqa: F811
        user_free.device_timezone = "Asia/Novosibirsk"
        db.commit()
        body = client.get("/api/v1/push/upcoming?days=3", headers=auth_headers_free).json()
        assert body["timezone"] == "Asia/Novosibirsk"
        for e in body["events"]:
            assert datetime.fromisoformat(e["at"]).utcoffset().total_seconds() == 7 * 3600

    def test_request_timezone_wins(self, client, auth_headers_free, chart):  # noqa: F811
        body = client.get("/api/v1/push/upcoming?days=3&tz=Asia/Tokyo", headers=auth_headers_free).json()
        assert body["timezone"] == "Asia/Tokyo"

    def test_without_device_timezone_chart_zone(self, client, auth_headers_free, chart):  # noqa: F811
        body = client.get("/api/v1/push/upcoming?days=3", headers=auth_headers_free).json()
        assert body["timezone"] == "Europe/Moscow"


class TestFeed:
    def test_times_follow_phone_zone(self, client, auth_headers_free, chart):  # noqa: F811
        url = f"/api/v1/chart/{chart.id}/feed?from_date=2026-10-01&to_date=2026-10-10"
        msk = client.get(url, headers=auth_headers_free).json()
        nsk = client.get(url + "&tz=Asia/Novosibirsk", headers=auth_headers_free).json()
        assert msk["timezone"] == "Europe/Moscow"
        assert nsk["timezone"] == "Asia/Novosibirsk"
        by_key = {e["key"]: e for e in msk["events"]}
        moved = [
            (datetime.fromisoformat(by_key[e["key"]]["at"]), datetime.fromisoformat(e["at"]))
            for e in nsk["events"] if e["key"] in by_key and e["kind"] == "moon_phase"
        ]
        assert moved, "в окне нет лунных фаз — проверка пустая"
        for a, b in moved:
            assert a == b                          # тот же момент
            assert b.utcoffset().total_seconds() == 7 * 3600   # по часам Новосибирска

    def test_garbage_tz_falls_back_to_chart(self, client, auth_headers_free, chart):  # noqa: F811
        url = f"/api/v1/chart/{chart.id}/feed?from_date=2026-10-01&to_date=2026-10-03&tz=junk"
        assert client.get(url, headers=auth_headers_free).json()["timezone"] == "Europe/Moscow"

    def test_chart_row_is_not_modified(self, client, auth_headers_free, db, chart):  # noqa: F811
        url = f"/api/v1/chart/{chart.id}/feed?from_date=2026-10-01&to_date=2026-10-03&tz=Asia/Tokyo"
        client.get(url, headers=auth_headers_free)
        db.refresh(chart)
        assert chart.timezone == "Europe/Moscow"


class TestPlanner:
    def test_planner_accepts_tz(self, client, auth_headers_free, chart):  # noqa: F811
        r = client.get(f"/api/v1/chart/{chart.id}/planner/monthly?tz=Asia/Novosibirsk",
                       headers=auth_headers_free)
        assert r.status_code == 200, r.text
