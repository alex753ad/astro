"""Обращение из приложения — весь путь до запроса в Telegram.

27.09.2026 обращения из приложения («Оплата и поддержка» → Написать) не
доходили в канал, жалобы с веба доходили. Юнит-тесты `_format_report` и
подмена `send_support_message` целиком этот путь не проходили: подменялось
ровно то место, где он мог обрываться. Здесь запрос собирается так, как его
шлёт `mobile/lib/supportBus.js` (multipart, токен, версия, телефон, текст
ошибки, экран payment), у пользователя есть подписка и платежи, а подменён
только сетевой вызов Telegram — всё, что выше него, исполняется настоящее.
"""
from datetime import timedelta
from unittest.mock import patch

import httpx

from backend.models import PaymentEvent, Subscription
from backend.time_utils import utcnow

APP_FORM = {
    "screen": "payment",
    "message": "Заплатила, а тариф не включился",
    "app_version": "0.1.0 (99da376)",
    "device": "SM-A515F, Android 13",
    "error_text": "Оплата не подтвердилась.",
    "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-A515F Build/TP1A; wv) Chrome/140 Mobile",
}


def _seed_payments(db, user):
    db.add(Subscription(user_id=user.id, tier="lite", status="active",
                        current_period_end=utcnow() + timedelta(days=30)))
    db.add(PaymentEvent(provider="yookassa", inv_id="2e9f-test-1", user_id=user.id,
                        tier="lite", period="month", amount=790.0))
    db.add(PaymentEvent(provider="yookassa", inv_id="2e9f-test-2", user_id=user.id,
                        tier="lite", period=None, amount=790.0))
    db.commit()


def test_app_payment_report_reaches_telegram_call(client, db, user_free, auth_headers_free, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    monkeypatch.setenv("TELEGRAM_SUPPORT_CHAT_ID", "-1001234")
    _seed_payments(db, user_free)

    sent = []

    async def fake_post(self, url, data=None, files=None, **kw):
        # Копия на почту (Resend) идёт тем же httpx — считаем только Telegram.
        if "api.telegram.org" in url:
            sent.append({"url": url, "data": data})
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", fake_post):
        resp = client.post("/api/v1/feedback", data=APP_FORM, headers=auth_headers_free)

    assert resp.status_code == 201, resp.text
    assert len(sent) == 1, "запрос в Telegram не ушёл"
    call = sent[0]
    assert call["url"].endswith("/bot123:TEST/sendMessage")
    assert call["data"]["chat_id"] == "-1001234"
    text = call["data"]["text"]
    for part in ("Обращение в поддержку", "Экран: payment", user_free.email,
                 "Версия: 0.1.0 (99da376)", "Телефон: SM-A515F, Android 13",
                 "Ошибка: Оплата не подтвердилась.", "Заплатила, а тариф не включился",
                 "Тариф:", "Платёж 2e9f-test-1", "Платёж 2e9f-test-2"):
        assert part in text, part
    assert len(text) <= 4096


# ── Токен бота не уходит в логи и Sentry ─────────────────
# 27.09.2026: строка httpx «HTTP Request: POST https://api.telegram.org/bot<токен>/…»
# уровня INFO стояла в `docker compose logs api` и попала в вывод диагностики.

def test_httpx_request_log_is_silenced():
    import logging
    import backend.notifications.telegram  # noqa: F401 — уровень ставится при импорте
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_success_logs_message_id(client, db, user_free, auth_headers_free, monkeypatch, caplog):
    import logging
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    monkeypatch.setenv("TELEGRAM_SUPPORT_CHAT_ID", "-1001234")

    async def fake_post(self, url, data=None, files=None, **kw):
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 77, "chat": {"id": -1001234}}},
                              request=httpx.Request("POST", url))

    with caplog.at_level(logging.INFO, logger="astro.notifications.telegram"), \
            patch.object(httpx.AsyncClient, "post", fake_post):
        client.post("/api/v1/feedback", data=APP_FORM, headers=auth_headers_free)
    assert any("message_id=77" in r.getMessage() for r in caplog.records)
    assert not any("123:TEST" in r.getMessage() for r in caplog.records)


def test_sentry_breadcrumb_hides_bot_token():
    from backend.sentry_setup import scrub
    url = "https://api.telegram.org/bot8761921026:AAG-secret_x/sendMessage"
    event = {"breadcrumbs": {"values": [
        {"category": "httplib", "data": {"url": url}, "message": url},
    ]}}
    crumb = scrub(event)["breadcrumbs"]["values"][0]
    assert "AAG-secret_x" not in crumb["data"]["url"] and "AAG-secret_x" not in crumb["message"]
    assert crumb["data"]["url"] == "https://api.telegram.org/bot***/sendMessage"
