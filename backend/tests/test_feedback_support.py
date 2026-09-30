"""Обращение в поддержку из приложения (feedback/router.py).

* текст сигнала владельцу: номер аккаунта и email (для ответа), версия,
  телефон, текст ошибки; жалоба с веба — в прежнем виде;
* лимит: вошедший — по user_id, аноним — по IP (`feedback_key`);
* контекст пишется в БД и отдаётся админке; неудача Telegram обращение не
  теряет и уходит ошибкой (ERROR → Sentry).
"""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

from backend.auth.jwt import create_access_token
from backend.auth.rate_limits import feedback_key
from backend.feedback import router as fb


def _row(**kw):
    base = dict(screen="feed", url=None, message="Лента не грузится", user_agent="UA")
    base.update(kw)
    return SimpleNamespace(**base)


USER = SimpleNamespace(id="u-42", email="anna@example.com")
APP_FORM = {"screen": "feed", "message": "Лента не грузится", "app_version": "0.1.0 (abc1234)",
            "device": "SM-A515F, Android 13", "error_text": "На сервере сбой."}


# ── Текст сигнала ────────────────────────────────────────

def test_app_report_has_account_version_device_error():
    text = fb._format_report(_row(), USER, {"version": "0.1.0 (abc1234)", "device": "SM-A515F, Android 13",
                                            "error": "На сервере сбой."})
    assert text.startswith("Обращение в поддержку")
    for part in ("#u-42 anna@example.com", "Версия: 0.1.0 (abc1234)", "Телефон: SM-A515F, Android 13",
                 "Ошибка: На сервере сбой.", "Лента не грузится"):
        assert part in text


def test_app_report_without_error_has_no_error_line():
    text = fb._format_report(_row(), USER, {"version": "0.1.0", "device": "Android 10", "error": ""})
    assert "Ошибка" not in text


def test_web_report_unchanged_shape():
    text = fb._format_report(_row(url="/chart/1"), USER)
    assert text.startswith("Новая жалоба")
    assert "Устройство: UA" in text and "URL: /chart/1" in text


# ── Ключ лимита ──────────────────────────────────────────

def _request(token=None, ip="203.0.113.7"):
    headers = [(b"authorization", f"Bearer {token}".encode())] if token is not None else []
    return Request({"type": "http", "method": "POST", "path": "/api/v1/feedback",
                    "headers": headers, "client": (ip, 5000), "query_string": b""})


class TestFeedbackKey:
    def test_signed_in_user_keyed_by_id_not_ip(self):
        uid = "0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa"
        token = create_access_token(uid, "a@example.com")
        a = feedback_key(_request(token, ip="203.0.113.7"))
        b = feedback_key(_request(token, ip="198.51.100.9"))
        assert a == b == f"feedback:user:{uid}"

    def test_two_users_behind_one_nat_get_separate_buckets(self):
        a = feedback_key(_request(create_access_token("0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa", "a@x.ru")))
        b = feedback_key(_request(create_access_token("0f8c1a2b-2222-4444-8888-bbbbbbbbbbbb", "b@x.ru")))
        assert a != b

    def test_anonymous_keyed_by_ip(self):
        assert feedback_key(_request(None)) == "feedback:ip:203.0.113.7"

    def test_garbage_token_is_anonymous_not_new_bucket(self):
        """Мусор в заголовке не даёт нового ведра: ключ — тот же IP."""
        assert feedback_key(_request("garbage-1")) == feedback_key(_request("garbage-2")) \
            == "feedback:ip:203.0.113.7"

    def test_route_uses_this_key(self):
        src = open(fb.__file__, encoding="utf-8").read()
        assert '@limiter.limit("5/hour", key_func=feedback_key)' in src


# ── БД, админка, отказ Telegram ──────────────────────────

def test_context_saved_and_shown_to_admin(client, db, auth_headers_free, user_free):
    from backend.models import Feedback
    with patch.object(fb, "send_support_message", AsyncMock(return_value=True)):
        resp = client.post("/api/v1/feedback", data=APP_FORM, headers=auth_headers_free)
    assert resp.status_code == 201
    row = db.query(Feedback).one()
    assert row.user_id == user_free.id
    assert row.context == {"version": "0.1.0 (abc1234)", "device": "SM-A515F, Android 13",
                           "error": "На сервере сбой."}
    out = fb.FeedbackOut.model_validate(row)
    assert out.context["device"] == "SM-A515F, Android 13" and out.user_id == user_free.id


