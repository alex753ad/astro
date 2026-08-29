"""Приветственная цепочка писем ставится после успешной оплаты.

Постановщик жил в payments/stripe_service.py и уехал вместе с ним в f3fc0a3
(«удалить Robokassa и Stripe как мёртвый код», 19.08.2026). К ЮKassa цепочку
тогда не перепривязали, и с 19.08 платящий человек не получал по почте
ничего — ни приветствия, ни подтверждения оплаты. Задачи при этом остались
в tasks.py и выглядели живыми.

Здесь проверяется сам факт постановки и три условия вокруг неё: верный
тариф, отсутствие повтора при продлении и то, что недоступная очередь не
стоит человеку подписки.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest

from backend.models import Subscription
from backend.payments.common import activate_subscription
from backend.time_utils import utcnow


@pytest.fixture
def queued(monkeypatch):
    """Перехватывает .delay у всех трёх цепочек, возвращает список вызовов."""
    calls: list[tuple[str, object]] = []

    for tier, name in (
        ("lite", "schedule_lite_emails"),
        ("pro", "schedule_pro_emails"),
        ("premium", "schedule_premium_emails"),
    ):
        monkeypatch.setattr(
            f"backend.tasks.{name}.delay",
            (lambda t: lambda uid: calls.append((t, uid)))(tier),
            raising=True,
        )
    return calls


class TestChainIsQueued:
    @pytest.mark.parametrize("tier", ["lite", "pro", "premium"])
    def test_paid_activation_queues_matching_chain(self, db, user_free, queued, tier):
        activate_subscription(str(user_free.id), tier, "monthly", db)

        assert [t for t, _ in queued] == [tier], (
            "поставлена цепочка не того тарифа или не поставлена вовсе"
        )
        assert queued[0][1] == user_free.id

    def test_tier_change_queues_the_new_tier(self, db, user_free, queued):
        """Смена тарифа — не продление: письмо про новый тариф человек видит
        впервые, и оно должно прийти."""
        activate_subscription(str(user_free.id), "lite", "monthly", db)
        queued.clear()

        activate_subscription(str(user_free.id), "pro", "monthly", db)

        assert [t for t, _ in queued] == ["pro"]


class TestRenewalDoesNotRepeat:
    def test_second_payment_same_tier_queues_nothing(self, db, user_free, queued):
        """Продливший Вегу на второй месяц не должен снова получить
        «Добро пожаловать»."""
        activate_subscription(str(user_free.id), "lite", "monthly", db)
        assert len(queued) == 1
        queued.clear()

        activate_subscription(str(user_free.id), "lite", "monthly", db)

        assert queued == [], "приветствие ушло повторно при продлении"

    def test_expired_same_tier_is_treated_as_new(self, db, user_free, queued):
        """Подписка истекла и человек вернулся — это уже не продление:
        renewal требует ЖИВОЙ подписки того же тарифа."""
        activate_subscription(str(user_free.id), "lite", "monthly", db)
        queued.clear()

        sub = db.query(Subscription).filter(Subscription.user_id == user_free.id).first()
        sub.current_period_end = utcnow() - timedelta(days=1)
        db.commit()

        activate_subscription(str(user_free.id), "lite", "monthly", db)

        assert [t for t, _ in queued] == ["lite"]


class TestQueueOutageDoesNotBreakPayment:
    def test_activation_survives_broker_failure(self, db, user_free):
        """Redis/Celery недоступны. Деньги списаны, тариф обязан быть выдан:
        письмо — приятное дополнение, а не часть оплаты."""
        with patch(
            "backend.tasks.schedule_lite_emails.delay",
            side_effect=OSError("broker unreachable"),
        ):
            activate_subscription(str(user_free.id), "lite", "monthly", db)

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
            activate_subscription(str(user_free.id), "pro", "monthly", db)

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
        assert f"{TIER_FLAGS['pro']['interpretations_per_month']} AI-интерпретаци" in html

    async def test_pro_welcome_does_not_name_a_wrong_model(self):
        """Движок один на все тарифы; тариф регулирует глубину, а не модель."""
        from backend.email_service import send_pro_welcome

        html = await self._render(send_pro_welcome, "a@example.com")
        assert "GPT-4o" not in html
