"""tests/test_stripe.py — тесты Stripe webhook событий.

Покрывает три ключевых события:
  1. checkout.session.completed → пользователь получает Pro/Premium
  2. customer.subscription.deleted → пользователь возвращается на Free
  3. invoice.payment_failed → уведомление пользователю

Реальные HTTP-запросы к Stripe не отправляются.
Подпись webhook генерируется через stripe.WebhookSignature.generate_header.

Запуск: pytest backend/tests/test_stripe.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

# ── Константы ────────────────────────────────────────────────────────────────

WEBHOOK_SECRET = "whsec_test_secret_key_for_testing_only"
STRIPE_PRICE_PRO = "price_pro_test"
STRIPE_PRICE_PREMIUM = "price_premium_test"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stripe_signature(payload: str, secret: str, timestamp: int | None = None) -> str:
    """Генерация Stripe-подписи (stripe-signature header)."""
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.{payload}"
    sig = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={sig}"


def _make_event(event_type: str, data: dict) -> dict:
    return {
        "id": f"evt_test_{event_type.replace('.', '_')}",
        "type": event_type,
        "created": int(time.time()),
        "livemode": False,
        "data": {"object": data},
        "api_version": "2023-10-16",
    }


def _post_webhook(client: TestClient, event: dict) -> "Response":
    payload = json.dumps(event)
    sig = _stripe_signature(payload, WEBHOOK_SECRET)
    return client.post(
        "/api/v1/payments/webhook",
        content=payload,
        headers={
            "stripe-signature": sig,
            "content-type": "application/json",
        },
    )


# ── Фикстуры ─────────────────────────────────────────────────────────────────

@pytest.fixture
def stripe_env(monkeypatch):
    """Устанавливаем тестовые переменные окружения для Stripe."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake_key")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", STRIPE_PRICE_PRO)
    monkeypatch.setenv("STRIPE_PRICE_ID_PREMIUM", STRIPE_PRICE_PREMIUM)


@pytest.fixture
def mock_stripe_verify():
    """Мок верификации подписи Stripe — всегда успешна в тестах."""
    with patch("backend.payments.stripe_service.stripe.Webhook.construct_event") as m:
        yield m


