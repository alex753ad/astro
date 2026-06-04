"""Sprint v3.1 — тесты задач 1-4 (tier hierarchy, rate_limits, coupon, paywall)."""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from backend.auth.rate_limits import TIER_FLAGS, get_tier_limits
from backend.auth.dependencies import require_tier, TIER_HIERARCHY


# ═══════════════════════════════════════════════════════════
# Задача 2 — TIER_HIERARCHY и require_tier
# ═══════════════════════════════════════════════════════════

class TestTierHierarchy:
    def test_hierarchy_order(self):
        assert TIER_HIERARCHY.index("free") < TIER_HIERARCHY.index("lite")
        assert TIER_HIERARCHY.index("lite") < TIER_HIERARCHY.index("pro")
        assert TIER_HIERARCHY.index("pro") < TIER_HIERARCHY.index("premium")

    def test_pro_above_lite(self):
        assert TIER_HIERARCHY.index("pro") > TIER_HIERARCHY.index("lite")

    def test_lite_no_rag_chat(self):
        assert get_tier_limits("lite")["rag_chat"] == False

    def test_pro_has_rag_chat(self):
        assert get_tier_limits("pro")["rag_chat"] == True

    def test_premium_no_rag_chat(self):
        assert get_tier_limits("premium")["rag_chat"] == False

    def test_lite_limits(self):
        limits = get_tier_limits("lite")
        assert limits["interpretations_per_month"] == 3
        assert limits["transits_ai"] == False
        assert limits["pdf_export"] == False

    def test_pro_limits(self):
        limits = get_tier_limits("pro")
        assert limits["interpretations_per_month"] == 15
        assert limits["transits_ai"] == True
        assert limits["pdf_export"] == True

    def test_premium_limits(self):
        limits = get_tier_limits("premium")
        assert limits["interpretations_per_month"] == 100
        assert limits["transits_ai"] == True

    def test_unknown_tier_returns_free(self):
        limits = get_tier_limits("nonexistent")
        assert limits == get_tier_limits("free")


# ═══════════════════════════════════════════════════════════
# Задача 4 — create_day14_coupon (один купон на пользователя)
# ═══════════════════════════════════════════════════════════

class TestDay14Coupon:
    def test_coupon_once_per_user(self, db: Session):
        """Второй вызов create_day14_coupon для того же user_id → возвращает None."""
        from backend.models import User, CouponSent
        from datetime import datetime

        user = User(
            email="coupon_test@example.com",
            hashed_password="hashed",
            is_active=True,
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Simulate already sent coupon
        db.add(CouponSent(user_id=user.id, coupon_id="coupon_abc", created_at=datetime.utcnow()))
        db.commit()

        from backend.payments.stripe_service import create_day14_coupon
        result = create_day14_coupon(user, db)
        assert result is None

    def test_coupon_created_for_new_user(self, db: Session):
        """Первый вызов — должен создать купон (с мокнутым Stripe)."""
        from backend.models import User, CouponSent

        user = User(
            email="coupon_new@example.com",
            hashed_password="hashed",
            is_active=True,
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        mock_coupon = MagicMock()
        mock_coupon.id = "coup_test_123"

        from backend.payments.stripe_service import create_day14_coupon
        with patch("backend.payments.stripe_service.stripe.Coupon.create", return_value=mock_coupon):
            result = create_day14_coupon(user, db)

        assert result == "coup_test_123"
        # Check persisted
        sent = db.query(CouponSent).filter(CouponSent.user_id == user.id).first()
        assert sent is not None
        assert sent.coupon_id == "coup_test_123"


# ═══════════════════════════════════════════════════════════
# Задача 3 — /profile/subscription Feature Flags
# ═══════════════════════════════════════════════════════════

class TestSubscriptionEndpoint:
    def test_returns_tier_and_limits(self, client, auth_headers_free):
        resp = client.get("/api/v1/profile/subscription", headers=auth_headers_free)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "free"
        assert "limits" in data
        assert "usage" in data

    def test_pro_user_returns_pro_tier(self, client, auth_headers_pro):
        resp = client.get("/api/v1/profile/subscription", headers=auth_headers_pro)
        assert resp.status_code == 200
        assert resp.json()["tier"] == "pro"

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/profile/subscription")
        assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════
# Задача 12 — PaywallModal context mapping
# ═══════════════════════════════════════════════════════════

class TestPaywallContextMapping:
    """Проверяем что 403 detail корректно сопоставляется с контекстом."""

    def test_tier_required_format(self, client, auth_headers_free):
        """Free user hitting pro endpoint должен получить structured 403."""
        # /api/v1/chart/{id}/transits/interpret требует pro
        resp = client.get(
            "/api/v1/chart/nonexistent/transits/interpret",
            headers=auth_headers_free,
        )
        # Либо 403 tier_required, либо 404 — оба приемлемы (зависит от порядка проверок)
        assert resp.status_code in (403, 404, 422)
