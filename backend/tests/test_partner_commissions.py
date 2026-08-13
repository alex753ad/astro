"""Тесты партнёрской программы (Этап 2): начисление и возврат комиссии.

credit_commission/refund_commission ничего не коммитят сами — коммит здесь
делает тест (как в проде — payments_router.robokassa_result).
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from backend.models import User, PaymentEvent, Partner, Commission
from backend.time_utils import utcnow
from backend.partners.commission import credit_commission, refund_commission, ATTRIBUTION_WINDOW_DAYS


def _make_user(db: Session, email: str, *, referred_by: str | None = None, created_at=None) -> User:
    user = User(
        email=email, hashed_password="hashed", is_active=True, is_email_confirmed=True,
        tier="free", referred_by=referred_by,
    )
    if created_at is not None:
        user.created_at = created_at
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_partner(db: Session, user: User, *, rate=0.10, status="active") -> Partner:
    partner = Partner(user_id=user.id, rate=rate, started_at=utcnow(), status=status)
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


def _make_payment(db: Session, buyer: User, *, amount=1990.0, created_at=None) -> PaymentEvent:
    pe = PaymentEvent(
        provider="robokassa", inv_id=f"inv-{buyer.id}-{amount}", user_id=buyer.id,
        tier="pro", period="monthly", amount=amount,
    )
    if created_at is not None:
        pe.created_at = created_at
    db.add(pe)
    db.flush()
    return pe


class TestCreditCommission:
    def test_creates_commission_for_active_partner_referrer(self, db: Session):
        referrer = _make_user(db, "referrer1@example.com")
        partner = _make_partner(db, referrer)
        buyer = _make_user(db, "buyer1@example.com", referred_by=referrer.id)
        payment = _make_payment(db, buyer, amount=1990.0)

        commission = credit_commission(db, payment, buyer)
        db.commit()

        assert commission is not None
        assert commission.partner_id == partner.id
        assert commission.payment_event_id == payment.id
        assert commission.rate == 0.10
        assert commission.amount == pytest.approx(199.0)
        assert commission.kind == "earned"

    def test_no_referrer_no_commission(self, db: Session):
        buyer = _make_user(db, "buyer2@example.com")
        payment = _make_payment(db, buyer)
        assert credit_commission(db, payment, buyer) is None

    def test_referrer_not_a_partner_no_commission(self, db: Session):
        referrer = _make_user(db, "referrer3@example.com")  # без Partner
        buyer = _make_user(db, "buyer3@example.com", referred_by=referrer.id)
        payment = _make_payment(db, buyer)
        assert credit_commission(db, payment, buyer) is None

    def test_paused_partner_no_commission(self, db: Session):
        referrer = _make_user(db, "referrer4@example.com")
        _make_partner(db, referrer, status="paused")
        buyer = _make_user(db, "buyer4@example.com", referred_by=referrer.id)
        payment = _make_payment(db, buyer)
        assert credit_commission(db, payment, buyer) is None

    def test_self_referral_guard(self, db: Session):
        referrer = _make_user(db, "referrer5@example.com")
        _make_partner(db, referrer)
        # Структурно невозможно (referred_by указывает на другого пользователя),
        # но buyer == партнёр должен быть отсечён защитной проверкой.
        payment = _make_payment(db, referrer)
        referrer.referred_by = referrer.id
        assert credit_commission(db, payment, referrer) is None

    def test_payment_within_attribution_window(self, db: Session):
        referrer = _make_user(db, "referrer6@example.com")
        _make_partner(db, referrer)
        joined = utcnow() - timedelta(days=ATTRIBUTION_WINDOW_DAYS - 1)
        buyer = _make_user(db, "buyer6@example.com", referred_by=referrer.id, created_at=joined)
        payment = _make_payment(db, buyer, created_at=utcnow())
        assert credit_commission(db, payment, buyer) is not None

    def test_payment_outside_attribution_window(self, db: Session):
        referrer = _make_user(db, "referrer7@example.com")
        _make_partner(db, referrer)
        joined = utcnow() - timedelta(days=ATTRIBUTION_WINDOW_DAYS + 1)
        buyer = _make_user(db, "buyer7@example.com", referred_by=referrer.id, created_at=joined)
        payment = _make_payment(db, buyer, created_at=utcnow())
        assert credit_commission(db, payment, buyer) is None


class TestRefundCommission:
    def test_creates_negative_adjustment(self, db: Session):
        referrer = _make_user(db, "referrer8@example.com")
        _make_partner(db, referrer)
        buyer = _make_user(db, "buyer8@example.com", referred_by=referrer.id)
        payment = _make_payment(db, buyer, amount=1990.0)
        original = credit_commission(db, payment, buyer)
        db.commit()

        adjustment = refund_commission(db, payment, note="возврат по просьбе клиента")
        db.commit()

        assert adjustment is not None
        assert adjustment.kind == "refund_adjustment"
        assert adjustment.amount == pytest.approx(-original.amount)
        assert adjustment.rate is None
        assert adjustment.partner_id == original.partner_id

    def test_idempotent_second_refund_returns_same_row(self, db: Session):
        referrer = _make_user(db, "referrer9@example.com")
        _make_partner(db, referrer)
        buyer = _make_user(db, "buyer9@example.com", referred_by=referrer.id)
        payment = _make_payment(db, buyer)
        credit_commission(db, payment, buyer)
        db.commit()

        first = refund_commission(db, payment)
        db.commit()
        second = refund_commission(db, payment)
        db.commit()

        assert first.id == second.id
        count = db.query(Commission).filter(
            Commission.payment_event_id == payment.id, Commission.kind == "refund_adjustment",
        ).count()
        assert count == 1

    def test_no_original_commission_nothing_to_refund(self, db: Session):
        buyer = _make_user(db, "buyer10@example.com")
        payment = _make_payment(db, buyer)  # без реферера — начисления не было
        assert refund_commission(db, payment) is None
