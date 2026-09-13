"""Мобильный канал доставки (FCM HTTP v1) и его стык с веб-пушами.

Что здесь закрывается и почему именно это:

1. **Отсутствие настроек — не ошибка.** На сервере, где FCM не настроен,
   веб-пуши обязаны продолжать работать. Прод-гварда на эти переменные нет
   намеренно, значит единственное, что удерживает инвариант, — тест.

2. **Суммарный счёт доставок.** По возвращённому числу `_process_user`
   решает, отмечать ли событие в `push_sent_log`. Вернуть только веб-доставки
   значило бы не отметить доставленное в приложение — и отправить его заново
   следующим тиком, каждые 15 минут, пока человек не удалит приложение.

3. **Мёртвый токен удаляется, а не копится.** Тот же контракт `PushGone`, что
   у веб-пуша: снаружи транспорты должны вести себя одинаково.

4. **`keys` доезжают до устройства.** На них держится дедуп между каналами:
   приложение гасит своё локальное уведомление о том же событии. Сопоставление
   идёт по ключу `kind:ref`, а не по тексту — привязываться к формулировкам
   сервера в этом проекте запрещено отдельно.
"""
from __future__ import annotations

import base64
import json

import pytest

from backend.models import DeviceToken, PushSubscription
from backend.push import fcm
from backend.push.sender import PushGone, send_to_user


