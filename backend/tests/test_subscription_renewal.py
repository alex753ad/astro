"""Повторная оплата продлевает подписку, а не перезаписывает её.

Решение владельца 22.08.2026: заплативший дважды за тот же тариф получает
60 дней. До этого второй платёж ставил current_period_end = сегодня + 30,
и оплаченный остаток первого молча пропадал.

Отдельно фиксируется граница, которую легко перепутать:
  ДВА РАЗНЫХ платежа (разные payment_id)  → срок суммируется;
  ОДИН платёж, доставленный дважды         → не меняется ничего.
Первое — деньги, полученные дважды. Второе — ретрай вебхука ЮKassa, который
приходит до тех пор, пока не получит 200. Если их перепутать, один платёж
начнёт продлевать подписку на каждый ретрай.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.models import PaymentEvent, Subscription, User
from backend.payments.common import (
    DuplicatePayment,
    TIER_PRICES_RUB,
    activate_subscription,
    process_payment,
)
from backend.time_utils import utcnow

DAY = timedelta(days=1)


def _pay(db, user_id, payment_id, tier="lite"):
    """Отдельный платёж — как два разных списания у ЮKassa."""
    return process_payment(
        db, provider="yookassa", payment_id=payment_id,
        user_id=user_id, tier=tier, period="monthly",
        amount=float(TIER_PRICES_RUB[tier]),
    )


def _sub(db, user_id) -> Subscription:
    db.expire_all()
    subs = db.query(Subscription).filter(Subscription.user_id == user_id).all()
    assert len(subs) == 1, f"ожидалась одна строка подписки, найдено {len(subs)}"
    return subs[0]


def _days_from_now(dt) -> float:
    return (dt - utcnow()).total_seconds() / 86400


# ── Продление тем же тарифом ───────────────────────────────

class TestSameTierAccumulates:

    def test_two_payments_give_sixty_days(self, db, user_free):
        _pay(db, user_free.id, "pay-1", tier="lite")
        first_end = _sub(db, user_free.id).current_period_end

        _pay(db, user_free.id, "pay-2", tier="lite")

        sub = _sub(db, user_free.id)
        assert sub.tier == "lite"
        # Ровно +30 суток к ПЕРВОЙ дате окончания, а не «сегодня + 30».
        assert abs((sub.current_period_end - (first_end + timedelta(days=30))).total_seconds()) < 60
        assert 59 < _days_from_now(sub.current_period_end) <= 60

    def test_three_payments_give_ninety_days(self, db, user_free):
        for i in range(3):
            _pay(db, user_free.id, f"pay-{i}", tier="lite")

        assert 89 < _days_from_now(_sub(db, user_free.id).current_period_end) <= 90

    def test_no_second_row_is_created(self, db, user_free):
        """Вторая активная строка ломала expire_subscriptions: он находил
        просроченную и сбрасывал тариф при живой второй."""
        _pay(db, user_free.id, "pay-1", tier="lite")
        _pay(db, user_free.id, "pay-2", tier="lite")

        db.expire_all()
        assert db.query(Subscription).filter(Subscription.user_id == user_free.id).count() == 1


# ── Смена тарифа: остаток сгорает ──────────────────────────

class TestTierChangeResets:

    def test_upgrade_burns_remainder(self, db, user_free):
        _pay(db, user_free.id, "pay-1", tier="lite")
        _pay(db, user_free.id, "pay-2", tier="pro")

        sub = _sub(db, user_free.id)
        assert sub.tier == "pro"
        # 30 дней от сегодня, а не 60: остаток Lite не переносится.
        assert 29 < _days_from_now(sub.current_period_end) <= 30
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "pro"

    def test_downgrade_also_resets(self, db, user_free):
        _pay(db, user_free.id, "pay-1", tier="pro")
        _pay(db, user_free.id, "pay-2", tier="lite")

        sub = _sub(db, user_free.id)
        assert sub.tier == "lite"
        assert 29 < _days_from_now(sub.current_period_end) <= 30


# ── Правило обязано быть описано в оферте ──────────────────

class TestOfferDocumentsTheRule:
    """Сгорание остатка при смене тарифа — то, о чём пользователь узнаёт
    постфактум, если не написать. Купивший Лиру на 25-й день Веги теряет пять
    дней; по ЗоЗПП это недоведённая информация об услуге.

    Правило работает в коде с самого начала (см. TestTierChangeResets выше) и
    до 23.08.2026 нигде не было описано. Тесты ниже связывают код с текстом:
    если поведение поменяют, упадёт последний тест и напомнит, что оферта
    стала неправдой.

    Текст проверяется в ОБЕИХ половинах пары: TermsPage.jsx — то, что видит
    пользователь, oferta_final.md — утверждённый владельцем исходник.
    Расхождение пары недопустимо (CLAUDE.md).
    """

    CLAUSE = (
        "При переходе на другой тариф до окончания оплаченного периода "
        "неиспользованные дни текущего тарифа не переносятся и не компенсируются. "
        "Новый тариф действует 30 дней с даты оплаты."
    )

    @staticmethod
    def _read(*parts) -> str:
        from pathlib import Path
        return (Path(__file__).resolve().parents[2].joinpath(*parts)).read_text(encoding="utf-8")

    def test_clause_present_in_both_halves_of_the_pair(self):
        page = self._read("frontend", "src", "pages", "TermsPage.jsx")
        source = self._read("oferta_final.md")
        assert self.CLAUSE in page, "оферта на сайте не предупреждает о сгорании остатка"
        assert self.CLAUSE in source, "oferta_final.md разошёлся с TermsPage.jsx"

    def test_pricing_page_warns_too(self):
        pricing = self._read("frontend", "src", "pages", "PricingPage.jsx")
        assert "При переходе на другой тариф" in pricing, \
            "на /pricing нет предупреждения — человек видит цену раньше, чем оферту"

    def test_clause_matches_actual_behaviour(self, db, user_free):
        """Если этот тест упал — сначала прочитать оферту, п. 4.3.

        Код перестал сжигать остаток при смене тарифа, значит текст в
        TermsPage.jsx / oferta_final.md стал неправдой. Писать в оферте то,
        чего код не делает, хуже, чем не писать ничего: править надо оба места
        разом, а не «чинить» этот assert.
        """
        _pay(db, user_free.id, "pay-1", tier="lite")
        before = _sub(db, user_free.id).current_period_end

        _pay(db, user_free.id, "pay-2", tier="pro")
        after = _sub(db, user_free.id).current_period_end

        assert after < before + timedelta(days=29), (
            "остаток прежнего тарифа перенёсся — оферта (п. 4.3) обещает обратное"
        )
        assert 29 < _days_from_now(after) <= 30, "новый тариф должен идти 30 дней с даты оплаты"


# ── Истёкшая подписка ──────────────────────────────────────

class TestExpiredStartsFromToday:

    def test_expired_same_tier_does_not_add_to_past_date(self, db, user_free):
        """Складывать с датой в прошлом означало бы выдать меньше 30 дней
        за полный платёж."""
        db.add(Subscription(
            user_id=user_free.id, stripe_price_id="lite_monthly",
            status="expired", tier="lite",
            current_period_end=utcnow() - timedelta(days=40),
        ))
        db.commit()

        _pay(db, user_free.id, "pay-1", tier="lite")

        assert 29 < _days_from_now(_sub(db, user_free.id).current_period_end) <= 30

    def test_status_active_but_date_in_past_still_starts_from_today(self, db, user_free):
        """expire_subscriptions ходит раз в сутки — между истечением и его
        запуском строка остаётся active с датой в прошлом. Проверка должна
        смотреть на дату, а не только на статус."""
        db.add(Subscription(
            user_id=user_free.id, stripe_price_id="lite_monthly",
            status="active", tier="lite",
            current_period_end=utcnow() - timedelta(days=2),
        ))
        db.commit()

        _pay(db, user_free.id, "pay-1", tier="lite")

        assert 29 < _days_from_now(_sub(db, user_free.id).current_period_end) <= 30

    def test_active_row_without_end_date_starts_from_today(self, db, user_free):
        """Состояние «бессрочно ⚠» (current_period_end IS NULL) не должно
        валить активацию на сложении с None."""
        db.add(Subscription(
            user_id=user_free.id, stripe_price_id="lite_monthly",
            status="active", tier="lite", current_period_end=None,
        ))
        db.commit()

        _pay(db, user_free.id, "pay-1", tier="lite")

        assert 29 < _days_from_now(_sub(db, user_free.id).current_period_end) <= 30


# ── Граница: два платежа против одного ретрая ──────────────

class TestRetryIsNotASecondPayment:
    """Самое опасное место этой правки: продление не должно срабатывать на
    повторной доставке ОДНОГО платежа."""

    def test_same_payment_id_delivered_repeatedly_changes_nothing(self, db, user_free):
        _pay(db, user_free.id, "pay-1", tier="lite")
        end_after_first = _sub(db, user_free.id).current_period_end

        # Ровно так выглядит ретрай вебхука ЮKassa: тот же payment_id.
        for _ in range(5):
            with pytest.raises(DuplicatePayment):
                _pay(db, user_free.id, "pay-1", tier="lite")

        sub = _sub(db, user_free.id)
        assert sub.current_period_end == end_after_first, \
            "ретрай продлил подписку — один платёж оплачен как несколько"
        assert 29 < _days_from_now(sub.current_period_end) <= 30
        db.expire_all()
        assert db.query(PaymentEvent).count() == 1

    def test_retry_interleaved_with_a_real_second_payment(self, db, user_free):
        """Смешанная последовательность: платёж, его ретраи, второй платёж,
        снова ретраи. Итог — ровно два продления, 60 дней."""
        _pay(db, user_free.id, "pay-1", tier="lite")
        for _ in range(2):
            with pytest.raises(DuplicatePayment):
                _pay(db, user_free.id, "pay-1", tier="lite")

        _pay(db, user_free.id, "pay-2", tier="lite")
        for _ in range(2):
            with pytest.raises(DuplicatePayment):
                _pay(db, user_free.id, "pay-2", tier="lite")

        assert 59 < _days_from_now(_sub(db, user_free.id).current_period_end) <= 60
        db.expire_all()
        assert db.query(PaymentEvent).count() == 2


# ── Существующие дубли в базе ──────────────────────────────

class TestPreExistingDuplicates:
    """Если дубли уже созданы (до этого фикса), активация должна работать с
    самой поздней строкой, а не с произвольной."""

    def test_extends_the_latest_row(self, db, user_free):
        near = utcnow() + timedelta(days=3)
        far = utcnow() + timedelta(days=25)
        db.add(Subscription(user_id=user_free.id, stripe_price_id="lite_monthly",
                            status="active", tier="lite", current_period_end=near))
        db.add(Subscription(user_id=user_free.id, stripe_price_id="lite_monthly",
                            status="active", tier="lite", current_period_end=far))
        db.commit()

        activate_subscription(user_id=user_free.id, tier="lite", period="monthly", db=db)

        db.expire_all()
        ends = [
            s.current_period_end
            for s in db.query(Subscription).filter(Subscription.user_id == user_free.id).all()
        ]
        # Продлена именно поздняя: 25 + 30 = 55 дней от сегодня.
        assert any(54 < _days_from_now(e) <= 55 for e in ends), ends
