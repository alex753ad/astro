"""Регрессия: GET /api/v1/admin/export падал на каждый вызов.

Роутер, который реально отвечает на этот путь (promo_router — регистрируется
в main.py раньше stats_router), делал raw SQL с колонкой `subscription_tier`,
которой в таблице users не существует (колонка называется `tier`), и держал
мёртвый импорт `from admin.admin_router import get_admin_stats` — модуля
`admin` без `backend.` не существует вовсе. Одноимённая рабочая версия в
stats_router.py была полностью экранирована порядком регистрации и никогда не
выполнялась (только рождала Duplicate Operation ID в OpenAPI).
"""

import pytest
from sqlalchemy import text

from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import User


@pytest.fixture
def promo_tables(db):
    """promo_codes/promo_usages не ORM-модели — их создаёт только Alembic
    (миграция 043_promo_codes), а тестовая SQLite-БД собирается из
    `Base.metadata.create_all()`, который их не видит. DDL здесь — упрощённый
    SQLite-совместимый подвид боевой схемы (без ARRAY, которого в SQLite нет),
    достаточный, чтобы прогнать сам роутер.
    """
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(32) UNIQUE NOT NULL,
            discount_type VARCHAR(10) NOT NULL,
            discount_value INTEGER NOT NULL,
            duration VARCHAR(20) NOT NULL,
            duration_months INTEGER,
            applies_to_plans TEXT,
            max_redemptions INTEGER,
            times_redeemed INTEGER NOT NULL DEFAULT 0,
            active BOOLEAN NOT NULL DEFAULT 1,
            expires_at DATETIME,
            created_at DATETIME
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS promo_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_code VARCHAR(32) NOT NULL,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            plan VARCHAR(20) NOT NULL,
            used_at DATETIME
        )
    """))
    db.commit()
    return db


@pytest.fixture
def admin_user(db):
    user = User(
        email="admin-export@example.com",
        hashed_password=hash_password("Password123!"),
        name="Admin",
        tier="premium",
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token(
        user_id=admin_user.id, email=admin_user.email, tier=admin_user.tier
    )
    return {"Authorization": f"Bearer {token}"}


class TestExportEndpointWorks:

    def test_admin_export_succeeds(self, client, admin_headers, promo_tables):
        resp = client.get("/api/v1/admin/export", headers=admin_headers)
        assert resp.status_code == 200

    def test_export_has_promo_router_shape(self, client, admin_headers, promo_tables, user_free):
        """Фронтенд (AdminPage.jsx) ждёт именно эту форму — users/gift_codes/promo_codes."""
        resp = client.get("/api/v1/admin/export", headers=admin_headers)
        body = resp.json()
        assert "users" in body
        assert "gift_codes" in body
        assert "promo_codes" in body
        assert any(u["id"] == user_free.id for u in body["users"])
        assert body["users"][0]["plan"] in ("free", "lite", "pro", "premium")

    def test_export_download_headers(self, client, admin_headers, promo_tables):
        resp = client.get("/api/v1/admin/export", headers=admin_headers)
        assert "attachment" in resp.headers.get("content-disposition", "")


class TestCouponsRouterHadNoTablesAtAll:
    """До миграции 043 промокоды не работали НИКАК — ни одна ручка, потому что
    promo_codes/promo_usages существовали только в TODO-комментарии.
    NOW() в create_promo/record_promo_usage — Postgres-специфичный SQL и на
    SQLite не пройдёт, поэтому здесь проверяются только чтения (list/stats),
    достаточные для регрессии на «таблицы наконец есть».
    """

    def test_list_promos_no_longer_500s(self, client, admin_headers, promo_tables):
        resp = client.get("/api/v1/admin/coupons", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_coupon_stats_no_longer_500s(self, client, admin_headers, promo_tables):
        resp = client.get("/api/v1/admin/coupons/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["list"] == []


class TestStatsEndpointStillWorks:
    """stats_router.get_stats — соседняя ручка, не должна была пострадать от правки."""

    def test_admin_stats_succeeds(self, client, admin_headers):
        resp = client.get("/api/v1/admin/stats", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "users" in body
        assert "recent_users" in body

    def test_recent_users_counts_present(self, client, admin_headers, user_free, created_chart):
        resp = client.get("/api/v1/admin/stats", headers=admin_headers)
        body = resp.json()
        row = next((u for u in body["recent_users"] if u["id"] == user_free.id), None)
        assert row is not None
        assert row["charts"] >= 1
