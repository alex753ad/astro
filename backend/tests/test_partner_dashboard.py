"""Тесты кабинета партнёра (Этап 3): дашборд, счётчик переходов, is_partner."""
from __future__ import annotations

import pytest

from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import User, Partner, PaymentEvent, Commission, PartnerPayout, PartnerVisit
from backend.time_utils import utcnow


@pytest.fixture
def referrer(db):
    user = User(
        email="referrer@example.com", hashed_password=hash_password("Password123!"),
        tier="free", is_active=True, is_email_confirmed=True,
        referral_code="POLUNINA1",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def referrer_headers(referrer):
    token = create_access_token(user_id=referrer.id, email=referrer.email, tier=referrer.tier)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def partner(db, referrer):
    p = Partner(user_id=referrer.id, rate=0.10, started_at=utcnow(), status="active")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _buyer(db, email, referred_by):
    user = User(
        email=email, hashed_password=hash_password("Password123!"),
        tier="pro", is_active=True, is_email_confirmed=True, referred_by=referred_by,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestPartnerDashboard:
    def test_404_for_non_partner(self, client, user_free, auth_headers_free):
        resp = client.get("/api/v1/partners/dashboard", headers=auth_headers_free)
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/partners/dashboard")
        assert resp.status_code in (401, 403)

    def test_aggregates_for_partner(self, db, client, referrer, referrer_headers, partner):
        buyer1 = _buyer(db, "buyer1@example.com", referrer.id)
        buyer2 = _buyer(db, "buyer2@example.com", referrer.id)

        pe1 = PaymentEvent(provider="robokassa", inv_id="inv-1", user_id=buyer1.id,
                            tier="pro", period="monthly", amount=1990.0)
        pe2 = PaymentEvent(provider="robokassa", inv_id="inv-2", user_id=buyer2.id,
                            tier="premium", period="monthly", amount=7990.0)
        db.add_all([pe1, pe2])
        db.flush()

        db.add(Commission(partner_id=partner.id, payment_event_id=pe1.id, amount=199.0, rate=0.10, kind="earned"))
        db.add(Commission(partner_id=partner.id, payment_event_id=pe2.id, amount=799.0, rate=0.10, kind="earned"))
        db.add(PartnerVisit(partner_id=partner.id))
        db.add(PartnerVisit(partner_id=partner.id))
        db.add(PartnerVisit(partner_id=partner.id))
        db.add(PartnerPayout(partner_id=partner.id, amount=500.0, paid_at=utcnow()))
        db.commit()

        resp = client.get("/api/v1/partners/dashboard", headers=referrer_headers)
        assert resp.status_code == 200
        body = resp.json()

        totals = body["totals"]
        assert totals["visits"] == 3
        assert totals["registered"] == 2
        assert totals["paid"] == 2
        assert totals["by_tier"] == {"pro": 1, "premium": 1}
        assert totals["revenue"] == pytest.approx(9980.0)
        assert totals["commission_earned"] == pytest.approx(998.0)
        assert totals["paid_out"] == pytest.approx(500.0)
        assert totals["owed"] == pytest.approx(498.0)
        assert totals["rate"] == pytest.approx(0.10)

        # Никаких персональных данных о приглашённых наружу не идёт.
        dumped = resp.text
        assert "buyer1@example.com" not in dumped
        assert "buyer2@example.com" not in dumped
        assert buyer1.id not in dumped
        assert buyer2.id not in dumped

        assert len(body["monthly"]) == 1
        month = body["monthly"][0]
        assert month["visits"] == 3
        assert month["registered"] == 2
        assert month["paid"] == 2

    def test_refund_adjustment_shows_as_negative(self, db, client, referrer, referrer_headers, partner):
        buyer = _buyer(db, "buyer3@example.com", referrer.id)
        pe = PaymentEvent(provider="robokassa", inv_id="inv-3", user_id=buyer.id,
                           tier="lite", period="monthly", amount=790.0)
        db.add(pe)
        db.flush()
        db.add(Commission(partner_id=partner.id, payment_event_id=pe.id, amount=79.0, rate=0.10, kind="earned"))
        db.add(Commission(partner_id=partner.id, payment_event_id=pe.id, amount=-79.0, rate=None, kind="refund_adjustment"))
        db.commit()

        resp = client.get("/api/v1/partners/dashboard", headers=referrer_headers)
        assert resp.status_code == 200
        assert resp.json()["totals"]["commission_earned"] == pytest.approx(0.0)


class TestTrackVisit:
    def test_valid_ref_code_creates_visit(self, db, client, referrer, partner):
        resp = client.post("/api/v1/partners/track-visit", json={"ref_code": "POLUNINA1"})
        assert resp.status_code == 200
        assert db.query(PartnerVisit).filter(PartnerVisit.partner_id == partner.id).count() == 1

    def test_unknown_ref_code_does_nothing_but_returns_ok(self, client):
        resp = client.post("/api/v1/partners/track-visit", json={"ref_code": "NOPE"})
        assert resp.status_code == 200

    def test_ref_code_of_non_partner_user_does_nothing(self, db, client):
        user = User(
            email="plain_referrer@example.com", hashed_password=hash_password("Password123!"),
            tier="free", is_active=True, is_email_confirmed=True, referral_code="PLAINREF1",
        )
        db.add(user)
        db.commit()
        resp = client.post("/api/v1/partners/track-visit", json={"ref_code": "PLAINREF1"})
        assert resp.status_code == 200
        assert db.query(PartnerVisit).count() == 0

    def test_is_rate_limited(self, client):
        """Публичный, без авторизации — без лимита кто угодно накрутил бы
        партнёру счётчик переходов до бессмысленной цифры (conftest.py
        глушит лимитер по умолчанию во всех тестах — здесь включаем обратно).
        """
        from backend.main import limiter

        limiter.enabled = True
        try:
            responses = []
            for _ in range(35):  # лимит rate_limit_anon = 30/minute
                resp = client.post("/api/v1/partners/track-visit", json={"ref_code": "whatever"})
                responses.append(resp.status_code)
                if resp.status_code == 429:
                    break
            assert 429 in responses, f"лимит не сработал за 35 запросов: {responses}"
        finally:
            limiter.enabled = False


class TestIsPartnerFlag:
    def test_me_reports_true_for_partner(self, client, referrer_headers, partner):
        resp = client.get("/api/v1/auth/me", headers=referrer_headers)
        assert resp.status_code == 200
        assert resp.json()["is_partner"] is True

    def test_me_reports_false_for_regular_user(self, client, user_free, auth_headers_free):
        resp = client.get("/api/v1/auth/me", headers=auth_headers_free)
        assert resp.status_code == 200
        assert resp.json()["is_partner"] is False

    def test_login_response_reports_is_partner_false_without_partner(self, client, referrer):
        resp = client.post("/api/v1/auth/login", json={
            "email": "referrer@example.com", "password": "Password123!",
        })
        assert resp.status_code == 200
        assert resp.json()["is_partner"] is False

    def test_login_response_reports_is_partner_true(self, client, referrer, partner):
        resp = client.post("/api/v1/auth/login", json={
            "email": "referrer@example.com", "password": "Password123!",
        })
        assert resp.status_code == 200
        assert resp.json()["is_partner"] is True
