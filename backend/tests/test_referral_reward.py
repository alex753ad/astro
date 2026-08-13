"""«Пригласи друга — 2 недели Pro за друга» под Robokassa.

Раньше награда шла только через Stripe Coupon (stripe_service.apply_referral_reward),
который требует referrer.stripe_customer_id — у Robokassa-плательщиков его
никогда нет, награда молча не срабатывала. Теперь — прямое продление
current_period_end (backend/payments/robokassa_service.apply_referral_reward),
только для рефереров с уже активной платной подпиской (решение владельца:
free-рефереры бонус не получают, чтобы не заводить отдельный джоб отзыва
временного pro — см. docstring функции).
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from backend.models import User, Subscription, Partner, Commission, PaymentEvent
from backend.payments.robokassa_service import apply_referral_reward, REFERRAL_REWARD_DAYS, TIER_PRICES
from backend.time_utils import utcnow


def _user(db: Session, email: str, *, tier="free", referred_by=None) -> User:
    user = User(
        email=email, hashed_password="hashed", is_active=True, is_email_confirmed=True,
        tier=tier, referred_by=referred_by,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _subscription(db: Session, user: User, *, status="active", current_period_end=None) -> Subscription:
    sub = Subscription(
        user_id=user.id, stripe_price_id=f"{user.tier}_monthly",
        status=status, tier=user.tier, current_period_end=current_period_end,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _close(a, b, tol=timedelta(seconds=5)) -> bool:
    """pytest.approx() не умеет надёжно сравнивать datetime с abs=timedelta —
    падает даже на разнице в микросекунды (проверено эмпирически)."""
    return abs(a - b) <= tol


class TestApplyReferralReward:
    def test_extends_active_paid_subscription(self, db: Session):
        referrer = _user(db, "referrer_paid@example.com", tier="pro")
        end = utcnow() + timedelta(days=10)
        sub = _subscription(db, referrer, current_period_end=end)

        apply_referral_reward(referrer.id, db)
        db.commit()

        db.refresh(sub)
        assert _close(sub.current_period_end, end + timedelta(days=REFERRAL_REWARD_DAYS))

    def test_free_tier_referrer_gets_nothing(self, db: Session):
        referrer = _user(db, "referrer_free@example.com", tier="free")
        apply_referral_reward(referrer.id, db)
        db.commit()
        assert db.query(Subscription).filter(Subscription.user_id == referrer.id).count() == 0

    def test_no_subscription_row_is_noop(self, db: Session):
        referrer = _user(db, "referrer_nosub@example.com", tier="pro")  # tier выставлен, Subscription нет
        apply_referral_reward(referrer.id, db)  # не должно упасть
        db.commit()
        assert db.query(Subscription).count() == 0

    def test_inactive_subscription_gets_nothing(self, db: Session):
        referrer = _user(db, "referrer_canceled@example.com", tier="pro")
        end = utcnow() + timedelta(days=5)
        sub = _subscription(db, referrer, status="canceled", current_period_end=end)
        apply_referral_reward(referrer.id, db)
        db.commit()
        db.refresh(sub)
        assert _close(sub.current_period_end, end)

    def test_unknown_referrer_is_noop(self, db: Session):
        apply_referral_reward("does-not-exist", db)  # не должно упасть

    def test_already_expired_period_extends_from_now_not_from_stale_date(self, db: Session):
        referrer = _user(db, "referrer_expired@example.com", tier="pro")
        stale_end = utcnow() - timedelta(days=40)  # подписка формально активна, но дата в прошлом
        sub = _subscription(db, referrer, current_period_end=stale_end)

        apply_referral_reward(referrer.id, db)
        db.commit()

        db.refresh(sub)
        # Не 40 дней в минусе + 14, а от текущего момента + 14
        assert sub.current_period_end > utcnow() + timedelta(days=REFERRAL_REWARD_DAYS - 1)

    def test_does_not_commit_itself(self, db: Session):
        """credit_commission-style контракт: коммитит вызывающая сторона."""
        referrer = _user(db, "referrer_nocommit@example.com", tier="pro")
        end = utcnow() + timedelta(days=5)
        sub = _subscription(db, referrer, current_period_end=end)
        apply_referral_reward(referrer.id, db)
        db.rollback()
        db.refresh(sub)
        assert _close(sub.current_period_end, end)


class TestRewardVsCommissionMutualExclusivity:
    """Партнёрская программа и обычная реферальная награда не должны
    срабатывать одновременно для одного реферера — payments_router.py.
    """

    PATH = "/api/v1/payments/robokassa/result"

    @staticmethod
    def _form(user_id, inv_id, tier="pro", period="monthly"):
        return {
            "InvId": inv_id,
            "OutSum": f"{TIER_PRICES[(tier, period)]:.2f}",
            "SignatureValue": "ignored-verify-is-mocked",
            "Shp_user": user_id,
            "Shp_tier": tier,
            "Shp_period": period,
        }

    @pytest.fixture(autouse=True)
    def _valid_signature(self, monkeypatch):
        monkeypatch.setattr(
            "backend.payments.payments_router.verify_payment",
            lambda form: (True, form.get("Shp_user", ""), form.get("Shp_tier", ""), form.get("Shp_period", "")),
        )

    def test_non_partner_referrer_gets_subscription_extended(self, client, db: Session):
        referrer = _user(db, "plain_ref@example.com", tier="pro")
        sub = _subscription(db, referrer, current_period_end=utcnow() + timedelta(days=5))
        buyer = _user(db, "buyer_plain_ref@example.com", tier="free", referred_by=referrer.id)

        resp = client.post(self.PATH, data=self._form(buyer.id, "800001"))
        assert resp.status_code == 200

        db.expire_all()
        assert db.query(Commission).count() == 0
        refreshed = db.query(Subscription).filter(Subscription.id == sub.id).first()
        assert refreshed.current_period_end > utcnow() + timedelta(days=REFERRAL_REWARD_DAYS - 1)

    def test_partner_referrer_gets_commission_not_subscription_extension(self, db: Session, client):
        referrer = _user(db, "partner_ref@example.com", tier="pro")
        sub = _subscription(db, referrer, current_period_end=utcnow() + timedelta(days=5))
        partner = Partner(user_id=referrer.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        buyer = _user(db, "buyer_partner_ref@example.com", tier="free", referred_by=referrer.id)

        original_end = sub.current_period_end
        resp = client.post(self.PATH, data=self._form(buyer.id, "800002"))
        assert resp.status_code == 200

        db.expire_all()
        assert db.query(Commission).filter(Commission.partner_id == partner.id).count() == 1
        refreshed = db.query(Subscription).filter(Subscription.id == sub.id).first()
        assert _close(refreshed.current_period_end, original_end), \
            "у партнёра не должна продлеваться подписка — он получает комиссию, не бонус-дни"

    def test_no_referrer_neither_fires(self, db: Session, client):
        buyer = _user(db, "no_referrer_buyer@example.com", tier="free")
        resp = client.post(self.PATH, data=self._form(buyer.id, "800003"))
        assert resp.status_code == 200
        db.expire_all()
        assert db.query(Commission).count() == 0
