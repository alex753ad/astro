"""Регрессия M-1: повторный вебхук Robokassa не продлевает подписку.

Раньше защита от повтора жила только в Redis, и при его недоступности код шёл
по ветке fail-open (`first_time = True`) — перехваченный или просто повторно
отправленный вебхук с валидной подписью продлевал подписку сколько угодно раз.
Теперь источник истины — уникальный inv_id в таблице payment_events, которая
не зависит от состояния кэша.
"""

from datetime import datetime, timedelta

import pytest

from backend.models import PaymentEvent, Subscription, User
from backend.payments.robokassa_service import TIER_PRICES


PATH = "/api/v1/payments/robokassa/result"


def _form(user_id, inv_id="777001", tier="pro", period="monthly"):
    return {
        "InvId": inv_id,
        "OutSum": f"{TIER_PRICES[(tier, period)]:.2f}",
        "SignatureValue": "ignored-verify-is-mocked",
        "Shp_user": user_id,
        "Shp_tier": tier,
        "Shp_period": period,
    }


@pytest.fixture
def valid_signature(monkeypatch):
    """Подпись проверяется отдельно (см. M-2) — здесь нас интересует повтор."""
    def _verify(form):
        return True, form.get("Shp_user", ""), form.get("Shp_tier", ""), form.get("Shp_period", "")

    monkeypatch.setattr("backend.payments.payments_router.verify_payment", _verify)
    return _verify


class TestDuplicateWebhook:

    def test_first_call_activates(self, client, db, user_free, valid_signature):
        resp = client.post(PATH, data=_form(user_free.id))
        assert resp.status_code == 200
        assert resp.text == "OK777001"

        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "pro"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").count() == 1

    def test_replay_does_not_extend_subscription(self, client, db, user_free, valid_signature):
        client.post(PATH, data=_form(user_free.id))
        db.expire_all()
        first_end = db.query(Subscription).filter(
            Subscription.user_id == user_free.id
        ).first().current_period_end

        # Тот же InvId ещё трижды — так выглядит и ретрай Robokassa, и повтор
        # перехваченного запроса.
        for _ in range(3):
            resp = client.post(PATH, data=_form(user_free.id))
            assert resp.status_code == 200
            assert resp.text == "OK777001"

        db.expire_all()
        subs = db.query(Subscription).filter(Subscription.user_id == user_free.id).all()
        assert len(subs) == 1, "дубль вебхука создал вторую подписку"
        assert subs[0].current_period_end == first_end, "дубль продлил подписку"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").count() == 1

    def test_different_inv_id_is_processed(self, client, db, user_free, valid_signature):
        """Защита не должна глотать настоящий второй платёж."""
        client.post(PATH, data=_form(user_free.id, inv_id="777001"))
        client.post(PATH, data=_form(user_free.id, inv_id="777002"))

        db.expire_all()
        assert db.query(PaymentEvent).count() == 2


class TestAuditTrail:
    """Побочный, но важный эффект таблицы: платежи наконец где-то фиксируются."""

    def test_event_row_has_payment_details(self, client, db, user_free, valid_signature):
        client.post(PATH, data=_form(user_free.id, tier="premium", period="monthly"))
        db.expire_all()

        event = db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").first()
        assert event is not None
        assert event.provider == "robokassa"
        assert event.user_id == user_free.id
        assert event.tier == "premium"
        assert event.period == "monthly"
        assert event.amount == pytest.approx(TIER_PRICES[("premium", "monthly")])
        assert event.created_at is not None


