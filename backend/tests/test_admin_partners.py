"""Тесты админской вкладки партнёров (Этап 4): CRUD партнёра, выплаты."""
from __future__ import annotations

import pytest

from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import User, Partner, PaymentEvent, Commission
from backend.time_utils import utcnow


@pytest.fixture
def admin_user(db):
    user = User(
        email="admin_partners@example.com", hashed_password=hash_password("Password123!"),
        name="Admin", tier="premium", is_admin=True, is_active=True, is_email_confirmed=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token(user_id=admin_user.id, email=admin_user.email, tier=admin_user.tier)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def target_user(db):
    user = User(
        email="future_partner@example.com", hashed_password="hashed",
        tier="free", is_active=True, is_email_confirmed=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestNonAdminRejected:
    def test_list_requires_admin(self, client, auth_headers_free):
        assert client.get("/api/v1/admin/partners", headers=auth_headers_free).status_code == 403

    def test_create_requires_admin(self, client, auth_headers_free):
        resp = client.post("/api/v1/admin/partners", json={"email": "x@example.com"}, headers=auth_headers_free)
        assert resp.status_code == 403


class TestCreatePartner:
    def test_creates_partner_for_existing_user(self, db, client, admin_headers, target_user):
        resp = client.post(
            "/api/v1/admin/partners",
            json={"email": "future_partner@example.com", "rate": 0.15, "note": "Полунина"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "future_partner@example.com"
        assert body["rate"] == pytest.approx(0.15)
        assert body["status"] == "active"
        assert body["note"] == "Полунина"
        assert db.query(Partner).filter(Partner.user_id == target_user.id).count() == 1

    def test_unknown_email_404(self, client, admin_headers):
        resp = client.post("/api/v1/admin/partners", json={"email": "nobody@example.com"}, headers=admin_headers)
        assert resp.status_code == 404

    def test_duplicate_partner_409(self, db, client, admin_headers, target_user):
        db.add(Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active"))
        db.commit()
        resp = client.post("/api/v1/admin/partners", json={"email": "future_partner@example.com"}, headers=admin_headers)
        assert resp.status_code == 409

    def test_default_rate_is_10_percent(self, client, admin_headers, target_user):
        resp = client.post("/api/v1/admin/partners", json={"email": "future_partner@example.com"}, headers=admin_headers)
        assert resp.json()["rate"] == pytest.approx(0.10)


class TestListPartners:
    def test_shows_same_totals_as_own_dashboard(self, db, client, admin_headers, target_user):
        partner = Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        db.refresh(partner)

        buyer = User(email="buyer_x@example.com", hashed_password="h", tier="pro",
                      is_active=True, is_email_confirmed=True, referred_by=target_user.id)
        db.add(buyer)
        db.commit()
        db.refresh(buyer)

        pe = PaymentEvent(provider="robokassa", inv_id="inv-admin-1", user_id=buyer.id,
                           tier="pro", period="monthly", amount=1990.0)
        db.add(pe)
        db.flush()
        db.add(Commission(partner_id=partner.id, payment_event_id=pe.id, amount=199.0, rate=0.10, kind="earned"))
        db.commit()

        # Собственный кабинет партнёра
        own_token = create_access_token(user_id=target_user.id, email=target_user.email, tier=target_user.tier)
        own_resp = client.get("/api/v1/partners/dashboard", headers={"Authorization": f"Bearer {own_token}"})
        own_totals = own_resp.json()["totals"]

        admin_resp = client.get("/api/v1/admin/partners", headers=admin_headers)
        assert admin_resp.status_code == 200
        admin_partner = admin_resp.json()["partners"][0]
        assert admin_partner["totals"] == own_totals


class TestUpdatePartner:
    def test_changes_rate_does_not_touch_past_commissions(self, db, client, admin_headers, target_user):
        partner = Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        db.refresh(partner)

        db.add(Commission(partner_id=partner.id, payment_event_id=None, amount=199.0, rate=0.10, kind="earned"))
        db.commit()

        resp = client.patch(f"/api/v1/admin/partners/{partner.id}", json={"rate": 0.20}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["rate"] == pytest.approx(0.20)

        stored = db.query(Commission).filter(Commission.partner_id == partner.id).first()
        assert stored.rate == pytest.approx(0.10)  # снимок на момент начисления не меняется

    def test_pause_and_reactivate(self, db, client, admin_headers, target_user):
        partner = Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        db.refresh(partner)

        resp = client.patch(f"/api/v1/admin/partners/{partner.id}", json={"status": "paused"}, headers=admin_headers)
        assert resp.json()["status"] == "paused"

        resp2 = client.patch(f"/api/v1/admin/partners/{partner.id}", json={"status": "active"}, headers=admin_headers)
        assert resp2.json()["status"] == "active"

    def test_invalid_status_rejected(self, db, client, admin_headers, target_user):
        partner = Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        db.refresh(partner)
        resp = client.patch(f"/api/v1/admin/partners/{partner.id}", json={"status": "bogus"}, headers=admin_headers)
        assert resp.status_code == 400

    def test_404_for_unknown_partner(self, client, admin_headers):
        resp = client.patch("/api/v1/admin/partners/does-not-exist", json={"rate": 0.2}, headers=admin_headers)
        assert resp.status_code == 404


class TestPayouts:
    def test_mark_payout_creates_record(self, db, client, admin_headers, target_user):
        partner = Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        db.refresh(partner)

        resp = client.post(
            f"/api/v1/admin/partners/{partner.id}/payouts",
            json={"amount": 1500.0, "note": "перевод на карту"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["amount"] == pytest.approx(1500.0)
        assert body["note"] == "перевод на карту"

        history = client.get(f"/api/v1/admin/partners/{partner.id}/payouts", headers=admin_headers)
        assert history.status_code == 200
        assert len(history.json()) == 1

    def test_negative_amount_rejected(self, db, client, admin_headers, target_user):
        partner = Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        db.refresh(partner)
        resp = client.post(
            f"/api/v1/admin/partners/{partner.id}/payouts",
            json={"amount": -100.0},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_payout_reduces_owed_in_own_dashboard(self, db, client, admin_headers, target_user):
        partner = Partner(user_id=target_user.id, rate=0.10, started_at=utcnow(), status="active")
        db.add(partner)
        db.commit()
        db.refresh(partner)
        db.add(Commission(partner_id=partner.id, payment_event_id=None, amount=1000.0, rate=0.10, kind="earned"))
        db.commit()

        client.post(f"/api/v1/admin/partners/{partner.id}/payouts", json={"amount": 400.0}, headers=admin_headers)

        token = create_access_token(user_id=target_user.id, email=target_user.email, tier=target_user.tier)
        resp = client.get("/api/v1/partners/dashboard", headers={"Authorization": f"Bearer {token}"})
        totals = resp.json()["totals"]
        assert totals["paid_out"] == pytest.approx(400.0)
        assert totals["owed"] == pytest.approx(600.0)

    def test_payout_404_for_unknown_partner(self, client, admin_headers):
        resp = client.post("/api/v1/admin/partners/does-not-exist/payouts", json={"amount": 100.0}, headers=admin_headers)
        assert resp.status_code == 404
