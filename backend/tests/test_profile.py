"""Tests for profile endpoints (Phase 4.3).

Validates:
- List saved charts (pagination, ownership)
- Delete chart (own chart, other user's chart, not found)
- Interpretation history
- Subscription info per tier
- GDPR data deletion
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import User, NatalChart, Subscription
from backend.auth.passwords import hash_password
from backend.auth.jwt import create_token_pair


# ── Helpers ───────────────────────────────────────────────

def make_user(db: Session, email: str, tier: str = "free") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("password123"),
        is_active=True,
        is_email_confirmed=True,
        tier=tier,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_chart(db: Session, user_id: str, birth_place: str = "Berlin") -> NatalChart:
    chart = NatalChart(
        user_id=user_id,
        birth_date="2000-01-15",
        birth_time="14:30",
        birth_place=birth_place,
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin",
        house_system="placidus",
        time_unknown=False,
        planets=[],
        houses=[],
        aspects=[],
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return chart


def auth_headers(user: User) -> dict:
    tokens = create_token_pair(user.id, user.email, user.tier)
    return {"Authorization": f"Bearer {tokens.access_token}"}


# ═══════════════════════════════════════════════════════════
# LIST CHARTS
# ═══════════════════════════════════════════════════════════

class TestListCharts:
    def test_returns_own_charts(self, client: TestClient, db: Session):
        user = make_user(db, "list_charts@example.com")
        make_chart(db, user.id, "Berlin")
        make_chart(db, user.id, "Paris")

        resp = client.get("/api/v1/profile/charts", headers=auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["charts"]) == 2

    def test_does_not_return_other_users_charts(self, client: TestClient, db: Session):
        user_a = make_user(db, "user_a@example.com")
        user_b = make_user(db, "user_b@example.com")
        make_chart(db, user_a.id)
        make_chart(db, user_b.id)

        resp = client.get("/api/v1/profile/charts", headers=auth_headers(user_a))
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_empty_charts_returns_empty_list(self, client: TestClient, db: Session):
        user = make_user(db, "no_charts@example.com")
        resp = client.get("/api/v1/profile/charts", headers=auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["charts"] == []

    def test_requires_auth(self, client: TestClient):
        resp = client.get("/api/v1/profile/charts")
        assert resp.status_code == 401

    def test_pagination_limit(self, client: TestClient, db: Session):
        user = make_user(db, "paginate@example.com")
        for i in range(5):
            make_chart(db, user.id, f"City{i}")

        resp = client.get(
            "/api/v1/profile/charts?limit=3&offset=0",
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["charts"]) == 3

    def test_pagination_offset(self, client: TestClient, db: Session):
        user = make_user(db, "paginate_offset@example.com")
        for i in range(5):
            make_chart(db, user.id, f"City{i}")

        resp = client.get(
            "/api/v1/profile/charts?limit=3&offset=3",
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        assert len(resp.json()["charts"]) == 2

    def test_chart_response_has_expected_fields(self, client: TestClient, db: Session):
        user = make_user(db, "fields_check@example.com")
        make_chart(db, user.id)

        resp = client.get("/api/v1/profile/charts", headers=auth_headers(user))
        chart = resp.json()["charts"][0]
        assert "id" in chart
        assert "birth_date" in chart
        assert "birth_place" in chart
        assert "house_system" in chart
        assert "time_unknown" in chart


# ═══════════════════════════════════════════════════════════
# DELETE CHART
# ═══════════════════════════════════════════════════════════

class TestDeleteChart:
    def test_delete_own_chart(self, client: TestClient, db: Session):
        user = make_user(db, "delete_chart@example.com")
        chart = make_chart(db, user.id)

        resp = client.delete(
            f"/api/v1/profile/charts/{chart.id}",
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

        deleted = db.query(NatalChart).filter(NatalChart.id == chart.id).first()
        assert deleted is None

    def test_cannot_delete_other_users_chart(self, client: TestClient, db: Session):
        owner = make_user(db, "chart_owner@example.com")
        attacker = make_user(db, "attacker@example.com")
        chart = make_chart(db, owner.id)

        resp = client.delete(
            f"/api/v1/profile/charts/{chart.id}",
            headers=auth_headers(attacker),
        )
        assert resp.status_code == 404  # Not found from attacker's perspective

        # Chart should still exist
        assert db.query(NatalChart).filter(NatalChart.id == chart.id).first() is not None

    def test_delete_nonexistent_chart(self, client: TestClient, db: Session):
        user = make_user(db, "del_nonexistent@example.com")
        resp = client.delete(
            "/api/v1/profile/charts/nonexistent-chart-id",
            headers=auth_headers(user),
        )
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client: TestClient, db: Session):
        user = make_user(db, "auth_delete@example.com")
        chart = make_chart(db, user.id)
        resp = client.delete(f"/api/v1/profile/charts/{chart.id}")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════
# INTERPRETATION HISTORY
# ═══════════════════════════════════════════════════════════

class TestInterpretationHistory:
    def test_history_returns_list(self, client: TestClient, db: Session):
        user = make_user(db, "history@example.com")
        resp = client.get("/api/v1/profile/history", headers=auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert "total" in data

    def test_history_requires_auth(self, client: TestClient):
        resp = client.get("/api/v1/profile/history")
        assert resp.status_code == 401

    def test_history_empty_for_new_user(self, client: TestClient, db: Session):
        user = make_user(db, "empty_history@example.com")
        resp = client.get("/api/v1/profile/history", headers=auth_headers(user))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION INFO
# ═══════════════════════════════════════════════════════════

class TestSubscriptionInfo:
    def test_free_user_has_correct_features(self, client: TestClient, db: Session):
        user = make_user(db, "free_sub@example.com", tier="free")
        resp = client.get("/api/v1/profile/subscription", headers=auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "free"
        assert data["features"]["transits"] is False
        assert data["features"]["unlimited_interpretations"] is False
        assert data["features"]["pdf_reports"] is False

    def test_pro_user_has_transits_enabled(self, client: TestClient, db: Session):
        user = make_user(db, "pro_sub@example.com", tier="pro")
        resp = client.get("/api/v1/profile/subscription", headers=auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "pro"
        assert data["features"]["transits"] is True
        assert data["features"]["unlimited_interpretations"] is True
        assert data["features"]["pdf_reports"] is False

    def test_premium_user_has_all_features(self, client: TestClient, db: Session):
        user = make_user(db, "premium_sub@example.com", tier="premium")
        resp = client.get("/api/v1/profile/subscription", headers=auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "premium"
        assert data["features"]["pdf_reports"] is True
        assert data["features"]["synastry"] is True

    def test_subscription_requires_auth(self, client: TestClient):
        resp = client.get("/api/v1/profile/subscription")
        assert resp.status_code == 401

    def test_active_subscription_reflected(self, client: TestClient, db: Session):
        user = make_user(db, "active_sub@example.com", tier="pro")
        sub = Subscription(
            user_id=user.id,
            stripe_subscription_id="sub_active",
            stripe_customer_id="cus_test",
            stripe_price_id="price_pro",
            status="active",
            tier="pro",
        )
        db.add(sub)
        db.commit()

        resp = client.get("/api/v1/profile/subscription", headers=auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["stripe_subscription_id"] == "sub_active"


# ═══════════════════════════════════════════════════════════
# GDPR — DELETE ALL DATA
# ═══════════════════════════════════════════════════════════

class TestGDPRDeleteData:
    def test_deletes_all_charts(self, client: TestClient, db: Session):
        user = make_user(db, "gdpr@example.com")
        make_chart(db, user.id, "Berlin")
        make_chart(db, user.id, "Tokyo")

        resp = client.delete("/api/v1/profile/data", headers=auth_headers(user))
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

        remaining = db.query(NatalChart).filter(NatalChart.user_id == user.id).count()
        assert remaining == 0

    def test_deletes_subscription_record(self, client: TestClient, db: Session):
        user = make_user(db, "gdpr_sub@example.com", tier="pro")
        sub = Subscription(
            user_id=user.id,
            stripe_subscription_id="sub_gdpr",
            stripe_customer_id="cus_gdpr",
            status="active",
            tier="pro",
        )
        db.add(sub)
        db.commit()

        client.delete("/api/v1/profile/data", headers=auth_headers(user))

        remaining_sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        assert remaining_sub is None

    def test_user_account_still_exists_after_data_deletion(self, client: TestClient, db: Session):
        """GDPR data delete removes content but keeps account (use /auth/me DELETE for full deletion)."""
        user = make_user(db, "gdpr_keep_account@example.com")
        client.delete("/api/v1/profile/data", headers=auth_headers(user))

        still_exists = db.query(User).filter(User.id == user.id).first()
        assert still_exists is not None

    def test_gdpr_requires_auth(self, client: TestClient):
        resp = client.delete("/api/v1/profile/data")
        assert resp.status_code == 401

    def test_does_not_delete_other_users_charts(self, client: TestClient, db: Session):
        user_a = make_user(db, "gdpr_a@example.com")
        user_b = make_user(db, "gdpr_b@example.com")
        chart_b = make_chart(db, user_b.id)

        client.delete("/api/v1/profile/data", headers=auth_headers(user_a))

        assert db.query(NatalChart).filter(NatalChart.id == chart_b.id).first() is not None
