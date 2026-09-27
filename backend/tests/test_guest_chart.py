"""Гость приложения: анонимная карта, прогноз по токену, привязка без дубля,
чистка просроченных (заход (a), решения владельца 27.09.2026)."""

from datetime import timedelta

from backend.models import NatalChart
from backend.tests.test_chart_access import _make_chart
from backend.tests.test_forecast import GOOD_DAILY, URL_TODAY, model  # noqa: F401 — фикстура
from backend.time_utils import utcnow


def _guest_chart(db, token="guest-tok", days=7):
    return _make_chart(db, access_token=token, expires_at=utcnow() + timedelta(days=days))


# ── Привязка ─────────────────────────────────────────────

def test_claim_moves_same_row_no_duplicate(client, db, user_free, auth_headers_free):
    chart = _guest_chart(db)
    before = db.query(NatalChart).count()

    resp = client.post(f"/api/v1/chart/{chart.id}/claim",
                       headers={**auth_headers_free, "X-Chart-Token": "guest-tok"})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": chart.id, "claimed": True}
    assert db.query(NatalChart).count() == before, "привязка создала вторую строку"
    db.refresh(chart)
    db.refresh(user_free)
    assert chart.user_id == user_free.id
    assert chart.access_token is None and chart.expires_at is None
    assert user_free.primary_chart_id == chart.id


def test_claim_again_by_owner_is_noop(client, db, user_free, auth_headers_free):
    chart = _guest_chart(db)
    h = {**auth_headers_free, "X-Chart-Token": "guest-tok"}
    client.post(f"/api/v1/chart/{chart.id}/claim", headers=h)
    resp = client.post(f"/api/v1/chart/{chart.id}/claim", headers=auth_headers_free)
    assert resp.status_code == 200 and resp.json()["claimed"] is False


def test_claim_needs_token(client, db, auth_headers_free):
    chart = _guest_chart(db)
    assert client.post(f"/api/v1/chart/{chart.id}/claim", headers=auth_headers_free).status_code == 404
    wrong = {**auth_headers_free, "X-Chart-Token": "nope"}
    assert client.post(f"/api/v1/chart/{chart.id}/claim", headers=wrong).status_code == 404


def test_claim_expired_is_404(client, db, auth_headers_free):
    chart = _guest_chart(db, days=-1)
    h = {**auth_headers_free, "X-Chart-Token": "guest-tok"}
    assert client.post(f"/api/v1/chart/{chart.id}/claim", headers=h).status_code == 404


def test_claim_foreign_owned_chart_is_404(client, db, user_pro, auth_headers_free):
    chart = _make_chart(db, user_id=user_pro.id)
    assert client.post(f"/api/v1/chart/{chart.id}/claim", headers=auth_headers_free).status_code == 404


def test_claim_requires_login(client, db):
    chart = _guest_chart(db)
    assert client.post(f"/api/v1/chart/{chart.id}/claim",
                       headers={"X-Chart-Token": "guest-tok"}).status_code == 401


def test_claim_respects_slot_limit(client, db, user_free, auth_headers_free):
    from backend.auth.rate_limits import get_tier_limits
    for _ in range(get_tier_limits("free")["profiles_limit"]):
        _make_chart(db, user_id=user_free.id)
    chart = _guest_chart(db)
    resp = client.post(f"/api/v1/chart/{chart.id}/claim",
                       headers={**auth_headers_free, "X-Chart-Token": "guest-tok"})
    assert resp.status_code == 403
    db.refresh(chart)
    assert chart.user_id is None, "карта ушла на аккаунт сверх лимита"


# ── Прогноз гостю ────────────────────────────────────────

