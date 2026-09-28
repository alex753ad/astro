"""Сброс пароля кодом (приложение, решение владельца 28.09.2026):
почта → код → новый пароль → вход, без браузера. Механизм кода — как при
регистрации (срок, попытки, пауза), ответ одинаков для существующей и
несуществующей почты."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.auth.router import MAX_OTP_ATTEMPTS, PWD_CODE_SENT

CODE_URL = "/api/v1/auth/password/reset-code"
VERIFY_URL = "/api/v1/auth/password/reset-verify"
NEW_PW = "NewPassword456!"


@pytest.fixture
def mail():
    sent = AsyncMock(return_value=True)
    with patch("backend.email_service.send_password_code_email", sent):
        yield sent


def _code(mail):
    # Код — второй аргумент подменённой отправки письма.
    return mail.await_args.args[1]


def test_same_answer_for_existing_and_unknown_email(client, user_free, mail):
    a = client.post(CODE_URL, json={"email": user_free.email})
    b = client.post(CODE_URL, json={"email": "nobody@mail.ru"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json() == {"message": PWD_CODE_SENT}
    assert mail.await_count == 1, "письмо ушло только существующему"


def test_resend_pause_same_for_both(client, user_free, mail):
    for email in (user_free.email, "nobody@mail.ru"):
        client.post(CODE_URL, json={"email": email})
        assert client.post(CODE_URL, json={"email": email}).status_code == 429


def test_code_resets_password_and_logs_in(client, db, user_free, mail, fake_redis):
    client.post(CODE_URL, json={"email": user_free.email.upper()})   # регистр не важен
    code = _code(mail)
    r = client.post(VERIFY_URL, json={"email": user_free.email, "code": code, "new_password": NEW_PW})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]
    assert client.post("/api/v1/auth/login", json={"email": user_free.email, "password": NEW_PW}).status_code == 200
    # Код одноразовый.
    again = client.post(VERIFY_URL, json={"email": user_free.email, "code": code, "new_password": NEW_PW})
    assert again.status_code == 400


def test_wrong_code_counts_attempts_like_registration(client, user_free, mail, fake_redis):
    client.post(CODE_URL, json={"email": user_free.email})
    for _ in range(MAX_OTP_ATTEMPTS):
        r = client.post(VERIFY_URL, json={"email": user_free.email, "code": "000000x"[:6], "new_password": NEW_PW})
        assert r.status_code == 400
    r = client.post(VERIFY_URL, json={"email": user_free.email, "code": "123456", "new_password": NEW_PW})
    assert "попыток" in r.json()["detail"] or "устарел" in r.json()["detail"]


def test_weak_password_does_not_burn_attempt(client, user_free, mail, fake_redis):
    client.post(CODE_URL, json={"email": user_free.email})
    code = _code(mail)
    assert client.post(VERIFY_URL, json={"email": user_free.email, "code": code, "new_password": "123"}).status_code == 400
    ok = client.post(VERIFY_URL, json={"email": user_free.email, "code": code, "new_password": NEW_PW})
    assert ok.status_code == 200


def test_unknown_email_verify_looks_like_expired(client):
    r = client.post(VERIFY_URL, json={"email": "nobody@mail.ru", "code": "123456", "new_password": NEW_PW})
    assert r.status_code == 400 and "устарел" in r.json()["detail"]
