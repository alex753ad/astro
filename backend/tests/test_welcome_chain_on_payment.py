"""Приветственная цепочка писем ставится после успешной оплаты.

Постановщик жил в payments/stripe_service.py и уехал вместе с ним в f3fc0a3
(«удалить Robokassa и Stripe как мёртвый код», 19.08.2026). К ЮKassa цепочку
тогда не перепривязали, и с 19.08 платящий человек не получал по почте
ничего — ни приветствия, ни подтверждения оплаты. Задачи при этом остались
в tasks.py и выглядели живыми.

Здесь проверяется сам факт постановки и три условия вокруг неё: верный
тариф, отсутствие повтора при продлении и то, что недоступная очередь не
стоит человеку подписки. С 23.09.2026 ставится одно приветствие по id
платежа, а сама оплата получает starts_chain — от неё Beat шлёт
lite_day14/pro_day30 (backend/lifecycle_emails.py).
"""

from __future__ import annotations

import itertools
from datetime import timedelta
from unittest.mock import patch

import pytest

from backend.models import PaymentEvent, Subscription
from backend.payments.common import activate_subscription
from backend.time_utils import utcnow

_inv = itertools.count(1)


def _pay(db, user, tier):
    """Оплата так, как её проводит process_payment: запись платежа + активация."""
    pe = PaymentEvent(provider="yookassa", inv_id=f"t-{next(_inv)}", user_id=user.id,
                      tier=tier, period="monthly", amount=100.0)
    db.add(pe)
    db.flush()
    activate_subscription(str(user.id), tier, "monthly", db, payment_event=pe)
    return pe


@pytest.fixture
def queued(monkeypatch):
    """Перехватывает .delay приветствия, возвращает список id платежей."""
    calls: list[int] = []
    monkeypatch.setattr(
        "backend.tasks.send_purchase_welcome_task.delay", calls.append, raising=True,
    )
    return calls


class TestChainIsQueued:
    @pytest.mark.parametrize("tier", ["lite", "pro", "premium"])
    def test_paid_activation_queues_welcome_for_this_payment(self, db, user_free, queued, tier):
        pe = _pay(db, user_free, tier)

        assert queued == [pe.id], "приветствие не поставлено или не по этому платежу"
        assert pe.starts_chain is True

    def test_tier_change_queues_the_new_tier(self, db, user_free, queued):
        """Смена тарифа — не продление: письмо про новый тариф человек видит
        впервые, и оно должно прийти."""
        _pay(db, user_free, "lite")
        queued.clear()

        pe = _pay(db, user_free, "pro")

        assert queued == [pe.id]
        assert pe.starts_chain is True


class TestRenewalDoesNotRepeat:
    def test_second_payment_same_tier_queues_nothing(self, db, user_free, queued):
        """Продливший Вегу на второй месяц не должен снова получить
        «Добро пожаловать» — и цепочку lite_day14 заново."""
        _pay(db, user_free, "lite")
        assert len(queued) == 1
        queued.clear()

        pe = _pay(db, user_free, "lite")

        assert queued == [], "приветствие ушло повторно при продлении"
        assert pe.starts_chain is False

    def test_expired_same_tier_is_treated_as_new(self, db, user_free, queued):
        """Подписка истекла и человек вернулся — это уже не продление:
        renewal требует ЖИВОЙ подписки того же тарифа."""
        _pay(db, user_free, "lite")
        queued.clear()

        sub = db.query(Subscription).filter(Subscription.user_id == user_free.id).first()
        sub.current_period_end = utcnow() - timedelta(days=1)
        db.commit()

        pe = _pay(db, user_free, "lite")

        assert queued == [pe.id]


class TestQueueOutageDoesNotBreakPayment:
    def test_activation_survives_broker_failure(self, db, user_free):
        """Redis/Celery недоступны. Деньги списаны, тариф обязан быть выдан:
        письмо — приятное дополнение, а не часть оплаты."""
        with patch(
            "backend.tasks.send_purchase_welcome_task.delay",
            side_effect=OSError("broker unreachable"),
        ):
            _pay(db, user_free, "lite")

        db.expire_all()
        assert user_free.tier == "lite", "подписка не выдана из-за письма"
        sub = db.query(Subscription).filter(Subscription.user_id == user_free.id).first()
        assert sub is not None and sub.status == "active"

    def test_missing_tasks_module_does_not_break_activation(self, db, user_free):
        """Импорт цепочек тоже под защитой: сломанный tasks.py не должен
        обрушить активацию."""
        with patch(
            "backend.payments.common.logger.warning"
        ) as warn, patch.dict("sys.modules", {"backend.tasks": None}):
            _pay(db, user_free, "pro")

        db.expire_all()
        assert user_free.tier == "pro"
        assert warn.called, "провал постановки должен попадать в лог"


class TestEmailsMatchTheGrid:
    """Обещания писем обязаны совпадать с TIER_FLAGS.

    Приветственное письмо Веги обещало «Транзиты на 12 месяцев» при
    transits_months = 1, письмо Лиры — «5 PDF в месяц» при pdf_per_month = 15
    и «на GPT-4o» при том, что движок один на все тарифы (deepseek_model_pro,
    решение владельца 19.08.2026). Числа выведены из флагов, тест стережёт,
    что их не наберут руками снова.
    """

    async def _render(self, fn, *a):
        captured = {}

        async def _fake_send(to, subject, html):
            captured["subject"], captured["html"] = subject, html
            return True

        with patch("backend.email_service._send", _fake_send):
            await fn(*a)
        return captured["html"]

    async def test_lite_welcome_uses_real_transit_horizon(self):
        from backend.auth.rate_limits import TIER_FLAGS
        from backend.email_service import send_lite_welcome

        html = await self._render(send_lite_welcome, "a@example.com")
        months = TIER_FLAGS["lite"]["transits_months"]

        assert f"Транзиты на {months} " in html, html[:0] or "горизонт не из флага"
        assert "Транзиты на 12 месяцев" not in html

    async def test_pro_welcome_uses_real_pdf_and_interpretation_limits(self):
        from backend.auth.rate_limits import TIER_FLAGS
        from backend.email_service import send_pro_welcome

        html = await self._render(send_pro_welcome, "a@example.com")

        assert f"— {TIER_FLAGS['pro']['pdf_per_month']} в месяц" in html
        # ⚠️ Слово «AI» из пользовательских текстов убрано 17.09.2026 (решение
        # владельца). Проверка осталась про ЧИСЛО из флага — именно она и
        # держит письмо в согласии с сеткой; формулировка тут не закрепляется.
        #
        # ⚠️ Проверять «"AI" not in html» здесь НЕЛЬЗЯ, хотя и хочется: в шапке
        # письма лежит логотип строкой data:image/png;base64, и эти две буквы
        # встречаются в ней случайно. Такая проверка падает на здоровом письме
        # и ловится только чтением 53 строк base64 в выводе.
        assert f"{TIER_FLAGS['pro']['interpretations_per_month']} интерпретаци" in html

    async def test_pro_welcome_does_not_name_a_wrong_model(self):
        """Движок один на все тарифы; тариф регулирует глубину, а не модель."""
        from backend.email_service import send_pro_welcome

        html = await self._render(send_pro_welcome, "a@example.com")
        assert "GPT-4o" not in html