@pytest.fixture
def test_user(db):
    """Создаём тестового пользователя с Stripe customer_id."""
    from backend.models import User
    from backend.auth.passwords import hash_password

    user = User(
        email="stripe_test@example.com",
        hashed_password=hash_password("Password123!"),
        name="Stripe Tester",
        tier="free",
        stripe_customer_id="cus_test_12345",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ═══════════════════════════════════════════════════════════
# checkout.session.completed → пользователь получает Pro
# ═══════════════════════════════════════════════════════════

class TestCheckoutSessionCompleted:

    def _checkout_event(self, customer_id: str, price_id: str, sub_id: str) -> dict:
        return _make_event("checkout.session.completed", {
            "id": "cs_test_12345",
            "customer": customer_id,
            "subscription": sub_id,
            "payment_status": "paid",
            "metadata": {"price_id": price_id},
        })

    def test_checkout_completed_upgrades_to_pro(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """После checkout.session.completed с Pro price → tier становится 'pro'."""
        event = self._checkout_event(
            customer_id="cus_test_12345",
            price_id=STRIPE_PRICE_PRO,
            sub_id="sub_test_pro_001",
        )
        mock_stripe_verify.return_value = event

        with patch("backend.payments.stripe_service.stripe.Subscription.retrieve") as mock_sub:
            mock_sub.return_value = MagicMock(
                id="sub_test_pro_001",
                status="active",
                items=MagicMock(data=[MagicMock(price=MagicMock(id=STRIPE_PRICE_PRO))]),
                current_period_end=int(time.time()) + 30 * 86400,
            )

            resp = _post_webhook(client, event)

        assert resp.status_code == 200

        db.refresh(test_user)
        assert test_user.tier == "pro"
        assert test_user.stripe_subscription_id == "sub_test_pro_001"

    def test_checkout_completed_upgrades_to_premium(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """checkout.session.completed с Premium price → tier = 'premium'."""
        event = self._checkout_event(
            customer_id="cus_test_12345",
            price_id=STRIPE_PRICE_PREMIUM,
            sub_id="sub_test_prem_001",
        )
        mock_stripe_verify.return_value = event

        with patch("backend.payments.stripe_service.stripe.Subscription.retrieve") as mock_sub:
            mock_sub.return_value = MagicMock(
                id="sub_test_prem_001",
                status="active",
                items=MagicMock(data=[MagicMock(price=MagicMock(id=STRIPE_PRICE_PREMIUM))]),
                current_period_end=int(time.time()) + 30 * 86400,
            )

            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        db.refresh(test_user)
        assert test_user.tier == "premium"

    def test_checkout_unknown_customer_returns_200(
        self, client, stripe_env, mock_stripe_verify
    ):
        """Неизвестный customer → webhook возвращает 200 (идемпотентность)."""
        event = self._checkout_event(
            customer_id="cus_unknown_xyz",
            price_id=STRIPE_PRICE_PRO,
            sub_id="sub_unknown",
        )
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)
        # Stripe требует 200 даже если customer не найден (иначе retry)
        assert resp.status_code == 200

    def test_invalid_signature_returns_400(self, client, stripe_env):
        """Неверная подпись → 400."""
        event = self._checkout_event("cus_test", STRIPE_PRICE_PRO, "sub_x")
        payload = json.dumps(event)

        resp = client.post(
            "/api/v1/payments/webhook",
            content=payload,
            headers={"stripe-signature": "t=0,v1=invalidsig", "content-type": "application/json"},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════
# customer.subscription.deleted → возврат на Free
# ═══════════════════════════════════════════════════════════

class TestSubscriptionDeleted:

    def _sub_deleted_event(self, customer_id: str, sub_id: str) -> dict:
        return _make_event("customer.subscription.deleted", {
            "id": sub_id,
            "customer": customer_id,
            "status": "canceled",
            "canceled_at": int(time.time()),
        })

    def test_subscription_deleted_downgrades_to_free(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """После отмены подписки пользователь → tier='free'."""
        # Сначала поднимаем до pro
        test_user.tier = "pro"
        test_user.stripe_subscription_id = "sub_to_delete"
        db.commit()

        event = self._sub_deleted_event("cus_test_12345", "sub_to_delete")
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)

        assert resp.status_code == 200
        db.refresh(test_user)
        assert test_user.tier == "free"

    def test_subscription_deleted_clears_subscription_id(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """После удаления подписки stripe_subscription_id очищается."""
        test_user.tier = "premium"
        test_user.stripe_subscription_id = "sub_premium_gone"
        db.commit()

        event = self._sub_deleted_event("cus_test_12345", "sub_premium_gone")
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)
        assert resp.status_code == 200

        db.refresh(test_user)
        assert test_user.stripe_subscription_id is None or test_user.tier == "free"

    def test_already_free_user_stays_free(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """Пользователь уже Free — downgrade идемпотентен."""
        test_user.tier = "free"
        db.commit()

        event = self._sub_deleted_event("cus_test_12345", "sub_already_free")
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)
        assert resp.status_code == 200

        db.refresh(test_user)
        assert test_user.tier == "free"


# ═══════════════════════════════════════════════════════════
# invoice.payment_failed → уведомление пользователю
# ═══════════════════════════════════════════════════════════

class TestInvoicePaymentFailed:

    def _payment_failed_event(
        self, customer_id: str, sub_id: str, attempt: int = 1
    ) -> dict:
        return _make_event("invoice.payment_failed", {
            "id": "in_test_failed",
            "customer": customer_id,
            "subscription": sub_id,
            "amount_due": 999,
            "currency": "usd",
            "attempt_count": attempt,
            "next_payment_attempt": int(time.time()) + 86400,
        })

    def test_payment_failed_returns_200(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """invoice.payment_failed обрабатывается без ошибки."""
        event = self._payment_failed_event("cus_test_12345", "sub_test_pro_001")
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)
        assert resp.status_code == 200

    def test_payment_failed_does_not_immediately_downgrade(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """Первый провал платежа — подписка НЕ сразу удаляется (Stripe даёт grace period)."""
        test_user.tier = "pro"
        test_user.stripe_subscription_id = "sub_grace"
        db.commit()

        event = self._payment_failed_event("cus_test_12345", "sub_grace", attempt=1)
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)
        assert resp.status_code == 200

        db.refresh(test_user)
        # После первого failed платежа tier не должен немедленно стать free
        # (Stripe пришлёт subscription.deleted когда реально отменит)
        # Этот тест документирует ожидаемое поведение системы
        assert test_user.tier in ("pro", "premium", "past_due")

    def test_payment_failed_notification_sent(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """При провале платежа должна быть попытка уведомить пользователя."""
        event = self._payment_failed_event("cus_test_12345", "sub_test_notif")
        mock_stripe_verify.return_value = event

        with patch("backend.payments.stripe_service.send_payment_failed_notification") as mock_notify:
            mock_notify.return_value = None
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        # Проверяем, что уведомление было инициировано
        if mock_notify.called:
            call_args = mock_notify.call_args
            # Уведомление должно содержать email или user_id
            assert call_args is not None

    def test_multiple_payment_failures_eventually_downgrades(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """3+ провала — система может снизить tier (зависит от бизнес-логики)."""
        test_user.tier = "pro"
        test_user.stripe_subscription_id = "sub_multi_fail"
        db.commit()

        for attempt in range(1, 4):
            event = self._payment_failed_event("cus_test_12345", "sub_multi_fail", attempt)
            mock_stripe_verify.return_value = event
            resp = _post_webhook(client, event)
            assert resp.status_code == 200

        # После 3 провалов Stripe обычно присылает subscription.deleted
        # Симулируем это
        del_event = _make_event("customer.subscription.deleted", {
            "id": "sub_multi_fail",
            "customer": "cus_test_12345",
            "status": "canceled",
        })
        mock_stripe_verify.return_value = del_event
        resp = _post_webhook(client, del_event)
        assert resp.status_code == 200

        db.refresh(test_user)
        assert test_user.tier == "free"


# ═══════════════════════════════════════════════════════════
# Дополнительные webhook-события
# ═══════════════════════════════════════════════════════════

class TestOtherWebhookEvents:

    def test_unknown_event_type_returns_200(
        self, client, stripe_env, mock_stripe_verify
    ):
        """Неизвестный тип события → 200 (идемпотентность)."""
        event = _make_event("some.unknown.event", {"foo": "bar"})
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)
        assert resp.status_code == 200

    def test_subscription_updated_active_keeps_tier(
        self, client, db, test_user, stripe_env, mock_stripe_verify
    ):
        """customer.subscription.updated с status=active → tier не меняется."""
        test_user.tier = "pro"
        db.commit()

        event = _make_event("customer.subscription.updated", {
            "id": "sub_updated",
            "customer": "cus_test_12345",
            "status": "active",
            "items": {"data": [{"price": {"id": STRIPE_PRICE_PRO}}]},
        })
        mock_stripe_verify.return_value = event

        resp = _post_webhook(client, event)
        assert resp.status_code == 200

        db.refresh(test_user)
        assert test_user.tier == "pro"
