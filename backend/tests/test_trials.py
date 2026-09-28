"""Пробные разборы транзитов и сообщения чата на бесплатном тарифе,
лимит чата Веги (решения владельца 28.09.2026).

* free: 2 разбора транзитов за всё время, на ЛЮБЫЕ транзиты (не «значимые»);
* free: 3 сообщения чата за всё время; Вега — 30 в месяц; Лира — без лимита;
* списание — только после выданного текста;
* остатки видны в /profile/subscription (trials);
* в промптах кабинета астролога нет имени, даты и места рождения клиента.
"""
from backend.auth.rate_limits import TIER_FLAGS, TRIAL_PERIOD, chat_quota, increment_monthly_usage, transit_trials_left
from backend.tests.test_chart_access import _make_chart
from backend.tests.test_transit_event_cache_quota import (  # noqa: F401 — фикстуры
    _post_event, clear_transit_interp_cache, fake_router,
)


def test_flags():
    assert TIER_FLAGS["free"]["transits_ai_trial"] == 2
    assert TIER_FLAGS["free"]["chat_trial"] == 3
    assert TIER_FLAGS["lite"]["chat_per_month"] == 30
    assert TIER_FLAGS["pro"].get("chat_per_month") is None


def test_free_transit_trials_any_transit_then_403(client, db, user_free, auth_headers_free, fake_router):  # noqa: F811
    chart = _make_chart(db, user_id=user_free.id)
    # Mars → Sun — быстрая планета, раньше на free «незначимая» и закрытая.
    r = _post_event(client, chart.id, auth_headers_free)
    assert r.status_code == 200, r.text
    assert "[DONE]" in r.text
    assert transit_trials_left(db, user_free) == 1

    # Второй — другим транзитом (кэш не мешает).
    from backend.cache import transit_interp_cache
    transit_interp_cache.clear()
    r = _post_event(client, chart.id, auth_headers_free)
    assert r.status_code == 200
    assert transit_trials_left(db, user_free) == 0

    transit_interp_cache.clear()
    r = _post_event(client, chart.id, auth_headers_free)
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert "Пробные разборы транзитов закончились" in detail
    assert f"{TIER_FLAGS['lite']['transits_ai_per_month']} в месяц" in detail


def test_subscription_shows_trials(client, db, user_free, auth_headers_free):
    data = client.get("/api/v1/profile/subscription", headers=auth_headers_free).json()
    assert data["trials"] == {"transit_trials_left": 2, "chat_left": 3, "chat_period": "trial"}


def test_chat_quota_by_tier(db, user_free):
    assert chat_quota(db, user_free) == (3, "trial")
    for _ in range(3):
        increment_monthly_usage(db, str(user_free.id), "chat_trial", TRIAL_PERIOD)
    assert chat_quota(db, user_free) == (0, "trial")
    user_free.tier = "lite"
    db.commit()
    assert chat_quota(db, user_free) == (30, "month")
    user_free.tier = "pro"
    db.commit()
    assert chat_quota(db, user_free) == (None, None)


def test_chat_limit_403_for_exhausted_free(client, db, user_free, auth_headers_free):
    chart = _make_chart(db, user_id=user_free.id)
    for _ in range(3):
        increment_monthly_usage(db, str(user_free.id), "chat_trial", TRIAL_PERIOD)
    r = client.post(f"/api/v1/chart/{chart.id}/rag-chat", json={"question": "Что у меня с работой?"},
                    headers=auth_headers_free)
    assert r.status_code == 403
    assert "Пробные сообщения закончились" in r.json()["detail"]


def test_chat_commit_only_after_answer(db, user_free, monkeypatch):
    import asyncio
    from backend.interpretation import rag_router
    monkeypatch.setattr(rag_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    async def no_memory(*a, **kw):
        return None
    monkeypatch.setattr(rag_router, "_update_memory", no_memory)

    asyncio.run(rag_router._finish_turn(str(user_free.id), "free", "q", [], {}))
    assert chat_quota(db, user_free) == (3, "trial"), "обрыв без ответа списал сообщение"
    asyncio.run(rag_router._finish_turn(str(user_free.id), "free", "q", [], {"answer": "текст"}))
    assert chat_quota(db, user_free) == (2, "trial")


def test_crm_prompts_have_no_name_or_birth_data():
    import inspect
    from backend.crm.brief_prompt import build_brief_prompt
    from backend.crm.summary_prompt import build_summary_prompt
    for fn in (build_brief_prompt, build_summary_prompt):
        params = inspect.signature(fn).parameters
        assert "client_name" not in params and "birth_info" not in params, fn.__name__
    text = build_brief_prompt(natal_profile={"planets": [{"name": "Sun", "sign": "Leo"}]})
    assert "ДАННЫЕ РОЖДЕНИЯ" not in text and "по имени" not in text


def test_quota_resets_on_is_first_of_next_utc_month(monkeypatch):
    """Счётчики — по календарному месяцу UTC, не от даты оплаты. Клиент берёт
    дату сброса из ответа (usage_resets_on) и не вычисляет её сам."""
    from backend.auth import rate_limits
    monkeypatch.setattr(rate_limits, "_current_period_ym", lambda: "2026-09")
    assert rate_limits.quota_resets_on() == "2026-10-01"
    monkeypatch.setattr(rate_limits, "_current_period_ym", lambda: "2026-12")
    assert rate_limits.quota_resets_on() == "2027-01-01"
    assert rate_limits.ru_day_month("2026-10-01") == "1 октября"


def test_subscription_has_reset_date(client, auth_headers_free):
    from backend.auth.rate_limits import quota_resets_on
    data = client.get("/api/v1/profile/subscription", headers=auth_headers_free).json()
    assert data["usage_resets_on"] == quota_resets_on()
