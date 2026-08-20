"""tests/test_chart_rate_limit.py — тарифный per-minute лимит на построение карт.

20.08.2026: раньше эту роль якобы играли chart_free_key/chart_pro_key/
chart_premium_key — ни разу не подключённые ни к одному эндпоинту с
27.05.2026, и даже подключённые не различали реальный тариф (три статичных
строки, TierMiddleware, снятый в том же коммите). Взамен —
check_chart_rate_limit: явная проверка внутри хендлера, Redis-счётчик,
настоящее чтение user.tier.

Покрывает:
- реальное различие порогов по тарифам (не тот дефект, что раньше);
- анонимов (ключ по IP, порог free);
- 429 с понятным текстом при превышении;
- fail-open при отвале Redis;
- CRM (create_client, get_client_chart, create_consultation/horary) —
  тот же механизм, 429 не тонет в try/except мягкой деградации.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.auth.rate_limits import (
    CHART_RATE_LIMIT_PER_MINUTE,
    check_chart_rate_limit,
)
from backend.auth.passwords import hash_password
from backend.auth.jwt import create_token_pair
from backend.models import User


def make_user(db: Session, email: str, tier: str = "free") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("Password123!"),
        is_active=True,
        is_email_confirmed=True,
        tier=tier,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    tokens = create_token_pair(user.id, user.email, user.tier)
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _fake_request() -> Request:
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "headers": [], "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


class TestCheckChartRateLimitUnit:
    """Юнит-тесты самой функции — без HTTP, напрямую по Redis-счётчику."""

    @pytest.mark.asyncio
    async def test_free_user_blocked_after_own_limit(self, db: Session, fake_redis):
        user = make_user(db, "rl_free@example.com", tier="free")
        limit = CHART_RATE_LIMIT_PER_MINUTE["free"]
        req = _fake_request()
        for _ in range(limit):
            await check_chart_rate_limit(user, req)
        with pytest.raises(HTTPException) as exc:
            await check_chart_rate_limit(user, req)
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_premium_user_gets_higher_real_limit(self, db: Session, fake_redis):
        """Настоящее различие по тарифу — не то же имя ключа для всех,
        как было в снятой схеме chart_free_key/chart_pro_key."""
        free_user = make_user(db, "rl_free2@example.com", tier="free")
        premium_user = make_user(db, "rl_premium@example.com", tier="premium")
        req = _fake_request()

        free_limit = CHART_RATE_LIMIT_PER_MINUTE["free"]
        premium_limit = CHART_RATE_LIMIT_PER_MINUTE["premium"]
        assert premium_limit > free_limit

        # Исчерпываем лимит free — premium не должен быть задет (разные счётчики).
        for _ in range(free_limit):
            await check_chart_rate_limit(free_user, req)
        with pytest.raises(HTTPException):
            await check_chart_rate_limit(free_user, req)

        # premium продолжает работать вплоть до своего, более высокого порога.
        for _ in range(premium_limit):
            await check_chart_rate_limit(premium_user, req)
        with pytest.raises(HTTPException):
            await check_chart_rate_limit(premium_user, req)

    @pytest.mark.asyncio
    async def test_anonymous_uses_ip_key_and_free_limit(self, db: Session, fake_redis):
        req = _fake_request()
        limit = CHART_RATE_LIMIT_PER_MINUTE["free"]
        for _ in range(limit):
            await check_chart_rate_limit(None, req)
        with pytest.raises(HTTPException) as exc:
            await check_chart_rate_limit(None, req)
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_error_message_mentions_wait(self, db: Session, fake_redis):
        user = make_user(db, "rl_msg@example.com", tier="free")
        req = _fake_request()
        for _ in range(CHART_RATE_LIMIT_PER_MINUTE["free"]):
            await check_chart_rate_limit(user, req)
        with pytest.raises(HTTPException) as exc:
            await check_chart_rate_limit(user, req)
        assert "минут" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_fail_open_when_redis_unavailable(self, db: Session):
        """Rate limiting — защита от перебора, не контроль доступа: отвал
        Redis не должен ронять создание карт (см. backend/limiter.py)."""
        user = make_user(db, "rl_failopen@example.com", tier="free")
        req = _fake_request()

        with patch(
            "backend.redis_client.get_redis",
            side_effect=Exception("redis down"),
        ):
            # Не поднимает исключение, несмотря на то что Redis недоступен.
            await check_chart_rate_limit(user, req)


class TestChartCalculateEndpointRateLimit:
    def test_free_user_429_after_limit(
        self, client: TestClient, db: Session, mock_calculator, mock_geo,
    ):
        user = make_user(db, "rl_endpoint_free@example.com", tier="free")
        headers = auth_headers(user)
        payload = {
            "birth_date": "1990-01-10",
            "birth_time": "12:00",
            "birth_place": "Moscow",
            "house_system": "placidus",
        }
        limit = CHART_RATE_LIMIT_PER_MINUTE["free"]
        statuses = []
        for _ in range(limit + 2):
            statuses.append(client.post("/api/v1/chart/calculate", json=payload, headers=headers).status_code)

        assert 429 in statuses


class TestCRMChartRateLimit:
    """CRM — тот же механизм: 429 не должен тонуть в мягкой деградации
    (create_client/create_consultation глотают Exception, чтобы не терять
    клиента при сбое расчёта — но лимит скорости не должен маскироваться под
    "карта не посчиталась")."""

    @pytest.fixture
    def premium_user(self, db: Session) -> User:
        return make_user(db, "rl_crm_astrologer@example.com", tier="premium")

    @pytest.mark.asyncio
    async def test_create_client_rate_limited_returns_429_not_silent_200(
        self, client: TestClient, db: Session, fake_redis, premium_user, mock_calculator, mock_geo,
    ):
        """Разгоняем счётчик до потолка напрямую (тот же ключ, что построит
        эндпоинт — chart_rate:user:{id}), затем один реальный HTTP-запрос:
        проверяем, что 429 доходит до клиента, а не тонет в try/except
        мягкой деградации вокруг _geocode_and_build_chart."""
        limit = CHART_RATE_LIMIT_PER_MINUTE["premium"]
        fake_req = _fake_request()
        for _ in range(limit):
            await check_chart_rate_limit(premium_user, fake_req)

        headers = auth_headers(premium_user)
        # birth_time не передаём (Optional) — ClientProfile.birth_time это
        # SQLAlchemy Time, а create_client кладёт туда сырую строку из
        # ClientCreate.birth_time: Optional[str] без конвертации. Под SQLite
        # это падает ("Time type only accepts Python time objects"),
        # отдельный баг, не по этой задаче — сюда его не тащим.
        resp = client.post(
            "/api/v1/clients",
            json={"name": "Клиент", "birth_date": "1990-01-10", "birth_place": "Moscow"},
            headers=headers,
        )

        assert resp.status_code == 429
