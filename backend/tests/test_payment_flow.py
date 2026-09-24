"""Оплата не должна теряться (задание 24.09.2026).

Пункты плана:
1. «оплатил → тариф включился»: ручка статуса для экрана ожидания — ждём,
   отказ с причиной, оплачено раньше вебхука (начисляет сама);
2. вебхук: повтор, раньше редиректа, через час, после смены цены — ровно одно
   начисление; гонка двух доставок — на Postgres, в конце файла;
3. тариф за аккаунтом: новый телефон / веб — после входа тариф на месте;
4. ежедневная сверка с ЮKassa: начисляет тем же путём, сигналит.
Плюс уведомление о смене цен (оферта п. 10.1) и история платежей.
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from datetime import date, datetime, timedelta

import pytest

from backend.models import Announcement, EmailSentLog, PaymentEvent, Subscription, User
from backend.payments import common
from backend.payments import yookassa_router as yk
from backend.payments.common import TIER_PRICES_RUB

YOOKASSA_IP = "185.71.76.1"
WEBHOOK_URL = "/api/v1/payments/yookassa/notification"
PID = "2f0c8a1e-000f-5000-8000-1d0e0c0b0a09"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(yk.settings, "yookassa_shop_id", "1442186", raising=False)
    monkeypatch.setattr(yk.settings, "yookassa_secret_key", "live_test_stub", raising=False)


@pytest.fixture
def sent(monkeypatch):
    """Всё, что ушло владельцу в Telegram."""
    out: list[str] = []

    async def _fake(text, photo_path=None):
        out.append(text)
        return True

    monkeypatch.setattr("backend.notifications.telegram.send_support_message", _fake)
    return out


@pytest.fixture
def api(monkeypatch):
    """Подменяет перечитывание платежа из API ЮKassa: api[id] = платёж."""
    store: dict[str, dict | None] = {}

    async def _fake(payment_id):
        return store.get(payment_id)

    monkeypatch.setattr(yk, "_fetch_payment", _fake)
    return store


def _payment(user_id, *, pid=PID, tier="pro", amount=None, status="succeeded",
             created_at=None, refunded=None, reason=None):
    value = TIER_PRICES_RUB[tier] if amount is None else amount
    p = {
        "id": pid, "status": status,
        "amount": {"value": f"{value:.2f}", "currency": "RUB"},
        "metadata": {"user_id": str(user_id), "tier": tier, "period": "monthly"},
    }
    if created_at:
        p["created_at"] = created_at
    if refunded:
        p["refunded_amount"] = {"value": f"{refunded:.2f}", "currency": "RUB"}
    if reason:
        p["cancellation_details"] = {"party": "payment_network", "reason": reason}
    return p


def _webhook(client, monkeypatch, pid=PID):
    monkeypatch.setattr(yk, "client_ip", lambda request: YOOKASSA_IP)
    return client.post(WEBHOOK_URL, json={"type": "notification", "event": "payment.succeeded",
                                          "object": {"id": pid}})


def _status(client, headers, pid=PID):
    return client.get(f"/api/v1/payments/status/{pid}", headers=headers)


def _events(db):
    db.expire_all()
    return db.query(PaymentEvent).filter(PaymentEvent.provider == "yookassa").all()


# ── 1. Экран ожидания: ручка статуса ────────────────────────

class TestStatus:
    def test_pending(self, client, db, user_free, auth_headers_free, api):
        api[PID] = _payment(user_free.id, status="pending")
        body = _status(client, auth_headers_free).json()
        assert body["state"] == "pending" and body["tier"] == "free"

    def test_canceled_gives_reason_in_russian(self, client, user_free, auth_headers_free, api):
        api[PID] = _payment(user_free.id, status="canceled", reason="insufficient_funds")
        body = _status(client, auth_headers_free).json()
        assert body["state"] == "canceled"
        assert body["reason"] == "На карте не хватило денег."

    def test_closed_window_midway(self, client, user_free, auth_headers_free, api):
        # Окно оплаты закрыли — ЮKassa отменяет платёж по истечении срока.
        api[PID] = _payment(user_free.id, status="canceled", reason="expired_on_confirmation")
        body = _status(client, auth_headers_free).json()
        assert body["state"] == "canceled" and "не была завершена" in body["reason"]

    def test_paid_before_webhook_activates_once(self, client, db, user_free, auth_headers_free,
                                                api, sent, monkeypatch):
        """Вернулся раньше вебхука: ручка начисляет сама; пришедший потом
        вебхук — дубль, срок не удваивается."""
        api[PID] = _payment(user_free.id)
        body = _status(client, auth_headers_free).json()
        assert body["state"] == "succeeded" and body["tier"] == "pro"
        assert body["active_until"]
        end = db.query(Subscription).filter(Subscription.user_id == user_free.id).one().current_period_end

        assert _webhook(client, monkeypatch).status_code == 200
        assert len(_events(db)) == 1
        db.expire_all()
        assert db.query(Subscription).filter(Subscription.user_id == user_free.id).one().current_period_end == end
        # Повторный опрос экрана — снова «готово», без нового начисления.
        assert _status(client, auth_headers_free).json()["state"] == "succeeded"
        assert len(_events(db)) == 1

    def test_foreign_payment_is_404(self, client, user_free, user_pro, auth_headers_free, api):
        api[PID] = _payment(user_pro.id)
        assert _status(client, auth_headers_free).status_code == 404

    def test_api_down_is_unknown_not_error(self, client, user_free, auth_headers_free, api):
        api[PID] = None
        body = _status(client, auth_headers_free).json()
        assert body["state"] == "unknown"

    def test_money_but_cannot_credit_is_review(self, client, db, user_free, auth_headers_free, api, sent):
        api[PID] = _payment(user_free.id, amount=1.0)
        assert _status(client, auth_headers_free).json()["state"] == "review"
        assert sent, "владелец не получил сигнал о платеже, который не начислен"


# ── 2. Вебхук: время доставки и смена цены ──────────────────

class TestWebhookTiming:
    def test_webhook_after_an_hour(self, client, db, user_free, api, sent, monkeypatch):
        created = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        api[PID] = _payment(user_free.id, created_at=created)
        assert _webhook(client, monkeypatch).status_code == 200
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).one().tier == "pro"

    def test_refund_before_late_webhook_does_not_activate(self, client, db, user_free, api, sent, monkeypatch):
        api[PID] = _payment(user_free.id, refunded=TIER_PRICES_RUB["pro"])
        assert _webhook(client, monkeypatch).status_code == 200
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).one().tier == "free"


class TestPriceSchedule:
    @pytest.fixture
    def raised(self, monkeypatch):
        """Цена Лиры поднимается 01.11.2026."""
        schedule = [
            (date(2026, 8, 19), {"lite": 790, "pro": 2490, "premium": 7990}),
            (date(2026, 11, 1), {"lite": 890, "pro": 2990, "premium": 7990}),
        ]
        monkeypatch.setattr(common, "PRICE_SCHEDULE", schedule)
        return schedule

    def test_price_on_uses_moscow_date(self, raised):
        # 31.10 22:00 UTC — по Москве уже 1 ноября.
        assert common.price_on("pro", datetime(2026, 10, 31, 20, 59)) == 2490
        assert common.price_on("pro", datetime(2026, 10, 31, 21, 0)) == 2990

    def test_created_before_change_paid_after_activates(self, client, db, user_free, api, sent,
                                                        raised, monkeypatch):
        """Главное: повышение цены не отбрасывает платёж по старой цене."""
        api[PID] = _payment(user_free.id, amount=2490, created_at="2026-10-31T12:00:00.000Z")
        assert _webhook(client, monkeypatch).status_code == 200
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).one().tier == "pro"

    def test_old_price_after_change_is_rejected(self, client, db, user_free, api, sent,
                                                raised, monkeypatch):
        api[PID] = _payment(user_free.id, amount=2490, created_at="2026-11-02T12:00:00.000Z")
        assert _webhook(client, monkeypatch).status_code == 200
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).one().tier == "free"
        assert any("сумма не совпадает" in m for m in sent)

    def test_upcoming_change(self, raised):
        assert common.upcoming_price_change(datetime(2026, 10, 1)) == raised[1]
        assert common.upcoming_price_change(datetime(2026, 11, 5)) is None


# ── 3. Тариф за аккаунтом ───────────────────────────────────

class TestTariffFollowsAccount:
    @pytest.mark.parametrize("platform", [None, "mobile"])
    def test_new_device_login_sees_tariff(self, client, db, user_free, api, sent, monkeypatch, platform):
        """Новый телефон, переустановка, вход на вебе — это новый вход тем же
        аккаунтом. Тариф и срок приходят с сервера, на устройстве не живут."""
        api[PID] = _payment(user_free.id)
        assert _webhook(client, monkeypatch).status_code == 200

        headers = {"X-Client-Platform": platform} if platform else {}
        login = client.post("/api/v1/auth/login", headers=headers,
                            json={"email": "free@example.com", "password": "Password123!"})
        assert login.status_code == 200, login.text
        assert login.json()["tier"] == "pro"
        token = login.json()["access_token"]
        sub = client.get("/api/v1/payments/subscription",
                         headers={"Authorization": f"Bearer {token}"}).json()
        assert sub["tier"] == "pro" and sub["current_period_end"]


# ── 4. Сверка с ЮKassa ──────────────────────────────────────

class _FakeRedis:
    def __init__(self):
        self.keys: dict[str, str] = {}

    def set(self, key, value, nx=False):
        if nx and key in self.keys:
            return False
        self.keys[key] = value
        return True

    def delete(self, key):
        return 1 if self.keys.pop(key, None) is not None else 0

    def exists(self, key):
        return key in self.keys


def _reconcile(db, redis, payments, now=None):
    from backend.payments.reconcile import run_reconciliation

    async def lister(since):
        return payments

    out: list[str] = []

    async def send(text):
        out.append(text)
        return True

    summary = asyncio.run(run_reconciliation(db, redis, now=now, lister=lister, send=send))
    return summary, out


class TestReconcile:
    def test_missing_webhook_is_credited_and_reported(self, db, user_free, sent):
        redis = _FakeRedis()
        summary, msgs = _reconcile(db, redis, [_payment(user_free.id)])
        assert summary["credited"] == [PID]
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).one().tier == "pro"
        assert any("Начислено сверкой" in m and PID in m and str(user_free.id) in m for m in msgs)

        # Второй прогон: ни второго начисления, ни второго сообщения.
        summary, msgs = _reconcile(db, redis, [_payment(user_free.id)])
        assert summary["credited"] == [] and not msgs
        assert len(_events(db)) == 1

    def test_unusable_is_not_credited(self, db, user_free, sent):
        summary, _ = _reconcile(db, _FakeRedis(), [_payment(user_free.id, amount=1.0)])
        assert summary["credited"] == []
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).one().tier == "free"
        assert any("сумма не совпадает" in m for m in sent)

    def test_refunded_is_not_credited(self, db, user_free, sent):
        summary, _ = _reconcile(db, _FakeRedis(), [_payment(user_free.id, refunded=100)])
        assert summary["credited"] == []

    def test_unknown_user_is_not_credited(self, db, sent):
        summary, _ = _reconcile(db, _FakeRedis(), [_payment("no-such-user")])
        assert summary["credited"] == []
        assert any("некому" in m or "не найден" in m or "выдать" in m for m in sent)

    def test_record_but_no_tier_signals_once(self, db, user_free, sent):
        redis = _FakeRedis()
        _reconcile(db, redis, [_payment(user_free.id)])
        user = db.query(User).filter(User.id == user_free.id).one()
        user.tier = "free"          # тариф пропал (откат, ручная правка)
        db.commit()
        summary, msgs = _reconcile(db, redis, [_payment(user_free.id)])
        assert summary["no_tier"] == [PID]
        assert any("тарифа нет" in m for m in msgs)
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).one().tier == "free", \
            "«запись есть — тарифа нет» — только сигнал, без начисления"
        _, msgs = _reconcile(db, redis, [_payment(user_free.id)])
        assert not msgs, "тот же инцидент просигналил второй раз"

    def test_api_down_signals(self, db):
        summary, msgs = _reconcile(db, _FakeRedis(), None)
        assert summary["checked"] == 0
        assert any("сверка с ЮKassa" in m for m in msgs)


# ── История и поддержка ─────────────────────────────────────

class TestHistory:
    def test_history_lists_payments_and_tariff(self, client, db, user_free, auth_headers_free,
                                               api, sent, monkeypatch):
        api[PID] = _payment(user_free.id)
        _webhook(client, monkeypatch)
        body = client.get("/api/v1/payments/history", headers=auth_headers_free).json()
        assert body["tier"] == "pro" and body["active_until"]
        assert body["items"][0]["id"] == PID and body["items"][0]["kind"] == "payment"


# ── Уведомление о смене цен ─────────────────────────────────

class TestPriceNotice:
    @pytest.fixture
    def schedule(self, monkeypatch):
        from backend.payments import price_notice as pn
        eff = date.today() + timedelta(days=20)
        sched = [(date(2026, 8, 19), {"lite": 790, "pro": 2490, "premium": 7990}),
                 (eff, {"lite": 890, "pro": 2490, "premium": 7990})]
        monkeypatch.setattr(common, "PRICE_SCHEDULE", sched)
        monkeypatch.setattr(pn, "PRICE_SCHEDULE", sched)
        monkeypatch.setattr(pn, "SEND_PAUSE_SEC", 0)
        return eff

    def test_less_than_14_days_is_refused(self, schedule):
        from backend.payments import price_notice as pn
        with pytest.raises(pn.NoticeError):
            pn.build_notice(schedule, today=schedule - timedelta(days=13))

    def test_date_not_in_schedule_is_refused(self, schedule):
        from backend.payments import price_notice as pn
        with pytest.raises(pn.NoticeError):
            pn.build_notice(schedule + timedelta(days=1))

    def test_text_names_old_and_new_price(self, schedule):
        from backend.payments import price_notice as pn
        notice = pn.build_notice(schedule)
        assert "790 ₽ → 890 ₽" in notice["text"]
        assert "Лира" not in notice["text"], "неизменившуюся цену перечислять незачем"

    def test_sends_to_confirmed_including_unsubscribed_once(self, db, schedule, monkeypatch):
        from backend.payments import price_notice as pn
        confirmed = User(email="c@example.com", hashed_password="x", tier="free", is_email_confirmed=True)
        unconfirmed = User(email="u@example.com", hashed_password="x", tier="free", is_email_confirmed=False)
        db.add_all([confirmed, unconfirmed])
        db.commit()
        got: list[str] = []

        async def fake_send(to, subject, html):
            got.append(to)
            return True

        monkeypatch.setattr("backend.email_service._send", fake_send)
        notice = pn.build_notice(schedule)
        assert pn.send_all(db, notice)["sent"] == 1
        assert got == ["c@example.com"]
        assert pn.send_all(db, notice) == {"sent": 0, "skipped": 1, "failed": 0}
        assert db.query(EmailSentLog).filter(EmailSentLog.kind == "price_notice").count() == 1

    def test_admin_dry_run_then_publish(self, client, db, schedule, monkeypatch):
        from backend.auth.jwt import create_access_token
        admin = User(email="admin@example.com", hashed_password="x", tier="free", is_admin=True)
        db.add(admin)
        db.commit()
        h = {"Authorization": f"Bearer {create_access_token(user_id=admin.id, email=admin.email, tier='free')}"}
        url = "/api/v1/payments/admin/price-notice"

        r = client.post(url, json={"effective_date": schedule.isoformat()}, headers=h)
        assert r.status_code == 200 and r.json()["dry_run"] is True
        assert db.query(Announcement).count() == 0, "dry run ничего не публикует"

        queued = []
        monkeypatch.setattr("backend.tasks.send_price_notice_task.delay", lambda d: queued.append(d))
        r = client.post(url, json={"effective_date": schedule.isoformat(), "dry_run": False}, headers=h)
        assert r.status_code == 200 and r.json()["published"] is True
        assert queued == [schedule.isoformat()]
        items = client.get("/api/v1/payments/announcements").json()["items"]
        assert len(items) == 1 and "меняются цены" in items[0]["title"]

    def test_not_admin_is_refused(self, client, auth_headers_free, schedule):
        r = client.post("/api/v1/payments/admin/price-notice",
                        json={"effective_date": schedule.isoformat()}, headers=auth_headers_free)
        assert r.status_code in (401, 403)


# ── Гонка двух доставок — только Postgres ──────────────────

from backend.tests.test_pilot_claim_race import _make_user, pg, requires_postgres  # noqa: E402,F401


@requires_postgres
def test_two_concurrent_deliveries_credit_once(pg, monkeypatch):  # noqa: F811
    """Две доставки одного платежа одновременно (вебхук + ручка статуса, или
    два ретрая ЮKassa). Уникальный inv_id на Postgres ставит вторую в очередь
    до коммита первой — начисление одно, срок не удваивается. На SQLite
    параллельности нет, поэтому тест только здесь."""
    async def _quiet(*a, **kw):
        return True
    monkeypatch.setattr("backend.notifications.telegram.send_support_message", _quiet)

    uid = _make_user(pg, f"race-{uuid.uuid4().hex[:8]}@example.com")
    pid = f"race-{uuid.uuid4()}"
    payment = _payment(uid, pid=pid)
    start = threading.Barrier(2)
    outcomes: list[str] = []

    def deliver():
        with pg() as s:
            start.wait(timeout=10)
            outcomes.append(asyncio.run(yk.settle_payment(s, payment)))

    threads = [threading.Thread(target=deliver) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert sorted(outcomes) == [yk.ACTIVATED, yk.DUPLICATE], outcomes
    with pg() as s:
        assert s.query(PaymentEvent).filter(PaymentEvent.inv_id == pid).count() == 1
        sub = s.query(Subscription).filter(Subscription.user_id == uid).one()
        days = (sub.current_period_end - datetime.utcnow()).days
        assert 28 <= days <= 30, f"срок {days} дней — начислено дважды?"
