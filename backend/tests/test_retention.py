"""Удержание D1/D7/D30: запись активных дней (backend/activity.py) и расчёт
(metrics.compute_retention_weekly). Правило «вернулся» — в metrics.py."""

from datetime import date, datetime, timedelta

import pytest

from backend import flags
from backend.activity import msk_today
from backend.auth.jwt import create_access_token
from backend.metrics import compute_retention_weekly, retention_summary_text
from backend.models import FeatureFlag, User, UserActivityDay


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


def _rows(db):
    return sorted((r.platform, r.flags) for r in db.query(UserActivityDay).all())


# ── Запись ──────────────────────────────────────────────

def test_web_and_app_recorded_once_per_day(client, db, auth_headers_free, user_free):
    for _ in range(3):
        assert client.get("/api/v1/auth/me", headers=auth_headers_free).status_code == 200
    client.get("/api/v1/auth/me", headers={**auth_headers_free, "Origin": "https://localhost"})
    assert _rows(db) == [("app", []), ("web", [])]
    assert {r.day for r in db.query(UserActivityDay)} == {msk_today()}


def test_background_requests_not_counted(client, db, auth_headers_free):
    client.post("/api/v1/push/device", headers=auth_headers_free, json={"token": "t1"})
    client.get("/api/v1/push/upcoming", headers=auth_headers_free)
    assert _rows(db) == []


def test_anonymous_not_counted(client, db):
    client.get("/api/v1/flags")
    assert _rows(db) == []


def test_flags_of_the_day_recorded(client, db, auth_headers_free, user_free):
    db.add(FeatureFlag(key="test_flag", mode="users", user_ids=[user_free.id]))
    db.commit()
    client.get("/api/v1/auth/me", headers=auth_headers_free)
    assert _rows(db) == [("web", ["test_flag"])]


# ── Расчёт ──────────────────────────────────────────────

TODAY = date(2026, 12, 1)
D0 = date(2026, 10, 5)  # понедельник


def _user(db, email, d0=D0, tier="free", **kw):
    # 09:00 UTC = 12:00 МСК того же дня
    u = User(email=email, tier=tier, created_at=datetime.combine(d0, datetime.min.time()) + timedelta(hours=9), **kw)
    db.add(u)
    db.commit()
    return u


def _active(db, user, offset, platform="web", flags_=(), d0=D0):
    db.add(UserActivityDay(user_id=user.id, day=d0 + timedelta(days=offset),
                           platform=platform, flags=list(flags_)))
    db.commit()


def test_windows(db):
    a = _user(db, "a@x.ru")
    _active(db, a, 0, "app")
    _active(db, a, 1, "app")
    _active(db, a, 13, "web")   # последний день окна D7
    b = _user(db, "b@x.ru")
    _active(db, b, 0)
    _active(db, b, 2)           # между окнами — не возврат
    _active(db, b, 14)          # после окна D7
    _active(db, b, 36)          # последний день окна D30
    total = compute_retention_weekly(db, today=TODAY)["groups"][0]["total"]
    assert total["users"] == 2
    assert total["d1"] == {"retained": 1, "eligible": 2, "pct": 50, "app": 1, "web": 0}
    assert total["d7"] == {"retained": 1, "eligible": 2, "pct": 50, "app": 0, "web": 1}
    assert total["d30"]["retained"] == 1


def test_window_not_over_not_in_denominator(db):
    u = _user(db, "a@x.ru")
    _active(db, u, 0)
    _active(db, u, 1)
    total = compute_retention_weekly(db, today=D0 + timedelta(days=13))["groups"][0]["total"]
    assert total["d1"]["eligible"] == 1
    assert total["d7"] == {"retained": 0, "eligible": 0, "pct": None, "app": 0, "web": 0}


def test_cohort_starts_with_first_recorded_day(db):
    old = _user(db, "old@x.ru", d0=D0 - timedelta(days=3))
    new = _user(db, "new@x.ru")
    _active(db, new, 0)
    _active(db, old, 3)  # старый пользователь зашёл в первый день записи
    res = compute_retention_weekly(db, today=TODAY)
    assert res["since"] == D0.isoformat()
    assert res["groups"][0]["total"]["users"] == 1


def test_admins_and_excluded_skipped(db):
    for i, kw in enumerate(({}, {"is_admin": True}, {"revenue_excluded": True})):
        _active(db, _user(db, f"{i}@x.ru", **kw), 0)
    assert compute_retention_weekly(db, today=TODAY)["groups"][0]["total"]["users"] == 1


def test_platform_tier_and_flag_split(db):
    a = _user(db, "a@x.ru", tier="pro")
    _active(db, a, 0, "app", ["test_flag"])
    _active(db, a, 0, "web")
    b = _user(db, "b@x.ru")
    _active(db, b, 0, "web")
    _active(db, b, 1, "web", ["test_flag"])
    c = _user(db, "c@x.ru")
    _active(db, c, 0, "web")
    _active(db, c, 2, "web", ["test_flag"])  # флаг позже дня 1 — не в счёт

    def users(**kw):
        return [g["total"]["users"] for g in compute_retention_weekly(db, today=TODAY, **kw)["groups"]]

    assert users(platform="app") == [1]   # в первый день и там, и там — приложение
    assert users(platform="web") == [2]
    assert users(tier="pro") == [1]
    assert users(flag="test_flag") == [2, 1]


def test_weeks_grouped_by_monday(db):
    _active(db, _user(db, "a@x.ru"), 0)
    d = D0 + timedelta(days=9)  # среда следующей недели
    _active(db, _user(db, "b@x.ru", d0=d), 0, d0=d)
    weeks = compute_retention_weekly(db, today=TODAY)["groups"][0]["weeks"]
    assert [w["week"] for w in weeks] == ["2026-10-12", "2026-10-05"]


def test_empty(db):
    assert compute_retention_weekly(db) == {"since": None, "groups": []}
    assert "Данных пока нет" in retention_summary_text(db)


def test_summary_text(db):
    a = _user(db, "a@x.ru")
    _active(db, a, 0, "app")
    _active(db, a, 1, "app")
    text = retention_summary_text(db, today=TODAY)
    assert "2026-10-05: 1 · 100% (1/1) · 0% (0/1) · 0% (0/1)" in text
    assert "Приложение: 1 · D1 100% (1/1)" in text
    assert "Сайт: 0 · D1 —" in text


# ── Ручка ───────────────────────────────────────────────

def test_endpoint_admin_only(client, db, auth_headers_free):
    assert client.get("/api/v1/admin/retention", headers=auth_headers_free).status_code == 403
    admin = _user(db, "admin@x.ru", is_admin=True)
    h = {"Authorization": f"Bearer {create_access_token(user_id=admin.id, email=admin.email, tier='free')}"}
    resp = client.get("/api/v1/admin/retention", headers=h)
    assert resp.status_code == 200, resp.text
    assert "test_flag" in resp.json()["flags"]
    assert client.get("/api/v1/admin/retention?platform=tv", headers=h).status_code == 422
    assert client.get("/api/v1/admin/retention?flag=nope", headers=h).status_code == 422
