"""Чеки «Мой налог»: одно сообщение на оплату и сводка за месяц.

Автоматизации чеков нет (ЮKassa закрыла чеки для самозанятых), поэтому
проверяется помощь владельцу: на каждую успешную оплату — вебхук, ручка
статуса, сверка — ровно одно сообщение с данными для чека; дата — момент
оплаты по Москве; 1-го числа — сводка прошлого месяца.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import pytest

from backend.models import PaymentEvent, User
from backend.payments import receipts
from backend.payments import yookassa_router as yk
from backend.tests.test_payment_flow import (  # noqa: F401 — фикстуры
    PID, _FakeRedis, _payment, _reconcile, _status, _webhook, api, configured, sent,
)

PAID = "2026-09-20T21:30:00.000Z"   # 21.09.2026 00:30 по Москве


def _receipts(msgs):
    return [m for m in msgs if m.startswith("🧾 Чек")]


class TestOnePerPayment:
    def test_webhook_sends_receipt_with_payment_date(self, client, user_free, api, sent, monkeypatch):
        p = _payment(user_free.id)
        p["captured_at"] = PAID
        api[PID] = p
        _webhook(client, monkeypatch)
        _webhook(client, monkeypatch)            # повтор ЮKassa
        [text] = _receipts(sent)
        assert "Сумма: 2 490,00 ₽" in text
        assert "Дата: 21.09.2026 00:30 МСК" in text, "дата — момент оплаты по Москве, не отправки"
        assert "тариф «Лира», 30 дней" in text
        assert "free@example.com" in text and PID in text
        assert "Тариф выдан" in text

    def test_status_then_webhook_one_receipt(self, client, user_free, auth_headers_free, api, sent, monkeypatch):
        api[PID] = _payment(user_free.id)
        _status(client, auth_headers_free)
        _webhook(client, monkeypatch)
        _status(client, auth_headers_free)
        assert len(_receipts(sent)) == 1

    def test_reconcile_credit_uses_payment_date(self, db, user_free, sent):
        p = _payment(user_free.id, created_at="2026-09-15T09:00:00.000Z")
        summary, msgs = _reconcile(db, _FakeRedis(), [p])
        assert summary["credited"] == [PID]
        [text] = _receipts(sent)
        assert "15.09.2026 12:00 МСК" in text
        _reconcile(db, _FakeRedis(), [p])
        assert len(_receipts(sent)) == 1, "второй прогон сверки дал второй чек"

    def test_money_without_tariff_still_needs_receipt(self, client, user_free, api, sent, monkeypatch):
        api[PID] = _payment(user_free.id, amount=100.0)
        _webhook(client, monkeypatch)
        _webhook(client, monkeypatch)
        [text] = _receipts(sent)
        assert "Тариф не выдан" in text and "100,00 ₽" in text

    def test_orphan_payment_receipt(self, db, sent):
        summary, _ = _reconcile(db, _FakeRedis(), [_payment("no-such-user")])
        [text] = _receipts(sent)
        assert "Покупатель: не определён" in text and "пользователя нет" in text

    def test_payment_date_is_stored(self, client, db, user_free, api, sent, monkeypatch):
        p = _payment(user_free.id)
        p["captured_at"] = PAID
        api[PID] = p
        _webhook(client, monkeypatch)
        row = db.query(PaymentEvent).filter(PaymentEvent.inv_id == PID).one()
        assert row.paid_at == datetime(2026, 9, 20, 21, 30)


class TestMonthlySummary:
    def _event(self, db, inv, amount, paid_at, user_id=None, tier="lite", period="monthly"):
        db.add(PaymentEvent(provider="yookassa", inv_id=inv, user_id=user_id, tier=tier,
                            period=period, amount=amount, paid_at=paid_at,
                            created_at=datetime(2026, 9, 10)))
        db.commit()

    def _run(self, db, api_items=None):
        out = []

        async def send(text):
            out.append(text)
            return True

        async def lister(since):
            return api_items

        n = asyncio.run(receipts.run_monthly_summary(db, today_msk=date(2026, 9, 1), lister=lister, send=send))
        assert n == len(out)
        return "\n".join(out)

    def test_month_is_by_moscow_payment_date(self, db, user_free):
        # 31.08 23:30 МСК — август; 01.09 00:30 МСК (31.08 21:30 UTC) — уже сентябрь.
        self._event(db, "aug-last", 790, datetime(2026, 8, 31, 20, 30), user_free.id)
        self._event(db, "sep-first", 790, datetime(2026, 8, 31, 21, 30), user_free.id)
        text = self._run(db, [])
        assert "август 2026" in text
        assert "aug-last" in text and "sep-first" not in text
        assert "Оплат: 1, сумма: 790,00 ₽" in text
        assert "free@example.com" in text

    def test_refunds_and_missing_api_payments_are_flagged(self, db, user_free):
        self._event(db, "p1", 2490, datetime(2026, 8, 10, 9, 0), user_free.id, tier="pro")
        self._event(db, "refund:r1", -2490, datetime(2026, 8, 12, 9, 0), user_free.id, tier="pro")
        self._event(db, "bad", 100, datetime(2026, 8, 13, 9, 0), user_free.id, period=None)
        api_items = [
            {"id": "p1", "created_at": "2026-08-10T09:00:00.000Z", "amount": {"value": "2490.00"}},
            {"id": "lost", "created_at": "2026-08-20T09:00:00.000Z", "amount": {"value": "790.00"}},
        ]
        text = self._run(db, api_items)
        assert "Возвраты (1)" in text and "refund:r1" in text
        assert "тариф не выдан" in text                      # платёж «bad»
        assert "Есть в ЮKassa, нет в базе (1)" in text and "lost" in text

    def test_api_down_is_said_not_hidden(self, db):
        assert "Список ЮKassa не получен" in self._run(db, None)

    def test_empty_month(self, db):
        text = self._run(db, [])
        assert "Оплат не было" in text and "сходится" in text

    def test_long_month_is_split_for_telegram(self, db, user_free):
        for i in range(120):
            self._event(db, f"pay-{i:03d}-{'x' * 30}", 790, datetime(2026, 8, 5, 9, i % 60), user_free.id)
        out = []

        async def send(text):
            out.append(text)
            return True

        async def lister(since):
            return []

        asyncio.run(receipts.run_monthly_summary(db, today_msk=date(2026, 9, 1), lister=lister, send=send))
        assert len(out) > 1 and all(len(m) <= 4096 for m in out)
        assert sum(m.count("pay-") for m in out) == 120, "при разрезании потерялись строки"

    def test_january_summarises_december(self):
        start, end, month = receipts.month_bounds(date(2027, 1, 1))
        assert month == date(2026, 12, 1)
        assert start == datetime(2026, 11, 30, 21, 0) and end == datetime(2026, 12, 31, 21, 0)