SERVICE_ACCOUNT = base64.b64encode(json.dumps({
    "type": "service_account",
    "project_id": "aristea-test",
    "private_key_id": "x",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
    "client_email": "fcm@aristea-test.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}).encode()).decode()


@pytest.fixture
def fcm_env(monkeypatch):
    """Настроенный канал с подделанным access-token.

    Токен подделывается на уровне `_access`, а не сети: настоящий обмен JWT
    требует валидного ключа RSA, а проверяем мы не подпись google-auth, а свою
    сборку запроса и разбор ответа.
    """
    monkeypatch.setenv("FCM_PROJECT_ID", "aristea-test")
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT_B64", SERVICE_ACCOUNT)
    monkeypatch.setattr(fcm, "_access", lambda: "ya29.fake")
    return True


class _Resp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def _device(db, user, token="tok-1"):
    row = DeviceToken(user_id=user.id, token=token, platform="android")
    db.add(row)
    db.commit()
    return row


class TestNotConfigured:
    """Ненастроенный FCM молчит и никому не мешает."""

    def test_configured_is_false_without_env(self, monkeypatch):
        monkeypatch.delenv("FCM_PROJECT_ID", raising=False)
        monkeypatch.delenv("FCM_SERVICE_ACCOUNT_B64", raising=False)
        assert fcm.configured() is False

    def test_send_to_devices_returns_zero_and_touches_no_network(self, db, user_free, monkeypatch):
        monkeypatch.delenv("FCM_PROJECT_ID", raising=False)
        monkeypatch.delenv("FCM_SERVICE_ACCOUNT_B64", raising=False)
        _device(db, user_free)

        def boom(*a, **k):  # pragma: no cover — срабатывание означает провал
            raise AssertionError("ненастроенный FCM полез в сеть")

        monkeypatch.setattr(fcm.httpx, "post", boom)
        assert fcm.send_to_devices(db, user_free.id, {"title": "т", "body": "б"}) == 0

    def test_broken_secret_is_not_configured(self, monkeypatch):
        monkeypatch.setenv("FCM_PROJECT_ID", "aristea-test")
        monkeypatch.setenv("FCM_SERVICE_ACCOUNT_B64", "не-base64-и-не-json")
        assert fcm.configured() is False


class TestRequestShape:
    """Что именно уходит в FCM."""

    def test_high_priority_channel_and_keys(self, db, user_free, fcm_env, monkeypatch):
        sent = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            sent["url"] = url
            sent["body"] = json
            sent["headers"] = headers
            return _Resp(200)

        monkeypatch.setattr(fcm.httpx, "post", fake_post)
        _device(db, user_free)

        n = fcm.send_to_devices(db, user_free.id, {
            "title": "♄ Сатурн", "body": "Проверка", "url": "/planner",
            "keys": ["transit:a", "moon:b"],
        })

        assert n == 1
        msg = sent["body"]["message"]
        assert "aristea-test" in sent["url"]
        assert sent["headers"]["Authorization"] == "Bearer ya29.fake"
        # high — не «погромче», а единственный приоритет, выводящий устройство
        # из Doze. Ради этого канал и заводился.
        assert msg["android"]["priority"] == "high"
        assert msg["android"]["notification"]["channel_id"] == "aristea-events"
        assert msg["notification"]["title"] == "♄ Сатурн"
        # Ключи — строкой: FCM в `data` других типов не принимает.
        assert msg["data"]["keys"] == "transit:a,moon:b"
        assert msg["data"]["url"] == "/planner"

    def test_missing_keys_do_not_break_the_send(self, db, user_free, fcm_env, monkeypatch):
        """Пилотные рассылки зовут тот же шов и ключей не передают."""
        monkeypatch.setattr(fcm.httpx, "post", lambda *a, **k: _Resp(200))
        _device(db, user_free)
        assert fcm.send_to_devices(db, user_free.id, {"title": "т", "body": "б"}) == 1


class TestDeadTokens:
    def test_unregistered_token_is_deleted(self, db, user_free, fcm_env, monkeypatch):
        monkeypatch.setattr(fcm.httpx, "post", lambda *a, **k: _Resp(404, "UNREGISTERED"))
        _device(db, user_free)

        assert fcm.send_to_devices(db, user_free.id, {"title": "т", "body": "б"}) == 0
        assert db.query(DeviceToken).filter(DeviceToken.user_id == user_free.id).count() == 0

    def test_foreign_project_token_is_deleted(self, db, user_free, fcm_env, monkeypatch):
        monkeypatch.setattr(
            fcm.httpx, "post",
            lambda *a, **k: _Resp(400, '{"error":{"message":"Invalid registration token"}}'),
        )
        _device(db, user_free)
        assert fcm.send_to_devices(db, user_free.id, {"title": "т", "body": "б"}) == 0
        assert db.query(DeviceToken).count() == 0

    def test_server_error_keeps_the_token(self, db, user_free, fcm_env, monkeypatch):
        """503 — это «попробуйте позже», а не «токен мёртв»."""
        monkeypatch.setattr(fcm.httpx, "post", lambda *a, **k: _Resp(503, "backend error"))
        _device(db, user_free)
        assert fcm.send_to_devices(db, user_free.id, {"title": "т", "body": "б"}) == 0
        assert db.query(DeviceToken).count() == 1


class TestDispatcher:
    """Шов send_to_user: один вызов — оба канала."""

    def test_delivery_count_sums_both_channels(self, db, user_free, fcm_env, monkeypatch):
        db.add(PushSubscription(
            user_id=user_free.id, endpoint="https://push.example/ep1", p256dh="k", auth="a",
        ))
        db.commit()
        _device(db, user_free)

        monkeypatch.setattr("backend.push.sender.send_web_push", lambda sub, payload: True)
        monkeypatch.setattr(fcm.httpx, "post", lambda *a, **k: _Resp(200))

        # ⚠️ Если бы функция возвращала только веб-доставки, `_process_user` не
        # отметил бы событие в push_sent_log и отправил бы его заново.
        assert send_to_user(db, user_free.id, {"title": "т", "body": "б", "keys": ["k:1"]}) == 2

    def test_mobile_only_user_still_counts(self, db, user_free, fcm_env, monkeypatch):
        _device(db, user_free)
        monkeypatch.setattr(fcm.httpx, "post", lambda *a, **k: _Resp(200))
        assert send_to_user(db, user_free.id, {"title": "т", "body": "б"}) == 1

    def test_web_only_user_unaffected_by_unconfigured_fcm(self, db, user_free, monkeypatch):
        monkeypatch.delenv("FCM_PROJECT_ID", raising=False)
        monkeypatch.delenv("FCM_SERVICE_ACCOUNT_B64", raising=False)
        db.add(PushSubscription(
            user_id=user_free.id, endpoint="https://push.example/ep2", p256dh="k", auth="a",
        ))
        db.commit()
        monkeypatch.setattr("backend.push.sender.send_web_push", lambda sub, payload: True)
        assert send_to_user(db, user_free.id, {"title": "т", "body": "б"}) == 1

    def test_dead_web_subscription_still_deleted(self, db, user_free, monkeypatch):
        """Регрессия на порядок: FCM-ветка не должна обойти чистку веб-подписок."""
        db.add(PushSubscription(
            user_id=user_free.id, endpoint="https://push.example/ep3", p256dh="k", auth="a",
        ))
        db.commit()

        def gone(sub, payload):
            raise PushGone(sub.endpoint)

        monkeypatch.setattr("backend.push.sender.send_web_push", gone)
        send_to_user(db, user_free.id, {"title": "т", "body": "б"})
        assert db.query(PushSubscription).count() == 0


class TestDeviceEndpoints:
    def test_token_moves_to_the_new_user_instead_of_doubling(
        self, client, db, user_free, user_pro, auth_headers_free, auth_headers_pro,
    ):
        """Один телефон — одна запись.

        ⚠️ Иначе прежний владелец телефона продолжал бы получать уведомления
        по чужой карте: токен принадлежит установленному приложению, а не
        аккаунту.
        """
        body = {"token": "same-device", "platform": "android"}
        assert client.post("/api/v1/push/device", json=body, headers=auth_headers_free).status_code == 200
        assert client.post("/api/v1/push/device", json=body, headers=auth_headers_pro).status_code == 200

        rows = db.query(DeviceToken).filter(DeviceToken.token == "same-device").all()
        assert len(rows) == 1
        assert rows[0].user_id == user_pro.id

    def test_empty_token_rejected(self, client, auth_headers_free):
        resp = client.post("/api/v1/push/device", json={"token": "  "}, headers=auth_headers_free)
        assert resp.status_code == 422

    def test_forget_removes_only_own_token(
        self, client, db, user_free, user_pro, auth_headers_free, auth_headers_pro,
    ):
        client.post("/api/v1/push/device", json={"token": "mine"}, headers=auth_headers_free)
        client.post("/api/v1/push/device", json={"token": "theirs"}, headers=auth_headers_pro)

        resp = client.request(
            "DELETE", "/api/v1/push/device",
            json={"token": "theirs"}, headers=auth_headers_free,
        )
        assert resp.status_code == 200
        # Чужой токен не тронут: удаление ограничено своим user_id.
        assert db.query(DeviceToken).filter(DeviceToken.token == "theirs").count() == 1
