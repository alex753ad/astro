"""Отписка от информационных писем (068, решение владельца 30.09.2026) и
умолчания нового пользователя (27.09.2026)."""

import inspect
from datetime import timedelta

import pytest

from backend import email_service
from backend.models import PushSentLog, User
from backend.profile.email_unsubscribe import unsubscribe_url
from backend.time_utils import utcnow

# Информационные письма — под отпиской: обязательный unsubscribe_url.
INFORMATIONAL = [
    "send_welcome_email", "send_retention_day2", "send_retention_day7", "send_retention_day14",
    "send_weekly_digest_email", "send_transit_alert_email", "send_lunar_return_email",
    "send_lite_day14", "send_pro_day30", "send_pilot_farewell", "send_dormant",
    "send_end_of_month_survey",
]
# Служебные — отписка их не останавливает, ссылки отписки у них нет.
SERVICE = [
    "send_otp_email", "send_password_code_email",
    "send_lite_welcome", "send_pro_welcome", "send_premium_welcome",
]


def test_new_user_notification_defaults_and_monday_digest(db):
    user = User(email="new-defaults@example.com", hashed_password=None)
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.push_daily_forecast is True
    assert user.push_planner is True
    assert user.push_key_transits is True
    assert user.push_moon_phases is False  # 072, решение владельца 01.10.2026
    assert user.digest_day_of_week == 0  # понедельник
    assert user.email_opt_out is False
    assert user.email_unsub_token, "без токена информационное письмо не уйдёт"


@pytest.mark.parametrize("name", INFORMATIONAL)
def test_informational_email_requires_unsubscribe_url(name):
    p = inspect.signature(getattr(email_service, name)).parameters["unsubscribe_url"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is inspect.Parameter.empty


@pytest.mark.parametrize("name", SERVICE)
def test_service_email_has_no_unsubscribe(name):
    assert "unsubscribe_url" not in inspect.signature(getattr(email_service, name)).parameters


def test_footer_link_only_with_url():
    plain = email_service._base("t", "p", "b")
    assert "Отписаться" not in plain
    assert "/unsubscribe" not in plain  # прежняя ссылка вела на несуществующую страницу

    html = email_service._base("t", "p", "b", unsubscribe_url="https://x/api/v1/email/unsubscribe/T")
    assert 'href="https://x/api/v1/email/unsubscribe/T"' in html
    assert "Отписаться от писем" in html


async def test_send_adds_one_click_headers_only_for_informational(monkeypatch):
    import httpx
    bodies = []

    async def fake_post(self, url, headers=None, json=None):
        bodies.append(json)
        return httpx.Response(200, json={"id": "1"})

    monkeypatch.setattr(email_service, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await email_service.send_retention_day14("a@example.com", unsubscribe_url="https://x/u/T")
    await email_service.send_otp_email("a@example.com", "123456")

    assert bodies[0]["headers"] == {
        "List-Unsubscribe": "<https://x/u/T>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    assert "headers" not in bodies[1]


def test_unsubscribe_url_none_when_opted_out(db, user_free):
    assert unsubscribe_url(user_free).endswith(f"/api/v1/email/unsubscribe/{user_free.email_unsub_token}")
    user_free.email_opt_out = True
    assert unsubscribe_url(user_free) is None


@pytest.mark.parametrize("path", ["/api/v1/email/unsubscribe/", "/api/v1/email/digest/unsubscribe/"])
def test_get_does_not_unsubscribe_post_does(client, db, user_free, path):
    url = path + user_free.email_unsub_token

    # Переход по ссылке (и почтовый сканер) только показывает кнопку.
    resp = client.get(url)
    assert resp.status_code == 200
    assert "<form" in resp.text
    db.refresh(user_free)
    assert user_free.email_opt_out is False

    resp = client.post(url)
    assert resp.status_code == 200
    assert "Письма больше не придут" in resp.text
    db.refresh(user_free)
    assert user_free.email_opt_out is True

    assert "уже оформлена" in client.get(url).text


def test_one_click_post_from_mail_client(client, db, user_free):
    """RFC 8058: почтовый клиент шлёт форму List-Unsubscribe=One-Click."""
    resp = client.post(f"/api/v1/email/unsubscribe/{user_free.email_unsub_token}",
                       data={"List-Unsubscribe": "One-Click"})
    assert resp.status_code == 200
    db.refresh(user_free)
    assert user_free.email_opt_out is True


def test_head_is_allowed(client, user_free):
    assert client.head(f"/api/v1/email/unsubscribe/{user_free.email_unsub_token}").status_code == 200


def test_unknown_token(client):
    resp = client.post("/api/v1/email/unsubscribe/nope")
    assert resp.status_code == 200
    assert "недействительна" in resp.text


def test_settings_return_emails(client, db, user_free, auth_headers_free):
    user_free.email_opt_out = True
    db.commit()
    assert client.get("/api/v1/push/settings", headers=auth_headers_free).json()["emails"] is False

    resp = client.patch("/api/v1/push/settings", json={"emails": True}, headers=auth_headers_free)
    assert resp.json()["emails"] is True
    db.refresh(user_free)
    assert user_free.email_opt_out is False


def test_digest_task_skips_opted_out():
    from backend import tasks
    assert "email_opt_out == False" in inspect.getsource(tasks.send_weekly_digest_task)


def test_lifecycle_skips_opted_out(db, monkeypatch):
    from backend.lifecycle_emails import run_lifecycle_emails
    sent = []

    async def fake_send(to, subject, html, **kw):
        sent.append(to)
        return True

    monkeypatch.setattr(email_service, "_send", fake_send)
    u = User(email="optout@example.com", tier="free", email_opt_out=True,
             created_at=utcnow() - timedelta(days=15))
    db.add(u)
    db.commit()

    assert run_lifecycle_emails(db)["retention_day14"] == 0
    assert sent == []


async def test_pilot_opted_out_marks_step_without_email(db, user_free, monkeypatch):
    """Шаг отмечается и без письма — иначе пуш рядом повторялся бы каждый тик."""
    from backend.pilot import cron

    async def must_not_send(*a, **k):
        raise AssertionError("письмо отписавшемуся")

    user_free.pilot_started_at = utcnow() - timedelta(days=28)
    user_free.email_opt_out = True
    db.commit()
    monkeypatch.setattr(cron, "_upcoming_windows", lambda db, user: [])
    monkeypatch.setattr("backend.email_service.send_pilot_farewell", must_not_send)
    monkeypatch.setattr("backend.push.sender.send_to_user", lambda *a, **k: 0)

    result = await cron._process(db, user_free)

    assert result.get("farewell") is True
    assert db.query(PushSentLog).filter(
        PushSentLog.user_id == user_free.id, PushSentLog.kind == "farewell",
    ).first() is not None
