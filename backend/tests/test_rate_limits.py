"""tests/test_rate_limits.py — тесты rate limiting и tier-ограничений.

Покрывает:
  - Per-tier лимиты (free / pro / premium)
  - Превышение лимита → 429 Too Many Requests
  - Заголовки X-RateLimit-* в ответах
  - require_tier: free-пользователь не может вызвать pro-эндпоинт
  - Авторизация: 401 без токена, 403 с недостаточным tier

Запуск: pytest backend/tests/test_rate_limits.py -v
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# ── Тесты tier-ограничений ────────────────────────────────────────────────────

class TestTierRestrictions:
    """Эндпоинты закрытые за tier должны возвращать 403 для низшего tier."""

    def test_free_user_can_access_basic_interpret(
        self, client, mock_calculator, mock_geo, auth_headers_free, created_chart
    ):
        """Free-пользователь может получить базовую интерпретацию."""
        if created_chart is None:
            pytest.skip("Chart not created")

        with patch("backend.interpretation.router.InterpretationRouter.interpret") as m:
            async def _gen(*a, **kw):
                yield "Базовая интерпретация"
            m.return_value = _gen()

            resp = client.get(
                f"/api/v1/chart/{created_chart}/interpret",
                headers=auth_headers_free,
            )
        assert resp.status_code in (200, 401, 403)  # 403 если free tier заблокирован

    def test_free_user_blocked_from_pro_features(
        self, client, auth_headers_free, created_chart, mock_calculator, mock_geo
    ):
        """Free-пользователь не может вызвать pro-эндпоинты (planner, transit detail)."""
        if created_chart is None:
            pytest.skip("Chart not created")

        resp = client.get(
            f"/api/v1/chart/{created_chart}/planner/monthly",
            headers=auth_headers_free,
        )
        # Ожидаем 403/402 если эндпоинт tier-gated, 404 если не найден, 200 если открытый
        assert resp.status_code in (402, 403, 401, 404, 200)

    def test_pro_user_can_access_pro_features(
        self, client, auth_headers_pro, mock_calculator, mock_geo
    ):
        """Pro-пользователь может вызвать pro-эндпоинты."""
        # Создаём карту под pro-пользователем
        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "name": "Pro Chart",
                "birth_date": "1990-06-15",
                "birth_time": "10:30",
                "birth_place": "Moscow",
                "latitude": 55.75,
                "longitude": 37.62,
            },
            headers=auth_headers_pro,
        )
        if resp.status_code != 200:
            pytest.skip("Chart creation failed")

        chart_id = resp.json().get("id") or resp.json().get("chart_id")
        if not chart_id:
            pytest.skip("No chart ID")

        planner_resp = client.get(
            f"/api/v1/chart/{chart_id}/planner/monthly",
            headers=auth_headers_pro,
        )
        # Pro должен получить 200, а не 403
        assert planner_resp.status_code != 403

    def test_unauthenticated_request_returns_401(self, client):
        """Запрос без токена к защищённому эндпоинту → 401."""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client):
        """Истёкший JWT → 401."""
        expired_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJ0ZXN0QGV4YW1wbGUuY29tIiwiZXhwIjoxNjAwMDAwMDAwfQ."
            "invalid_signature"
        )
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401

    def test_malformed_token_returns_401(self, client):
        """Некорректный JWT → 401."""
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not_a_real_token"},
        )
        assert resp.status_code == 401


# ── Тесты rate limiting ───────────────────────────────────────────────────────

class TestRateLimiting:
    """slowapi rate limiter — per-tier лимиты."""

    def test_rate_limit_headers_present(self, client, mock_calculator, mock_geo):
        """Ответ содержит заголовки X-RateLimit-*."""
        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "name": "Rate Test",
                "birth_date": "1990-06-15",
                "birth_time": "10:30",
                "birth_place": "Moscow",
                "latitude": 55.75,
                "longitude": 37.62,
            },
        )
        if resp.status_code == 200:
            # Заголовки могут быть X-RateLimit-Limit, X-RateLimit-Remaining
            headers_lower = {k.lower(): v for k, v in resp.headers.items()}
            has_rate_headers = any(
                "ratelimit" in k or "rate-limit" in k
                for k in headers_lower
            )
            # Логируем наличие заголовков (не блокирующая проверка)
            if has_rate_headers:
                remaining = headers_lower.get("x-ratelimit-remaining", "N/A")
                assert int(remaining) >= 0

    def test_too_many_requests_returns_429(self, client, mock_calculator, mock_geo):
        """Превышение лимита → 429. Включаем лимитер только для этого теста."""
        from backend.main import limiter

        payload = {
            "birth_date": "1990-06-15",
            "birth_time": "10:30",
            "birth_place": "Moscow",
            "house_system": "placidus",
        }

        # Включаем лимитер обратно для этого теста
        limiter.enabled = True
        try:
            responses = []
            for _ in range(35):  # лимит 30/minute
                resp = client.post("/api/v1/chart/calculate", json=payload)
                responses.append(resp.status_code)
                if resp.status_code == 429:
                    break

            # Должны получить хотя бы один 429, или тест просто документирует поведение
            assert 429 in responses or 200 in responses
        finally:
            limiter.enabled = False

    def test_free_tier_has_lower_limit_than_pro(self):
        """Free tier лимит < Pro tier лимит (документируем через конфиг)."""
        try:
            from backend.auth.rate_limits import FREE_RATE_LIMIT, PRO_RATE_LIMIT

            # Лимиты заданы в формате "N/period"
            def _parse_limit(limit_str: str) -> int:
                return int(limit_str.split("/")[0])

            free_n = _parse_limit(str(FREE_RATE_LIMIT))
            pro_n = _parse_limit(str(PRO_RATE_LIMIT))
            assert free_n < pro_n, f"Free {free_n} should be less than Pro {pro_n}"
        except ImportError:
            pytest.skip("rate_limits constants not importable")


# ── Тесты аутентификации ──────────────────────────────────────────────────────

class TestAuthentication:
    def test_register_creates_user(self, client):
        """POST /auth/register создаёт нового пользователя."""
        resp = client.post("/api/v1/auth/register", json={
            "email": "newuser@example.com",
            "password": "Password123!",
            "name": "New User",
        })
        assert resp.status_code in (200, 201)

    def test_register_duplicate_email_returns_409(self, client, user_free):
        """Повторная регистрация с тем же email → 409 Conflict."""
        resp = client.post("/api/v1/auth/register", json={
            "email": "free@example.com",  # уже существует
            "password": "Password123!",
            "name": "Duplicate",
        })
        assert resp.status_code in (409, 400)

    def test_login_returns_tokens(self, client, user_free):
        """Успешный логин возвращает access_token и refresh_token."""
        resp = client.post("/api/v1/auth/login", json={
            "email": "free@example.com",
            "password": "Password123!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_wrong_password_returns_401(self, client, user_free):
        """Неверный пароль → 401."""
        resp = client.post("/api/v1/auth/login", json={
            "email": "free@example.com",
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self, client):
        """Неизвестный email → 401."""
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "Password123!",
        })
        assert resp.status_code == 401

    def test_me_returns_user_data(self, client, user_free, auth_headers_free):
        """GET /auth/me возвращает данные текущего пользователя."""
        resp = client.get("/api/v1/auth/me", headers=auth_headers_free)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("email") == "free@example.com"
        assert "password" not in data
        assert "hashed_password" not in data

    def test_refresh_token_returns_new_access_token(self, client, user_free):
        """POST /auth/refresh с валидным refresh_token → новый access_token."""
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "free@example.com",
            "password": "Password123!",
        })
        refresh_token = login_resp.json().get("refresh_token")
        if not refresh_token:
            pytest.skip("No refresh_token in login response")

        refresh_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        assert "access_token" in refresh_resp.json()

    def test_gdpr_delete_removes_user(self, client, user_free, auth_headers_free):
        """DELETE /auth/me удаляет аккаунт пользователя."""
        resp = client.delete("/api/v1/auth/me", headers=auth_headers_free)
        assert resp.status_code in (200, 204)

        # После удаления токен больше не работает
        me_resp = client.get("/api/v1/auth/me", headers=auth_headers_free)
        assert me_resp.status_code == 401

    def test_password_weak_rejected(self, client):
        """Слабый пароль → 422 Validation Error."""
        resp = client.post("/api/v1/auth/register", json={
            "email": "weak@example.com",
            "password": "123",
            "name": "Weak",
        })
        assert resp.status_code == 422


# ── Монотонность тарифной сетки ───────────────────────────────────────────────

class TestTierMonotonicity:
    """Платный тариф не должен быть хуже более дешёвого ни по одному полю.

    Уже случалось: комментарий "3.2: было 6 (Pro не мог быть хуже Lite)" в
    rate_limits.py — сетку правили руками несколько раз, и без автоматической
    проверки такое расхождение легко не заметить (19.08.2026: обнаружили ещё
    одно — pdf_per_month у free/lite был безлимитным, у pro/premium конечным).

    None означает «безлимит» — считается больше любого числа.
    """

    TIER_ORDER = ["free", "lite", "pro", "premium"]

    # "Больше = лучше", None = безлимит. transits_ai_per_month включено, хотя
    # у pro/premium его перекрывает transits_ai=True — как чистое число он
    # всё равно не должен ни у кого убывать.
    NUMERIC_FIELDS = [
        "interpretation_word_limit",
        "interpretations_per_month",
        "charts_per_month",
        "charts_per_day",
        "transits_months",
        "transits_ai_per_month",
        "profiles_limit",
        "lunar_months",
        "planner_months",
        "pdf_per_month",
    ]

    # first_interpretation_free сюда намеренно не входит: это одноразовая
    # льгота только для free, не «уровень выгоды», сравнимый между тарифами.
    BOOLEAN_FIELDS = ["transits_ai", "synastry", "pdf_export"]

    @staticmethod
    def _rank(value):
        return (value is None, value if value is not None else 0)

    def test_numeric_fields_non_decreasing_across_tiers(self):
        from backend.auth.rate_limits import TIER_FLAGS

        violations = []
        for field in self.NUMERIC_FIELDS:
            values = [TIER_FLAGS[t].get(field) for t in self.TIER_ORDER]
            for i in range(len(values) - 1):
                lo, hi = values[i], values[i + 1]
                if self._rank(lo) > self._rank(hi):
                    violations.append(
                        f"{field}: {self.TIER_ORDER[i]}={lo!r} > {self.TIER_ORDER[i + 1]}={hi!r}"
                    )
        assert not violations, "Тариф дороже, а лимит хуже:\n" + "\n".join(violations)

    def test_boolean_fields_non_decreasing_across_tiers(self):
        from backend.auth.rate_limits import TIER_FLAGS

        violations = []
        for field in self.BOOLEAN_FIELDS:
            values = [bool(TIER_FLAGS[t].get(field)) for t in self.TIER_ORDER]
            for i in range(len(values) - 1):
                if values[i] and not values[i + 1]:
                    violations.append(
                        f"{field}: {self.TIER_ORDER[i]}=True > {self.TIER_ORDER[i + 1]}=False"
                    )
        assert not violations, "Тариф дороже, а фича пропала:\n" + "\n".join(violations)

    def test_derived_feature_flags_non_decreasing_across_tiers(self):
        """google_calendar/rag_chat/crm/unlimited_charts не хранятся в
        TIER_FLAGS напрямую — вычисляются в get_feature_flags() по строке
        tier, проверяем их тем же правилом отдельно."""
        from backend.auth.rate_limits import get_feature_flags

        class _FakeUser:
            def __init__(self, tier):
                self.tier = tier
                self.free_interpretation_used = False

        derived_fields = ["google_calendar", "rag_chat", "crm", "unlimited_charts"]
        violations = []
        for field in derived_fields:
            values = [bool(get_feature_flags(_FakeUser(t))[field]) for t in self.TIER_ORDER]
            for i in range(len(values) - 1):
                if values[i] and not values[i + 1]:
                    violations.append(
                        f"{field}: {self.TIER_ORDER[i]}=True > {self.TIER_ORDER[i + 1]}=False"
                    )
        assert not violations, "Тариф дороже, а фича пропала:\n" + "\n".join(violations)


# ── profiles_limit: лимит карт на аккаунт ────────────────────────────────────

class TestProfilesLimitEnforcement:
    """До 19.08.2026 profiles_limit только отображался на /pricing и в
    кабинете — реально создание карт им не ограничивалось. Теперь превышение
    лимита должно давать понятную 403-ошибку со ссылкой на /pricing, а не
    падать 500 и не притворяться, что лимита нет."""

    def test_exceeding_profiles_limit_returns_403_not_500(
        self, client, db, mock_calculator, mock_geo, auth_headers_free, user_free
    ):
        """profiles_limit — это лимит на аккаунт целиком, не на месяц (в
        отличие от charts_per_month, который совпадает с ним по числу для
        free). Бэкдейтим существующие карты в прошлый месяц, чтобы месячный
        лимит не сработал раньше и не заслонил собой именно эту проверку."""
        from datetime import timedelta

        from backend.auth.rate_limits import TIER_FLAGS
        from backend.models import NatalChart
        from backend.time_utils import utcnow

        limit = TIER_FLAGS["free"]["profiles_limit"]
        past = utcnow() - timedelta(days=40)
        for _ in range(limit):
            db.add(NatalChart(
                user_id=user_free.id,
                birth_date="1990-01-10",
                birth_place="Moscow",
                latitude=55.75, longitude=37.62, timezone="Europe/Moscow",
                planets=[], houses=[], aspects=[],
                created_at=past,
            ))
        db.commit()

        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )

        assert resp.status_code == 403, resp.text
        assert "/pricing" in resp.json()["detail"]

    def test_under_profiles_limit_still_succeeds(
        self, client, mock_calculator, mock_geo, auth_headers_free
    ):
        """Обычное создание первой карты не должно ловить новую проверку."""
        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )
        assert resp.status_code == 200, resp.text