class TestFailureIsAlerted:
    """№12 (аудит от 09.08): валидный платёж, не превратившийся в подписку, не
    оставлял никакого следа, кроме строки в логе, который ротируется. Теперь
    оба сбойных пути (запись платежа, активация) шлют алерт в служебный
    Telegram-канал — тот же, что уже используется для отзывов.
    """

    def test_activation_failure_sends_alert(self, client, db, user_free, valid_signature, monkeypatch):
        sent = {}

        async def fake_send(text):
            sent["text"] = text
            return True

        monkeypatch.setattr("backend.payments.payments_router.send_support_message", fake_send)
        monkeypatch.setattr(
            "backend.payments.payments_router.activate_subscription",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("БД моргнула")),
        )

        resp = client.post(PATH, data=_form(user_free.id))
        assert resp.status_code == 500
        assert "activate_subscription" in sent.get("text", "")
        assert "777001" in sent["text"]

    def test_payment_event_insert_failure_sends_alert(self, client, db, user_free, valid_signature, monkeypatch):
        sent = {}

        async def fake_send(text):
            sent["text"] = text
            return True

        monkeypatch.setattr("backend.payments.payments_router.send_support_message", fake_send)

        def broken_flush():
            raise RuntimeError("БД моргнула на flush")

        monkeypatch.setattr(db, "flush", broken_flush)

        resp = client.post(PATH, data=_form(user_free.id))
        assert resp.status_code == 500
        assert "payment_events insert" in sent.get("text", "")

    def test_successful_payment_does_not_alert(self, client, db, user_free, valid_signature, monkeypatch):
        calls = []

        async def fake_send(text):
            calls.append(text)
            return True

        monkeypatch.setattr("backend.payments.payments_router.send_support_message", fake_send)

        resp = client.post(PATH, data=_form(user_free.id))
        assert resp.status_code == 200
        assert calls == []


class TestActivationFailureIsRetryable:
    """Запись о платеже и активация — одна транзакция.

    Если закоммитить payment_events отдельно и упасть на активации, повтор
    вебхука увидит существующий inv_id, ответит "OK" и уйдёт: деньги списаны,
    подписки нет, ретраи Robokassa исчерпаны, автоматически починить нечем.
    """

    def test_failed_activation_leaves_nothing_behind(self, client, db, user_free, valid_signature, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("БД моргнула на активации")

        monkeypatch.setattr(
            "backend.payments.payments_router.activate_subscription", _boom
        )
        resp = client.post(PATH, data=_form(user_free.id))
        assert resp.status_code == 500

        db.expire_all()
        assert db.query(PaymentEvent).count() == 0, "полуфабрикат остался и заблокирует ретрай"
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"

    def test_retry_after_failure_activates(self, client, db, user_free, valid_signature, monkeypatch):
        from backend.payments import payments_router

        real_activate = payments_router.activate_subscription
        fail_next = {"yes": True}

        def _flaky(**kwargs):
            if fail_next["yes"]:
                fail_next["yes"] = False
                raise RuntimeError("БД моргнула на активации")
            return real_activate(**kwargs)

        # Не monkeypatch.undo(): он снял бы и подмену verify_payment из фикстуры.
        monkeypatch.setattr(payments_router, "activate_subscription", _flaky)

        assert client.post(PATH, data=_form(user_free.id)).status_code == 500

        # Robokassa звонит повторно — на этот раз всё в порядке.
        resp = client.post(PATH, data=_form(user_free.id))
        assert resp.status_code == 200

        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "pro"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").count() == 1


class TestRejectedWebhooksLeaveNoTrace:

    def test_amount_mismatch_does_not_activate(self, client, db, user_free, valid_signature):
        form = _form(user_free.id)
        form["OutSum"] = "1.00"

        resp = client.post(PATH, data=form)
        assert resp.status_code == 400

        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"
        assert db.query(PaymentEvent).count() == 0

    def test_bad_signature_does_not_activate(self, client, db, user_free, monkeypatch):
        monkeypatch.setattr(
            "backend.payments.payments_router.verify_payment",
            lambda form: (False, "", "", ""),
        )
        resp = client.post(PATH, data=_form(user_free.id))
        assert resp.status_code == 400

        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"
        assert db.query(PaymentEvent).count() == 0
