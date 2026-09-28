"""Почта без учёта регистра (приёмка 28.09.2026): в приложении клавиатура
подставляла «Lion_e@bk.ru», а сервер искал точным совпадением — вход
отказывал при верном пароле."""
import pytest

from backend.auth.emails import find_user_by_email
from backend.auth.passwords import hash_password
from backend.models import User


def _user(db, email):
    u = User(email=email, hashed_password=hash_password("Password123!"), tier="free")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.mark.parametrize("stored,typed", [
    ("test@mail.ru", "Test@Mail.ru"),
    ("Test@Mail.ru", "test@mail.ru"),
    ("test@mail.ru", "  test@mail.ru "),
])
def test_login_ignores_case_and_spaces(client, db, stored, typed):
    _user(db, stored)
    r = client.post("/api/v1/auth/login", json={"email": typed, "password": "Password123!"})
    assert r.status_code == 200, r.text


def test_wrong_password_still_401(client, db):
    _user(db, "test@mail.ru")
    r = client.post("/api/v1/auth/login", json={"email": "Test@Mail.ru", "password": "nope-nope1"})
    assert r.status_code == 401


def test_forgot_password_finds_user_in_any_case(client, db, monkeypatch):
    _user(db, "test@mail.ru")
    sent = []

    async def fake_send(to, subject, html):
        sent.append(to)
        return True
    monkeypatch.setattr("backend.email_service._send", fake_send)
    r = client.post("/api/v1/auth/forgot-password", json={"email": "TEST@mail.ru"})
    assert r.status_code == 200
    assert sent, "письмо сброса не ушло для почты в другом регистре"


def test_duplicates_by_case_are_not_guessed(db):
    a = _user(db, "dup@mail.ru")
    _user(db, "Dup@mail.ru")
    assert find_user_by_email(db, "dup@mail.ru").id == a.id      # точное совпадение
    assert find_user_by_email(db, "DUP@MAIL.RU") is None         # наугад не выбираем
