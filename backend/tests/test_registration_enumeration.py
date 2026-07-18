"""Регрессия: форма регистрации не раскрывает существование аккаунта."""

from unittest.mock import AsyncMock, patch

import pytest


SEND_CODE = "/api/v1/auth/register/email/send-code"
NEW_EMAIL = "brand-new@yandex.ru"


def _payload(email):
    return {"email": email, "password": "Password123!", "name": "Test"}


@pytest.fixture
def existing_user(db):
    """Пользователь с адресом на разрешённом домене (схема пускает только их)."""
    from backend.auth.passwords import hash_password
    from backend.models import User

    user = User(
        email="taken@yandex.ru",
        hashed_password=hash_password("Password123!"),
        name="Existing",
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(autouse=True)
def no_outbound_email():
    """Письма не шлём — интересует только форма ответа."""
    with patch("backend.email_service.send_otp_email", new_callable=AsyncMock), \
         patch("backend.email_service._send", new_callable=AsyncMock):
        yield


class TestResponsesAreIndistinguishable:

    def test_existing_email_returns_200(self, client, existing_user):
        resp = client.post(SEND_CODE, json=_payload(existing_user.email))
        assert resp.status_code == 200

    def test_new_email_returns_200(self, client):
        resp = client.post(SEND_CODE, json=_payload(NEW_EMAIL))
        assert resp.status_code == 200

    def test_status_and_body_match(self, client, existing_user):
        """Главная проверка: ответы неотличимы."""
        existing = client.post(SEND_CODE, json=_payload(existing_user.email))
        new = client.post(SEND_CODE, json=_payload(NEW_EMAIL))

        assert existing.status_code == new.status_code
        assert existing.json() == new.json()

    def test_no_409_conflict(self, client, existing_user):
        """409 был прямым индикатором занятого адреса."""
        assert client.post(SEND_CODE, json=_payload(existing_user.email)).status_code != 409


class TestThrottleDoesNotLeak:

    def test_second_request_throttled_for_existing(self, client, existing_user):
        """Повтор по занятому адресу тоже упирается в троттлинг."""
        client.post(SEND_CODE, json=_payload(existing_user.email))
        second = client.post(SEND_CODE, json=_payload(existing_user.email))
        assert second.status_code == 429

    def test_second_request_throttled_for_new(self, client):
        client.post(SEND_CODE, json=_payload(NEW_EMAIL))
        second = client.post(SEND_CODE, json=_payload(NEW_EMAIL))
        assert second.status_code == 429

    def test_throttle_behaviour_matches(self, client, existing_user):
        """Утечка второго порядка: 429 должен вести себя одинаково."""
        client.post(SEND_CODE, json=_payload(existing_user.email))
        existing_second = client.post(SEND_CODE, json=_payload(existing_user.email))

        client.post(SEND_CODE, json=_payload(NEW_EMAIL))
        new_second = client.post(SEND_CODE, json=_payload(NEW_EMAIL))

        assert existing_second.status_code == new_second.status_code
        assert existing_second.json() == new_second.json()


class TestNoAccountCreatedForExisting:

    @pytest.mark.asyncio
    async def test_otp_not_stored_for_existing_email(self, client, existing_user, fake_redis):
        """Занятому адресу OTP не выдаётся — иначе им можно перехватить аккаунт."""
        from backend.auth.router import _otp_key

        client.post(SEND_CODE, json=_payload(existing_user.email))
        assert await fake_redis.get(_otp_key(existing_user.email)) is None

    @pytest.mark.asyncio
    async def test_otp_stored_for_new_email(self, client, fake_redis):
        from backend.auth.router import _otp_key

        client.post(SEND_CODE, json=_payload(NEW_EMAIL))
        assert await fake_redis.get(_otp_key(NEW_EMAIL)) is not None

    def test_verify_rejects_without_valid_code(self, client, existing_user):
        client.post(SEND_CODE, json=_payload(existing_user.email))
        resp = client.post(
            "/api/v1/auth/register/email/verify",
            json={"email": existing_user.email, "code": "000000"},
        )
        assert resp.status_code == 400
