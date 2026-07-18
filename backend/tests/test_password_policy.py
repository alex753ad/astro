"""Регрессия: единая политика паролей для регистрации и сброса."""

import pytest

from backend.auth.passwords import (
    BCRYPT_MAX_BYTES,
    hash_password,
    validate_password,
    verify_password,
)
from backend.auth.jwt import create_password_reset_token


class TestPolicyFunction:

    @pytest.mark.parametrize("password", [
        "1234567",        # 7 символов
        "short",
        "",
    ])
    def test_too_short_rejected(self, password):
        with pytest.raises(ValueError):
            validate_password(password)

    def test_exactly_min_length_accepted(self):
        assert validate_password("Abcd1234") == "Abcd1234"

    @pytest.mark.parametrize("password", [
        "12345678", "password", "qwerty123", "p@ssw0rd", "changeme",
    ])
    def test_common_passwords_rejected(self, password):
        with pytest.raises(ValueError):
            validate_password(password)

    def test_blocklist_is_case_insensitive(self):
        with pytest.raises(ValueError):
            validate_password("PassWord")

    def test_all_digits_rejected(self):
        with pytest.raises(ValueError):
            validate_password("9182736450")


class TestBcryptByteLimit:
    """bcrypt читает только первые 72 байта — длиннее принимать нельзя."""

    def test_exactly_72_bytes_accepted(self):
        password = "a" * BCRYPT_MAX_BYTES
        assert validate_password(password) == password

    def test_73_bytes_rejected(self):
        with pytest.raises(ValueError, match="слишком длинный"):
            validate_password("a" * (BCRYPT_MAX_BYTES + 1))

    def test_cyrillic_counted_in_bytes_not_chars(self):
        """37 кириллических символов — это 74 байта."""
        password = "п" * 37
        assert len(password) < BCRYPT_MAX_BYTES  # по символам проходит
        with pytest.raises(ValueError, match="слишком длинный"):
            validate_password(password)

    def test_cyrillic_within_limit_accepted(self):
        password = "п" * 36  # 72 байта ровно
        assert validate_password(password) == password

    def test_silent_truncation_would_have_collided(self):
        """Демонстрация проблемы: bcrypt не различает пароли за 72 байтом."""
        base = "a" * BCRYPT_MAX_BYTES
        hashed = hash_password(base)
        # Оба «пароля» совпали бы с хешем — поэтому длина и ограничена.
        assert verify_password(base + "XXXX", hashed)
        with pytest.raises(ValueError):
            validate_password(base + "XXXX")


class TestRegistrationEnforcesPolicy:

    def _send(self, client, password):
        return client.post(
            "/api/v1/auth/register/email/send-code",
            json={"email": "newbie@yandex.ru", "password": password, "name": "T"},
        )

    @pytest.mark.parametrize("password", ["short", "12345678", "password", "п" * 40])
    def test_weak_password_rejected(self, client, password):
        assert self._send(client, password).status_code == 422

    def test_strong_password_accepted(self, client):
        from unittest.mock import AsyncMock, patch

        with patch("backend.email_service.send_otp_email", new_callable=AsyncMock):
            assert self._send(client, "Str0ngPassphrase!").status_code == 200


class TestResetEnforcesSamePolicy:

    def _reset(self, client, user, password):
        token = create_password_reset_token(user.id, user.email)
        return client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": password},
        )

    @pytest.mark.parametrize("password", ["short", "123456789", "password", "п" * 40])
    def test_weak_password_rejected(self, client, user_free, password):
        """Раньше сброс проверял только длину и «только цифры»."""
        assert self._reset(client, user_free, password).status_code == 400

    def test_common_password_rejected(self, client, user_free):
        resp = self._reset(client, user_free, "qwerty123")
        assert resp.status_code == 400

    def test_overlong_password_rejected(self, client, user_free):
        resp = self._reset(client, user_free, "a" * 100)
        assert resp.status_code == 400

    def test_strong_password_accepted(self, client, user_free):
        assert self._reset(client, user_free, "Str0ngPassphrase!").status_code == 200
