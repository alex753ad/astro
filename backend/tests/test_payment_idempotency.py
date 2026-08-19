"""Регрессия M-1: повторная обработка одного и того же платежа не продлевает
подписку дважды.

Раньше защита от повтора жила только в Redis, и при его недоступности код шёл
по ветке fail-open (`first_time = True`) — перехваченный или просто повторно
отправленный вебхук с валидной подписью продлевал подписку сколько угодно раз.
Теперь источник истины — уникальный payment_id в таблице payment_events,
которая не зависит от состояния кэша.

Идемпотентность/комиссия/реферальная награда/активация — провайдер-независимая
логика (`backend.payments.common.process_payment`), тесты ниже бьют по ней
напрямую, а не через HTTP-роут конкретного провайдера. Исключение —
`TestRejectedWebhooksLeaveNoTrace`: она проверяет специфичные для Robokassa
вещи (подпись, сверка суммы), которые нарочно остались в payments_router.py
и process_payment не касаются.
"""

import pytest

from backend.models import PaymentEvent, Subscription, User
from backend.payments.common import DuplicatePayment, PaymentProcessingError, process_payment
from backend.payments.robokassa_service import TIER_PRICES


PATH = "/api/v1/payments/robokassa/result"


def _pay(db, user_id, payment_id="777001", tier="pro", period="monthly"):
    return process_payment(
        db, provider="robokassa", payment_id=payment_id,
        user_id=user_id, tier=tier, period=period,
        amount=TIER_PRICES[(tier, period)],
    )


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

    def test_first_call_activates(self, db, user_free):
        _pay(db, user_free.id)

        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "pro"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").count() == 1

    def test_replay_does_not_extend_subscription(self, db, user_free):
        _pay(db, user_free.id)
        db.expire_all()
        first_end = db.query(Subscription).filter(
            Subscription.user_id == user_free.id
        ).first().current_period_end

        # Тот же payment_id ещё трижды — так выглядит и ретрай провайдера,
        # и повтор перехваченного запроса.
        for _ in range(3):
            with pytest.raises(DuplicatePayment):
                _pay(db, user_free.id)

        db.expire_all()
        subs = db.query(Subscription).filter(Subscription.user_id == user_free.id).all()
        assert len(subs) == 1, "дубль создал вторую подписку"
        assert subs[0].current_period_end == first_end, "дубль продлил подписку"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").count() == 1

    def test_different_payment_id_is_processed(self, db, user_free):
        """Защита не должна глотать настоящий второй платёж."""
        _pay(db, user_free.id, payment_id="777001")
        _pay(db, user_free.id, payment_id="777002")

        db.expire_all()
        assert db.query(PaymentEvent).count() == 2


class TestAuditTrail:
    """Побочный, но важный эффект таблицы: платежи наконец где-то фиксируются."""

    def test_event_row_has_payment_details(self, db, user_free):
        _pay(db, user_free.id, tier="premium", period="monthly")
        db.expire_all()

        event = db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").first()
        assert event is not None
        assert event.provider == "robokassa"
        assert event.user_id == user_free.id
        assert event.tier == "premium"
        assert event.period == "monthly"
        assert event.amount == pytest.approx(TIER_PRICES[("premium", "monthly")])
        assert event.created_at is not None


class TestFailureIsSurfaced:
    """№12 (аудит от 09.08): валидный платёж, не превратившийся в подписку, не
    должен теряться в логе, который ротируется. process_payment поднимает
    PaymentProcessingError с указанием стадии сбоя в `.stage` — вызывающая
    сторона (роутер конкретного провайдера) превращает это в алерт живому
    человеку, см. payments_router._alert_payment_failure.
    """

    def test_activation_failure_raises_with_stage(self, db, user_free, monkeypatch):
        monkeypatch.setattr(
            "backend.payments.common.activate_subscription",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("БД моргнула")),
        )
        with pytest.raises(PaymentProcessingError) as exc_info:
            _pay(db, user_free.id)
        assert exc_info.value.stage == "activate_subscription"

    def test_payment_event_insert_failure_raises_with_stage(self, db, user_free, monkeypatch):
        def broken_flush():
            raise RuntimeError("БД моргнула на flush")

        monkeypatch.setattr(db, "flush", broken_flush)

        with pytest.raises(PaymentProcessingError) as exc_info:
            _pay(db, user_free.id)
        assert exc_info.value.stage == "payment_events insert"

    def test_successful_payment_does_not_raise(self, db, user_free):
        _pay(db, user_free.id)


class TestActivationFailureIsRetryable:
    """Запись о платеже и активация — одна транзакция.

    Если закоммитить payment_events отдельно и упасть на активации, повтор
    вебхука увидит существующий payment_id, ответит "OK" и уйдёт: деньги
    списаны, подписки нет, ретраи провайдера исчерпаны, автоматически починить
    нечем.
    """

    def test_failed_activation_leaves_nothing_behind(self, db, user_free, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("БД моргнула на активации")

        monkeypatch.setattr("backend.payments.common.activate_subscription", _boom)

        with pytest.raises(PaymentProcessingError):
            _pay(db, user_free.id)

        db.expire_all()
        assert db.query(PaymentEvent).count() == 0, "полуфабрикат остался и заблокирует ретрай"
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"

    def test_retry_after_failure_activates(self, db, user_free, monkeypatch):
        from backend.payments import common

        real_activate = common.activate_subscription
        fail_next = {"yes": True}

        def _flaky(**kwargs):
            if fail_next["yes"]:
                fail_next["yes"] = False
                raise RuntimeError("БД моргнула на активации")
            return real_activate(**kwargs)

        monkeypatch.setattr(common, "activate_subscription", _flaky)

        with pytest.raises(PaymentProcessingError):
            _pay(db, user_free.id)

        # Провайдер звонит повторно — на этот раз всё в порядке. Ничего не
        # осталось от первой попытки, значит это не дубль.
        _pay(db, user_free.id)

        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "pro"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id == "777001").count() == 1


class TestRejectedWebhooksLeaveNoTrace:
    """Специфичные для Robokassa проверки (подпись, сумма) — остаются в
    payments_router.py, process_payment их не касается. Проверяются через
    HTTP, а не process_payment.
    """

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