def test_guest_gets_forecast_by_token(client, db, model):  # noqa: F811
    chart = _guest_chart(db)
    model["replies"] = [GOOD_DAILY]
    resp = client.get(URL_TODAY.format(chart.id), headers={"X-Chart-Token": "guest-tok"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "model"


def test_forecast_without_token_or_login_is_404(client, db, model):  # noqa: F811
    chart = _guest_chart(db)
    assert client.get(URL_TODAY.format(chart.id)).status_code == 404


def test_guest_limit_only_for_ip_keys():
    from backend.auth.rate_limits import GUEST_UNLIMITED, guest_limit
    provider = guest_limit("30/day")
    assert provider("guest:ip:203.0.113.7") == "30/day"
    assert provider("guest:user:u-1") == GUEST_UNLIMITED


def test_guest_limits_are_on_routes():
    import inspect
    from backend import main
    from backend.forecast import router as fr
    assert 'guest_limit("20/day"), key_func=guest_key' in inspect.getsource(main)
    assert inspect.getsource(fr).count('guest_limit("30/day"), key_func=guest_key') == 2


# ── Чистка ───────────────────────────────────────────────

def test_purge_removes_only_expired_anonymous(db, user_free, monkeypatch):
    from backend import tasks
    expired = _guest_chart(db, token="a", days=-1)
    alive = _guest_chart(db, token="b", days=3)
    owned = _make_chart(db, user_id=user_free.id)
    ids = (expired.id, alive.id, owned.id)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    assert tasks.purge_expired_anonymous_charts() == {"deleted": 1}
    left = {c.id for c in db.query(NatalChart).filter(NatalChart.id.in_(ids))}
    assert left == {alive.id, owned.id}


# ── Заход (b): согласие гостя и письмо при привязке ──────

GUEST_PAYLOAD = {"birth_date": "1990-06-15", "birth_time": "10:30",
                 "birth_place": "Moscow, Russia", "house_system": "placidus"}


def test_guest_consent_is_recorded_on_chart(client, db, mock_geo):
    from backend.auth.consent import CURRENT_PRIVACY_VERSION
    resp = client.post("/api/v1/chart/calculate", json={**GUEST_PAYLOAD, "consent": True})
    assert resp.status_code == 200, resp.text
    chart = db.get(NatalChart, resp.json()["id"])
    assert chart.consent_given_at is not None
    assert chart.consent_privacy_version == CURRENT_PRIVACY_VERSION


def test_consent_stays_on_chart_after_claim(client, db, user_free, auth_headers_free, monkeypatch):
    from backend import tasks
    monkeypatch.setattr(tasks.send_claim_welcome_task, "delay", lambda *a: None)
    chart = _guest_chart(db)
    chart.consent_given_at = utcnow()
    chart.consent_privacy_version = "2026-09-02"
    db.commit()
    client.post(f"/api/v1/chart/{chart.id}/claim", headers={**auth_headers_free, "X-Chart-Token": "guest-tok"})
    db.refresh(chart)
    assert chart.user_id == user_free.id and chart.consent_privacy_version == "2026-09-02"


def test_claim_queues_welcome(client, db, user_free, auth_headers_free, monkeypatch):
    from backend import tasks
    queued = []
    monkeypatch.setattr(tasks.send_claim_welcome_task, "delay", lambda *a: queued.append(a))
    chart = _guest_chart(db)
    client.post(f"/api/v1/chart/{chart.id}/claim", headers={**auth_headers_free, "X-Chart-Token": "guest-tok"})
    assert queued == [(user_free.id, chart.id)]


def test_claim_welcome_sent_once_and_only_for_first_chart(db, user_free, monkeypatch):
    from unittest.mock import AsyncMock
    from backend import email_service, tasks
    from backend.models import EmailSentLog
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, "send_welcome_email", sent)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    chart = _make_chart(db, user_id=user_free.id)

    assert tasks.send_claim_welcome_task(user_free.id, chart.id) is True
    assert tasks.send_claim_welcome_task(user_free.id, chart.id) is False
    assert sent.await_count == 1
    assert db.query(EmailSentLog).filter_by(user_id=user_free.id, kind=tasks.WELCOME_CLAIM_KIND).count() == 1

    second = _make_chart(db, user_id=user_free.id)
    db.query(EmailSentLog).delete()
    db.commit()
    assert tasks.send_claim_welcome_task(user_free.id, second.id) is False, "у аккаунта уже была карта"
