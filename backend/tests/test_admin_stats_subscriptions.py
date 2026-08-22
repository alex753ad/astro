"""Срок действия тарифа и анонимные карты в /api/v1/admin/stats.

До 22.08.2026 блок recent_users отдавал только users.tier — дату окончания
подписки не отдавал никто, ни в API, ни в интерфейсе. Отличить «оплачено до
21.09» от «платный тариф без срока, который tasks.expire_subscriptions не
понизит никогда» было нечем.

Ключевое требование к ответу: None в subscription_end неоднозначен, поэтому
рядом едет has_subscription — фронт по этой паре разводит пять состояний
(AdminPage.jsx:SubscriptionCell). Пустая ячейка в админке недопустима: два
состояния из пяти означают тариф, который не истечёт никогда.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import NatalChart, Subscription, User
from backend.time_utils import utcnow

STATS_URL = "/api/v1/admin/stats"


@pytest.fixture
def admin_headers(db):
    admin = User(
        email="admin-stats@example.com",
        hashed_password=hash_password("Password123!"),
        name="Admin", tier="premium", is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return {"Authorization": f"Bearer {create_access_token(
        user_id=admin.id, email=admin.email, tier=admin.tier)}"}


def _user(db, email, tier="free", pilot=False):
    u = User(
        email=email, hashed_password=hash_password("Password123!"),
        name=email, tier=tier,
        pilot_started_at=utcnow() if pilot else None,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _row(client, headers, email):
    resp = client.get(STATS_URL, headers=headers)
    assert resp.status_code == 200, resp.text
    rows = {r["email"]: r for r in resp.json()["recent_users"]}
    assert email in rows, f"{email} не попал в recent_users"
    return rows[email]


# ── Пять состояний срока действия ──────────────────────────

class TestSubscriptionEndStates:

    def test_active_subscription_reports_date(self, client, db, admin_headers):
        u = _user(db, "paid@example.com", tier="pro")
        end = utcnow() + timedelta(days=30)
        db.add(Subscription(user_id=u.id, stripe_price_id="pro_monthly",
                            status="active", tier="pro", current_period_end=end))
        db.commit()

        row = _row(client, admin_headers, "paid@example.com")
        assert row["has_subscription"] is True
        assert row["subscription_status"] == "active"
        assert row["subscription_end"] is not None
        assert row["subscription_end"].startswith(end.date().isoformat())

    def test_expired_subscription_still_reports_its_date(self, client, db, admin_headers):
        """Просроченная подписка обязана остаться видимой с датой — иначе
        непонятно, почему у человека упал тариф."""
        u = _user(db, "expired@example.com", tier="free")
        db.add(Subscription(user_id=u.id, stripe_price_id="pro_monthly",
                            status="expired", tier="free",
                            current_period_end=utcnow() - timedelta(days=3)))
        db.commit()

        row = _row(client, admin_headers, "expired@example.com")
        assert row["has_subscription"] is True
        assert row["subscription_status"] == "expired"
        assert row["subscription_end"] is not None

    def test_subscription_without_end_date_is_distinguishable(self, client, db, admin_headers):
        """Состояние «бессрочно ⚠»: строка есть, дата пустая.
        expire_subscriptions такие пропускает (current_period_end.isnot(None))."""
        u = _user(db, "endless@example.com", tier="pro")
        db.add(Subscription(user_id=u.id, stripe_price_id="pro_monthly",
                            status="active", tier="pro", current_period_end=None))
        db.commit()

        row = _row(client, admin_headers, "endless@example.com")
        assert row["has_subscription"] is True, \
            "без этого флага «нет строки» и «строка без даты» неразличимы"
        assert row["subscription_end"] is None

    def test_paid_tier_without_subscription_row_is_distinguishable(self, client, db, admin_headers):
        """Состояние «без подписки ⚠»: expire_subscriptions джойнит ОТ
        subscriptions, поэтому такого пользователя не найдёт никогда."""
        _user(db, "orphan@example.com", tier="pro")

        row = _row(client, admin_headers, "orphan@example.com")
        assert row["has_subscription"] is False
        assert row["subscription_end"] is None
        assert row["plan"] == "pro"

    def test_pilot_without_subscription(self, client, db, admin_headers):
        """У пилота подписки нет штатно — его понижает pilot/cron.py."""
        _user(db, "pilot@example.com", tier="premium", pilot=True)

        row = _row(client, admin_headers, "pilot@example.com")
        assert row["has_subscription"] is False
        assert row["is_pilot"] is True

    def test_free_user_without_subscription(self, client, db, admin_headers):
        _user(db, "plain@example.com", tier="free")

        row = _row(client, admin_headers, "plain@example.com")
        assert row["has_subscription"] is False
        assert row["is_pilot"] is False
        assert row["plan"] == "free"


class TestMultipleSubscriptions:
    """На subscriptions.user_id нет уникального индекса (наследство Stripe),
    так что строк на пользователя может быть больше одной. Админка обязана
    показывать ту же, что и остальной код, — самую позднюю."""

    def test_latest_period_end_wins(self, client, db, admin_headers):
        u = _user(db, "double@example.com", tier="pro")
        older = utcnow() + timedelta(days=5)
        newer = utcnow() + timedelta(days=40)
        db.add(Subscription(user_id=u.id, stripe_price_id="pro_monthly",
                            status="active", tier="pro", current_period_end=older))
        db.add(Subscription(user_id=u.id, stripe_price_id="pro_monthly",
                            status="active", tier="pro", current_period_end=newer))
        db.commit()

        row = _row(client, admin_headers, "double@example.com")
        assert row["subscription_end"].startswith(newer.date().isoformat())
