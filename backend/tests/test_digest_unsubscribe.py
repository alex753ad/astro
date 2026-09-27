"""Недельный дайджест: отписка по ссылке из письма и умолчания нового
пользователя (решения владельца 27.09.2026)."""

from backend.models import User
from backend.profile.digest_unsubscribe import ensure_unsub_token


def test_new_user_has_all_notifications_on_and_monday_digest(db):
    user = User(email="new-defaults@example.com", hashed_password=None)
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.push_daily_forecast is True
    assert user.push_planner is True
    assert user.push_key_transits is True
    assert user.push_moon_phases is True
    assert user.digest_day_of_week == 0  # понедельник
    assert user.digest_opt_out is False


def test_get_does_not_unsubscribe_post_does(client, db, user_free):
    token = ensure_unsub_token(user_free, db)
    url = f"/api/v1/email/digest/unsubscribe/{token}"

    # Переход по ссылке (и почтовый сканер) только показывает кнопку.
    resp = client.get(url)
    assert resp.status_code == 200
    assert "<form" in resp.text
    db.refresh(user_free)
    assert user_free.digest_opt_out is False

    resp = client.post(url)
    assert resp.status_code == 200
    db.refresh(user_free)
    assert user_free.digest_opt_out is True


def test_head_is_allowed(client, db, user_free):
    token = ensure_unsub_token(user_free, db)
    assert client.head(f"/api/v1/email/digest/unsubscribe/{token}").status_code == 200


def test_unknown_token(client):
    resp = client.post("/api/v1/email/digest/unsubscribe/nope")
    assert resp.status_code == 200
    assert "недействительна" in resp.text


def test_token_is_stable(db, user_free):
    assert ensure_unsub_token(user_free, db) == ensure_unsub_token(user_free, db)


def test_digest_task_skips_opted_out():
    import inspect
    from backend import tasks
    src = inspect.getsource(tasks.send_weekly_digest_task)
    assert "digest_opt_out == False" in src


def test_digest_email_has_working_unsubscribe_link():
    from backend.email_service import _base
    html = _base("t", "p", "b", unsubscribe_url="https://x/api/v1/email/digest/unsubscribe/T")
    assert 'href="https://x/api/v1/email/digest/unsubscribe/T"' in html
    assert "Отписаться от дайджеста" in html
