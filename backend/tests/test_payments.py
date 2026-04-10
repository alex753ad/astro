"""Tests for Stripe payment integration (Phase 4.2).

Validates:
- Checkout session creation
- Customer portal session
- Webhook: checkout.session.completed
- Webhook: customer.subscription.updated
- Webhook: invoice.payment_failed
- Tier mapping (price_id ↔ tier)
- Signature verification failure
"""

from __future__ import annotations

import json
import hashlib
import hmac
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import User, Subscription
from backend.payments.stripe_service import (
    get_or_create_customer,
    create_checkout_session,
    create_portal_session,
    handle_checkout_completed,
    handle_subscription_updated,
    handle_payment_failed,
    TIER_PRICE_MAP,
    PRICE_TIER_MAP,
)


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def free_user(db: Session) -> User:
    user = User(
        email="stripe_test@example.com",
        hashed_password="hashed",
        is_active=True,
        is_email_confirmed=True,
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_user(db: Session) -> User:
    user = User(
        email="pro_stripe@example.com",
        hashed_password="hashed",
        is_active=True,
        is_email_confirmed=True,
        tier="pro",
        stripe_customer_id="cus_existing123",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def mock_stripe_customer():
    customer = MagicMock()
    customer.id = "cus_new_mock123"
    return customer


@pytest.fixture
def mock_checkout_session():
    session = MagicMock()
    session.id = "cs_test_mock123"
    session.url = "https://checkout.stripe.com/pay/cs_test_mock123"
    return session


@pytest.fixture
def mock_portal_session():
    session = MagicMock()
    session.url = "https://billing.stripe.com/session/portal_mock123"
    return session


# ═══════════════════════════════════════════════════════════
# CUSTOMER MANAGEMENT
# ═══════════════════════════════════════════════════════════

class TestCustomerManagement:
    def test_returns_existing_customer_id(self, pro_user, db):
        """Should not create new customer if one already exists."""
        with patch("backend.payments.stripe_service.stripe.Customer.create") as mock_create:
            customer_id = get_or_create_customer(pro_user, db)
            mock_create.assert_not_called()
            assert customer_id == "cus_existing123"

    def test_creates_new_customer_for_free_user(self, free_user, db, mock_stripe_customer):
        """Should create Stripe customer and persist ID for new user."""
        with patch(
            "backend.payments.stripe_service.stripe.Customer.create",
            return_value=mock_stripe_customer,
        ):
            customer_id = get_or_create_customer(free_user, db)
            assert customer_id == "cus_new_mock123"
            # Should be persisted to DB
            db.refresh(free_user)
            assert free_user.stripe_customer_id == "cus_new_mock123"

    def test_customer_created_with_correct_metadata(self, free_user, db, mock_stripe_customer):
        """Stripe customer creation should include user_id in metadata."""
        with patch(
            "backend.payments.stripe_service.stripe.Customer.create",
            return_value=mock_stripe_customer,
        ) as mock_create:
            get_or_create_customer(free_user, db)
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["email"] == free_user.email
            assert call_kwargs["metadata"]["user_id"] == free_user.id


# ═══════════════════════════════════════════════════════════
# CHECKOUT SESSION
# ═══════════════════════════════════════════════════════════

class TestCheckoutSession:
    def test_creates_session_for_pro_tier(self, free_user, db, mock_stripe_customer, mock_checkout_session):
        """Should return checkout URL for pro tier."""
        with patch("backend.payments.stripe_service.stripe.Customer.create", return_value=mock_stripe_customer), \
             patch("backend.payments.stripe_service.stripe.checkout.Session.create", return_value=mock_checkout_session):
            url = create_checkout_session(
                user=free_user,
                tier="pro",
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
                db=db,
            )
            assert url == mock_checkout_session.url

    def test_creates_session_for_premium_tier(self, free_user, db, mock_stripe_customer, mock_checkout_session):
        """Should accept premium tier."""
        with patch("backend.payments.stripe_service.stripe.Customer.create", return_value=mock_stripe_customer), \
             patch("backend.payments.stripe_service.stripe.checkout.Session.create", return_value=mock_checkout_session):
            url = create_checkout_session(
                user=free_user,
                tier="premium",
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
                db=db,
            )
            assert url is not None

    def test_unknown_tier_raises(self, free_user, db):
        """Unknown tier should raise ValueError before calling Stripe."""
        with pytest.raises(ValueError, match="Unknown tier"):
            create_checkout_session(
                user=free_user,
                tier="ultra",
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
                db=db,
            )

    def test_session_uses_subscription_mode(self, free_user, db, mock_stripe_customer, mock_checkout_session):
        """Session must be created in subscription mode."""
        with patch("backend.payments.stripe_service.stripe.Customer.create", return_value=mock_stripe_customer), \
             patch("backend.payments.stripe_service.stripe.checkout.Session.create", return_value=mock_checkout_session) as mock_create:
            create_checkout_session(
                user=free_user,
                tier="pro",
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
                db=db,
            )
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["mode"] == "subscription"
            assert call_kwargs["metadata"]["user_id"] == free_user.id
            assert call_kwargs["metadata"]["tier"] == "pro"


# ═══════════════════════════════════════════════════════════
# CUSTOMER PORTAL
# ═══════════════════════════════════════════════════════════

class TestPortalSession:
    def test_creates_portal_session(self, pro_user, db, mock_portal_session):
        """Should return portal URL for existing Stripe customer."""
        with patch(
            "backend.payments.stripe_service.stripe.billing_portal.Session.create",
            return_value=mock_portal_session,
        ):
            url = create_portal_session(
                user=pro_user,
                return_url="https://app.example.com/profile",
                db=db,
            )
            assert url == mock_portal_session.url

    def test_portal_uses_correct_customer(self, pro_user, db, mock_portal_session):
        """Portal session should use the user's Stripe customer ID."""
        with patch(
            "backend.payments.stripe_service.stripe.billing_portal.Session.create",
            return_value=mock_portal_session,
        ) as mock_create:
            create_portal_session(pro_user, "https://app.example.com/profile", db)
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["customer"] == "cus_existing123"


# ═══════════════════════════════════════════════════════════
# WEBHOOK: checkout.session.completed
# ═══════════════════════════════════════════════════════════

class TestWebhookCheckoutCompleted:
    def test_activates_subscription_and_upgrades_tier(self, free_user, db):
        """Successful checkout should upgrade user tier and create subscription."""
        event = {
            "data": {
                "object": {
                    "metadata": {"user_id": free_user.id, "tier": "pro"},
                    "subscription": "sub_mock123",
                    "customer": "cus_mock123",
                }
            }
        }
        handle_checkout_completed(event, db)

        db.refresh(free_user)
        assert free_user.tier == "pro"
        assert free_user.stripe_customer_id == "cus_mock123"

        sub = db.query(Subscription).filter(Subscription.user_id == free_user.id).first()
        assert sub is not None
        assert sub.status == "active"
        assert sub.tier == "pro"
        assert sub.stripe_subscription_id == "sub_mock123"

    def test_missing_user_id_does_not_crash(self, db):
        """Event without user_id in metadata should log warning but not crash."""
        event = {
            "data": {
                "object": {
                    "metadata": {},  # no user_id
                    "subscription": "sub_mock",
                    "customer": "cus_mock",
                }
            }
        }
        # Should not raise
        handle_checkout_completed(event, db)

    def test_unknown_user_id_does_not_crash(self, db):
        """Event with non-existent user_id should log error but not crash."""
        event = {
            "data": {
                "object": {
                    "metadata": {"user_id": "non-existent-id", "tier": "pro"},
                    "subscription": "sub_mock",
                    "customer": "cus_mock",
                }
            }
        }
        handle_checkout_completed(event, db)

    def test_updates_existing_subscription(self, free_user, db):
        """If subscription already exists, it should be updated not duplicated."""
        # Create existing sub record
        existing_sub = Subscription(
            user_id=free_user.id,
            stripe_subscription_id="sub_old",
            stripe_customer_id="cus_old",
            status="active",
            tier="pro",
        )
        db.add(existing_sub)
        db.commit()

        event = {
            "data": {
                "object": {
                    "metadata": {"user_id": free_user.id, "tier": "pro"},
                    "subscription": "sub_new123",
                    "customer": "cus_new123",
                }
            }
        }
        handle_checkout_completed(event, db)

        subs = db.query(Subscription).filter(Subscription.user_id == free_user.id).all()
        assert len(subs) == 1  # no duplicate
        assert subs[0].stripe_subscription_id == "sub_new123"


# ═══════════════════════════════════════════════════════════
# WEBHOOK: customer.subscription.updated
# ═══════════════════════════════════════════════════════════

class TestWebhookSubscriptionUpdated:
    def _make_sub_event(self, subscription_id: str, status: str, price_id: str, user_id: str) -> dict:
        return {
            "data": {
                "object": {
                    "id": subscription_id,
                    "status": status,
                    "metadata": {"user_id": user_id},
                    "items": {
                        "data": [{"price": {"id": price_id}}]
                    },
                }
            }
        }

    def test_cancellation_downgrades_to_free(self, free_user, db):
        """Canceled subscription should downgrade user to free tier."""
        # Setup existing subscription
        sub = Subscription(
            user_id=free_user.id,
            stripe_subscription_id="sub_cancel_test",
            stripe_customer_id="cus_mock",
            status="active",
            tier="pro",
        )
        db.add(sub)
        free_user.tier = "pro"
        db.commit()

        price_id = list(TIER_PRICE_MAP.values())[0] or "price_pro_test"
        event = self._make_sub_event("sub_cancel_test", "canceled", price_id, free_user.id)
        handle_subscription_updated(event, db)

        db.refresh(free_user)
        assert free_user.tier == "free"

    def test_active_subscription_keeps_tier(self, free_user, db):
        """Active subscription update should maintain pro/premium tier."""
        price_id = list(TIER_PRICE_MAP.values())[0] or "price_pro_test"
        sub = Subscription(
            user_id=free_user.id,
            stripe_subscription_id="sub_active_test",
            stripe_customer_id="cus_mock",
            status="active",
            tier="pro",
            stripe_price_id=price_id,
        )
        db.add(sub)
        db.commit()

        event = self._make_sub_event("sub_active_test", "active", price_id, free_user.id)
        handle_subscription_updated(event, db)

        db.refresh(sub)
        assert sub.status == "active"

    def test_past_due_downgrades_user(self, free_user, db):
        """past_due status should downgrade user to free."""
        sub = Subscription(
            user_id=free_user.id,
            stripe_subscription_id="sub_pastdue",
            stripe_customer_id="cus_mock",
            status="active",
            tier="pro",
        )
        db.add(sub)
        free_user.tier = "pro"
        db.commit()

        event = self._make_sub_event("sub_pastdue", "past_due", "price_unknown", free_user.id)
        handle_subscription_updated(event, db)

        db.refresh(free_user)
        assert free_user.tier == "free"

    def test_unknown_subscription_id_does_not_crash(self, db):
        """Unknown subscription ID should log warning but not crash."""
        event = self._make_sub_event("sub_unknown", "canceled", "price_x", "user_x")
        handle_subscription_updated(event, db)


# ═══════════════════════════════════════════════════════════
# WEBHOOK: invoice.payment_failed
# ═══════════════════════════════════════════════════════════

class TestWebhookPaymentFailed:
    def test_payment_failed_logs_without_downgrade(self, pro_user, db):
        """Payment failure should log but NOT immediately downgrade (Stripe retries)."""
        event = {
            "data": {
                "object": {
                    "customer": pro_user.stripe_customer_id,
                    "subscription": "sub_mock",
                }
            }
        }
        handle_payment_failed(event, db)

        # User should still be pro — Stripe handles dunning
        db.refresh(pro_user)
        assert pro_user.tier == "pro"

    def test_payment_failed_unknown_customer_does_not_crash(self, db):
        """Unknown customer in payment failure should not crash."""
        event = {
            "data": {
                "object": {
                    "customer": "cus_unknown_123",
                    "subscription": "sub_mock",
                }
            }
        }
        handle_payment_failed(event, db)


# ═══════════════════════════════════════════════════════════
# TIER / PRICE MAPPING
# ═══════════════════════════════════════════════════════════

class TestTierMapping:
    def test_tier_price_map_has_pro_and_premium(self):
        assert "pro" in TIER_PRICE_MAP
        assert "premium" in TIER_PRICE_MAP

    def test_price_tier_map_is_inverse(self):
        """PRICE_TIER_MAP should be the inverse of TIER_PRICE_MAP."""
        for tier, price_id in TIER_PRICE_MAP.items():
            if price_id:  # skip empty placeholders
                assert PRICE_TIER_MAP.get(price_id) == tier


# ═══════════════════════════════════════════════════════════
# API ENDPOINT TESTS (via TestClient)
# ═══════════════════════════════════════════════════════════

class TestPaymentsEndpoints:
    """Integration tests for /api/v1/payments/* endpoints."""

    def test_checkout_requires_auth(self, client: TestClient):
        resp = client.post("/api/v1/payments/checkout", json={"tier": "pro"})
        assert resp.status_code == 401

    def test_portal_requires_auth(self, client: TestClient):
        resp = client.post("/api/v1/payments/portal")
        assert resp.status_code == 401

    def test_webhook_without_signature_rejected(self, client: TestClient):
        """Stripe webhook without valid signature should return 400."""
        payload = json.dumps({"type": "checkout.session.completed"})
        resp = client.post(
            "/api/v1/payments/webhook",
            content=payload,
            headers={"Content-Type": "application/json"},
            # No stripe-signature header
        )
        # Either 400 (bad signature) or 422 (missing header) is acceptable
        assert resp.status_code in (400, 422)

    def test_webhook_with_invalid_signature_rejected(self, client: TestClient):
        """Stripe webhook with wrong signature should be rejected."""
        payload = json.dumps({"type": "checkout.session.completed"})
        resp = client.post(
            "/api/v1/payments/webhook",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=123,v1=invalidsignature",
            },
        )
        assert resp.status_code in (400, 422)
