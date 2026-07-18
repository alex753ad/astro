"""Регрессия: определение IP за прокси и блокировка перебора паролей."""

import pytest

from backend.limiter import client_ip


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    """Минимальная замена Request: нужны только client и headers."""

    def __init__(self, peer, forwarded=None):
        self.client = _FakeClient(peer) if peer else None
        self.headers = {"X-Forwarded-For": forwarded} if forwarded else {}


@pytest.fixture
def trusted(monkeypatch):
    """Доверяем 10.0.0.0/8."""
    import backend.limiter as lim
    import ipaddress

    monkeypatch.setattr(lim, "TRUSTED_PROXIES", [ipaddress.ip_network("10.0.0.0/8")])


@pytest.fixture
def untrusted(monkeypatch):
    """Список доверенных прокси пуст."""
    import backend.limiter as lim

    monkeypatch.setattr(lim, "TRUSTED_PROXIES", [])


class TestClientIpResolution:

    def test_direct_peer_used_when_no_proxies_trusted(self, untrusted):
        req = _FakeRequest("203.0.113.5")
        assert client_ip(req) == "203.0.113.5"

    def test_forwarded_header_ignored_from_untrusted_peer(self, untrusted):
        """Ключевой случай: клиент подделывает X-Forwarded-For."""
        req = _FakeRequest("203.0.113.5", forwarded="1.2.3.4")
        assert client_ip(req) == "203.0.113.5"

    def test_spoofed_header_cannot_change_key(self, untrusted):
        """Разные подделанные заголовки с одного адреса дают один ключ."""
        a = client_ip(_FakeRequest("203.0.113.5", forwarded="1.1.1.1"))
        b = client_ip(_FakeRequest("203.0.113.5", forwarded="2.2.2.2"))
        assert a == b == "203.0.113.5"

    def test_forwarded_used_from_trusted_proxy(self, trusted):
        req = _FakeRequest("10.0.0.1", forwarded="203.0.113.5")
        assert client_ip(req) == "203.0.113.5"

    def test_takes_rightmost_untrusted_hop(self, trusted):
        """Левые сегменты подделывает клиент — берём ближайший к прокси."""
        req = _FakeRequest("10.0.0.1", forwarded="1.2.3.4, 203.0.113.5, 10.0.0.2")
        assert client_ip(req) == "203.0.113.5"

    def test_spoofed_prefix_ignored(self, trusted):
        """Клиент дописал чужой IP слева — он не должен стать ключом."""
        req = _FakeRequest("10.0.0.1", forwarded="9.9.9.9, 203.0.113.5")
        assert client_ip(req) == "203.0.113.5"

    def test_all_hops_trusted_falls_back_to_peer(self, trusted):
        req = _FakeRequest("10.0.0.1", forwarded="10.0.0.2, 10.0.0.3")
        assert client_ip(req) == "10.0.0.1"

    def test_missing_client_is_handled(self, untrusted):
        assert client_ip(_FakeRequest(None)) == "unknown"


class TestLoginLockout:

    def _login(self, client, email, password):
        return client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )

    def test_wrong_password_returns_401(self, client, user_free):
        resp = self._login(client, user_free.email, "WrongPassword1!")
        assert resp.status_code == 401

    def test_locks_after_threshold(self, client, user_free):
        """После порога неудач — 429 вместо 401."""
        from backend.config import get_settings

        limit = get_settings().login_max_failures
        for _ in range(limit):
            self._login(client, user_free.email, "WrongPassword1!")

        resp = self._login(client, user_free.email, "WrongPassword1!")
        assert resp.status_code == 429

    def test_lock_survives_correct_password(self, client, user_free):
        """Заблокированный аккаунт не пускает даже с верным паролем."""
        from backend.config import get_settings

        for _ in range(get_settings().login_max_failures):
            self._login(client, user_free.email, "WrongPassword1!")

        resp = self._login(client, user_free.email, "Password123!")
        assert resp.status_code == 429

    def test_successful_login_resets_counter(self, client, user_free):
        from backend.config import get_settings

        limit = get_settings().login_max_failures
        for _ in range(limit - 1):
            self._login(client, user_free.email, "WrongPassword1!")

        assert self._login(client, user_free.email, "Password123!").status_code == 200

        # Счётчик обнулён — снова доступен полный лимит попыток.
        for _ in range(limit - 1):
            assert self._login(client, user_free.email, "WrongPassword1!").status_code == 401

    def test_lockout_is_per_account(self, client, user_free, user_pro):
        """Блокировка одного аккаунта не задевает другой."""
        from backend.config import get_settings

        for _ in range(get_settings().login_max_failures):
            self._login(client, user_free.email, "WrongPassword1!")

        assert self._login(client, user_pro.email, "Password123!").status_code == 200

    def test_unknown_email_also_counted(self, client):
        """Перебор по несуществующему адресу тоже упирается в лимит."""
        from backend.config import get_settings

        for _ in range(get_settings().login_max_failures):
            self._login(client, "nobody@example.com", "WrongPassword1!")

        resp = self._login(client, "nobody@example.com", "WrongPassword1!")
        assert resp.status_code == 429