def test_web_complaint_has_no_context(client, db):
    from backend.models import Feedback
    with patch.object(fb, "send_support_message", AsyncMock(return_value=True)):
        client.post("/api/v1/feedback", data={"screen": "chart", "message": "x"})
    assert db.query(Feedback).one().context is None


def test_telegram_failure_keeps_row_and_logs_error(client, db, auth_headers_free, caplog):
    from backend.models import Feedback
    with caplog.at_level(logging.ERROR, logger="astro.feedback"), \
            patch.object(fb, "send_support_message", AsyncMock(return_value=False)):
        resp = client.post("/api/v1/feedback", data=APP_FORM, headers=auth_headers_free)
    assert resp.status_code == 201
    row = db.query(Feedback).one()
    assert any(r.levelno == logging.ERROR and f"#{row.id}" in r.getMessage() for r in caplog.records)


# ── Копия на почту: уходит всегда, независимо от Telegram ──

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def test_email_copy_sent_when_telegram_fails(client, db, auth_headers_free):
    email = AsyncMock(return_value=True)
    with patch.object(fb, "send_support_message", AsyncMock(return_value=False)), \
            patch.object(fb, "send_support_copy", email):
        resp = client.post("/api/v1/feedback", data=APP_FORM, headers=auth_headers_free)
    assert resp.status_code == 201
    email.assert_awaited_once()
    to, fid, text, shot, _ = email.await_args.args
    assert to == "carearistea@mail.ru" and fid == resp.json()["id"] and "Лента не грузится" in text
    assert shot is None


def test_email_copy_sent_when_telegram_raises(client, db):
    email = AsyncMock(return_value=True)
    with patch.object(fb, "send_support_message", AsyncMock(side_effect=RuntimeError("tg down"))), \
            patch.object(fb, "send_support_copy", email):
        client.post("/api/v1/feedback", data={"screen": "chart", "message": "x"})
    email.assert_awaited_once()


def test_email_copy_has_screenshot_when_telegram_fails(client, db):
    email = AsyncMock(return_value=True)
    with patch.object(fb, "send_support_message", AsyncMock(return_value=False)), \
            patch.object(fb, "send_support_copy", email):
        resp = client.post("/api/v1/feedback", data={"screen": "chart", "message": "x"},
                           files={"screenshot": ("s.png", PNG, "image/png")})
    assert resp.status_code == 201
    _, _, _, shot, filename = email.await_args.args
    assert shot == PNG and filename == "screenshot.png"


def test_email_failure_logged_and_telegram_still_sent(client, db, caplog):
    tg = AsyncMock(return_value=True)
    with caplog.at_level(logging.ERROR, logger="astro.feedback"), \
            patch.object(fb, "send_support_message", tg), \
            patch.object(fb, "send_support_copy", AsyncMock(return_value=False)):
        resp = client.post("/api/v1/feedback", data={"screen": "chart", "message": "x"})
    tg.assert_awaited_once()
    assert any("на почту" in r.getMessage() and f"#{resp.json()['id']}" in r.getMessage()
               for r in caplog.records)


async def test_too_big_screenshot_sent_without_attachment():
    from backend import email_service as es
    send = AsyncMock(return_value=True)
    with patch.object(es, "_send", send), patch.object(es, "SUPPORT_ATTACHMENT_MAX_BYTES", 10):
        await es.send_support_copy("a@b.c", 7, "текст", PNG)
    to, subject, html, attachments = send.await_args.args
    assert attachments is None and "слишком большой" in html and subject == "Обращение #7"


async def test_screenshot_attached_as_base64():
    import base64
    from backend import email_service as es
    send = AsyncMock(return_value=True)
    with patch.object(es, "_send", send):
        await es.send_support_copy("a@b.c", 7, "<b>", PNG, "screenshot.png")
    _, _, html, attachments = send.await_args.args
    assert attachments == [{"filename": "screenshot.png", "content": base64.b64encode(PNG).decode()}]
    assert "&lt;b&gt;" in html
