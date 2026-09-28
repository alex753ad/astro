"""Счётчики платных тарифов — за оплаченный период (решение владельца 28.09.2026).

Держит:
* покупка 29-го не даёт двух лимитов — 1-е число окно не обнуляет;
* продление даёт свежий счётчик, когда кончается оплаченное окно;
* смена тарифа (Вега → Лира) — свежий счётчик сразу;
* пробные free (TRIAL_PERIOD) не обнуляются никогда;
* даты для текста отказа — по МСК, «новые после продления» без оплаченного
  продления;
* подписка без якоря (была до миграции 065) — окна кончаются в дату конца срока.
"""
from datetime import datetime, timedelta

import pytest

from backend.auth import rate_limits
from backend.auth.rate_limits import (
    TRIAL_PERIOD, get_monthly_usage, increment_monthly_usage, usage_dates, usage_window,
)


@pytest.fixture
def clock(monkeypatch):
    """Одно время на оплату (payments.common.utcnow) и на счётчики (_now)."""
    state = {"now": datetime(2026, 9, 29, 12, 0)}

    def now():
        return state["now"]

    monkeypatch.setattr(rate_limits, "_now", now)
    monkeypatch.setattr("backend.payments.common.utcnow", now)
    return state


def _buy(db, user, tier="lite"):
    from backend.payments.common import activate_subscription
    return activate_subscription(str(user.id), tier, "monthly", db)


def _use(db, user, kind="chat", n=1):
    for _ in range(n):
        increment_monthly_usage(db, str(user.id), kind)


def test_purchase_on_29th_does_not_give_two_limits(db, user_free, clock):
    _buy(db, user_free)
    _use(db, user_free, n=30)
    clock["now"] = datetime(2026, 10, 1, 9, 0)          # 1-е число — раньше тут был сброс
    assert get_monthly_usage(db, str(user_free.id), "chat") == 30
    clock["now"] = datetime(2026, 10, 28, 23, 0)        # всё ещё первые 30 дней
    assert get_monthly_usage(db, str(user_free.id), "chat") == 30


def test_renewal_gives_a_fresh_counter_when_the_paid_window_ends(db, user_free, clock):
    _buy(db, user_free)
    _use(db, user_free, n=30)
    clock["now"] = datetime(2026, 10, 20, 12, 0)
    assert _buy(db, user_free) is True                  # продление, срок прибавлен в конец
    assert get_monthly_usage(db, str(user_free.id), "chat") == 30   # внутри старого окна — то же
    assert usage_dates(db, str(user_free.id))["resets_on"] == "2026-10-29"
    clock["now"] = datetime(2026, 10, 29, 12, 1)        # 30 дней от покупки
    assert get_monthly_usage(db, str(user_free.id), "chat") == 0


def test_tier_change_gives_a_fresh_counter_at_once(db, user_free, clock):
    _buy(db, user_free, "lite")
    _use(db, user_free, "transit_ai", n=15)
    clock["now"] = datetime(2026, 10, 5, 12, 0)
    assert _buy(db, user_free, "pro") is False          # смена тарифа — не продление
    assert get_monthly_usage(db, str(user_free.id), "transit_ai") == 0


def test_free_trials_are_never_reset(db, user_free, clock):
    increment_monthly_usage(db, str(user_free.id), "chat_trial", TRIAL_PERIOD)
    _buy(db, user_free)
    clock["now"] = datetime(2027, 3, 1)
    assert get_monthly_usage(db, str(user_free.id), "chat_trial", TRIAL_PERIOD) == 1


def test_dates_are_moscow_and_say_after_renewal(db, user_free, clock):
    clock["now"] = datetime(2026, 9, 29, 22, 30)        # 01:30 МСК 30 сентября
    _buy(db, user_free)
    d = usage_dates(db, str(user_free.id))
    assert d == {"resets_on": None, "access_until": "2026-10-30"}
    assert rate_limits.ended_text(db, str(user_free.id), "chat", 30) == (
        "30 сообщений на этот срок закончились. Следующие — с 30 октября, после продления.")


def test_ended_text_after_paid_renewal_has_no_renewal_clause(db, user_free, clock):
    _buy(db, user_free)
    clock["now"] = datetime(2026, 10, 20, 12, 0)
    _buy(db, user_free)                                 # продление оплачено
    assert rate_limits.ended_text(db, str(user_free.id), "transit_ai", 15) == (
        "15 разборов транзитов на этот срок закончились. Следующие — с 29 октября.")
    assert rate_limits.ended_text(db, str(user_free.id), "pdf", 1).startswith(
        "1 PDF-отчёт на этот срок закончился.")


def test_free_tier_keeps_calendar_month(db, user_free, clock):
    assert usage_window(db, str(user_free.id)) is None
    assert usage_dates(db, str(user_free.id)) == {"resets_on": "2026-10-01", "access_until": None}


def test_subscription_without_anchor_ends_windows_at_period_end(db, user_free, clock):
    from backend.models import Subscription
    end = datetime(2026, 10, 15, 8, 0)
    db.add(Subscription(user_id=user_free.id, tier="lite", status="active", current_period_end=end))
    db.commit()
    w = usage_window(db, str(user_free.id))
    assert w["fresh_at"] is None and w["access_until"] == end
    # Ключ новый, не «ГГГГ-ММ»: сентябрьский расход по календарю не переносится.
    assert w["key"] != "2026-09"


def test_subscription_endpoint_reports_dates(client, db, user_free, auth_headers_free, clock):
    _buy(db, user_free)
    data = client.get("/api/v1/profile/subscription", headers=auth_headers_free).json()
    assert data["usage_resets_on"] is None
    assert data["usage_access_until"] == "2026-10-29"


# ── PDF при переходе с бесплатного (задание 28.09.2026, раздел 3) ──────────
# Free считает PDF по календарному месяцу (ключ «ГГГГ-ММ»), платные — по окну
# оплаченного срока. После покупки ключ счётчика — ключ нового окна, лимит —
# TIER_FLAGS нового тарифа: бесплатный «1 в месяц» не должен остаться.

@pytest.mark.parametrize("tier, quota", [("lite", 5), ("pro", 15)])
def test_pdf_quota_switches_at_once_after_purchase_from_free(db, user_free, clock, tier, quota):
    from fastapi import HTTPException
    from backend.auth.rate_limits import tier_limiter

    _use(db, user_free, "pdf")                          # бесплатный PDF этого месяца
    with pytest.raises(HTTPException):
        tier_limiter.check_pdf_limit(user_free, db)     # на free — исчерпан

    _buy(db, user_free, tier)
    db.refresh(user_free)
    assert user_free.tier == tier
    assert get_monthly_usage(db, str(user_free.id), "pdf") == 0
    for _ in range(quota):
        tier_limiter.check_pdf_limit(user_free, db)     # не бросает
        _use(db, user_free, "pdf")
    with pytest.raises(HTTPException) as exc:
        tier_limiter.check_pdf_limit(user_free, db)
    assert f"{quota} PDF-отчётов на этот срок закончились" in exc.value.detail
