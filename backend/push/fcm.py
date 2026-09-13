"""Отправка пушей в мобильное приложение через FCM HTTP v1.

Зачем вообще, если веб-пуши работают. Внутри Android WebView веб-пуш
недоступен, а локальные уведомления на устройстве не будят телефон: без
разрешения на точный будильник Android ставит НЕточный, и он ждёт, пока
устройство проснётся само (разбор — docs/HISTORY-push.md). Высокоприоритетное
сообщение FCM — единственный механизм, который прошивки будят намеренно.

ENV:
  FCM_PROJECT_ID           — идентификатор проекта Firebase
  FCM_SERVICE_ACCOUNT_B64  — JSON сервис-аккаунта, base64 одной строкой

⚠️ Легаси-ключ сервера (`Authorization: key=...`) больше не работает: Google
выключил старый API. Только v1, только OAuth2-токен из сервис-аккаунта.

⚠️ Берём `google-auth` + уже имеющийся `httpx`, а не `firebase-admin`. Тот
тянет за собой половину google-cloud ради одного HTTP-вызова, и каждый такой
пакет — это ещё одна строка в `pip-audit` и ещё одна причина, по которой
однажды не соберётся образ.

⚠️ Отсутствие настроек — НЕ ошибка. Веб-пуши обязаны продолжать работать на
сервере, где FCM не настроен вовсе: функции ниже в этом случае возвращают
«не отправлено», а не бросают. Прод-гвард на эти переменные не ставится
намеренно — иначе включение мобильного канала стало бы условием запуска.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time

import httpx
from sqlalchemy.orm import Session

from backend.models import DeviceToken
from backend.push.sender import PushGone

logger = logging.getLogger("astro.push")

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_TTL_GUARD = 120  # секунд до истечения, когда токен уже считаем протухшим

# Кэш access-token. ⚠️ Без него каждый пуш начинался бы с подписи JWT и обмена
# его на токен — а тик планировщика проходит по всем подписанным подряд, то
# есть на сотне пользователей это сотня лишних round-trip'ов к Google.
_token_lock = threading.Lock()
_access_token: str | None = None
_access_token_exp: float = 0.0


def project_id() -> str:
    return os.getenv("FCM_PROJECT_ID", "")


def _service_account() -> dict | None:
    raw = os.getenv("FCM_SERVICE_ACCOUNT_B64", "")
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw))
    except Exception as e:
        # Битый секрет — это отказ настройки, а не события: он не пройдёт и в
        # следующий раз, поэтому кричим один раз внятно, а не молчим.
        logger.error("FCM_SERVICE_ACCOUNT_B64 не разбирается: %s", e)
        return None


def configured() -> bool:
    """Настроен ли мобильный канал. Ответ «нет» — нормальное состояние."""
    return bool(project_id()) and _service_account() is not None


def _fetch_access_token() -> str | None:
    info = _service_account()
    if not info:
        return None
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError:
        logger.error("google-auth не установлен — мобильные пуши отключены")
        return None

    try:
        creds = service_account.Credentials.from_service_account_info(info, scopes=[_SCOPE])
        creds.refresh(Request())
        global _access_token, _access_token_exp
        _access_token = creds.token
        # У google-auth `expiry` — naive UTC; сравнивать с ним арифметикой не
        # надо, достаточно собственного срока: токен живёт час.
        _access_token_exp = time.time() + 3600
        return _access_token
    except Exception as e:
        logger.warning("FCM: не удалось получить access-token: %s", e)
        return None


def _access() -> str | None:
    global _access_token
    with _token_lock:
        if _access_token and time.time() < _access_token_exp - _TOKEN_TTL_GUARD:
            return _access_token
        return _fetch_access_token()


def send_fcm(token: str, payload: dict) -> bool:
    """Один пуш на одно устройство. True — доставлено.

    При мёртвом токене бросает PushGone — тем же контрактом, что и веб-пуш,
    чтобы вызывающему не пришлось различать транспорты.
    """
    if not configured():
        return False
    access = _access()
    if not access:
        return False

    body = {
        "message": {
            "token": token,
            "notification": {
                "title": payload.get("title", "✦ Aristea"),
                "body": payload.get("body", ""),
            },
            "android": {
                # ⚠️ high — не «погромче», а единственный приоритет, который
                # выводит устройство из Doze. Ради этого весь канал и заводился.
                "priority": "high",
                "notification": {"channel_id": "aristea-events"},
            },
            # Данные доезжают до приложения и при показе системой (читаются при
            # тапе). `url` — куда вести, `keys` — какие события внутри: по ним
            # приложение гасит своё локальное уведомление о том же событии.
            # Всё строками: FCM других типов в `data` не принимает.
            "data": {
                "url": str(payload.get("url", "/")),
                "keys": ",".join(payload.get("keys", []) or []),
            },
        }
    }

    url = f"https://fcm.googleapis.com/v1/projects/{project_id()}/messages:send"
    try:
        resp = httpx.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {access}"},
            timeout=10,
        )
    except Exception as e:
        logger.warning("FCM send error token=%s: %s", token[:12], e)
        return False

    if resp.status_code == 200:
        return True

    # 404 UNREGISTERED — приложение удалено или токен ротирован.
    # 400 INVALID_ARGUMENT по полю token — токен от другого проекта Firebase.
    # И то, и другое лечится удалением записи, а не повтором.
    if resp.status_code == 404 or (resp.status_code == 400 and "token" in resp.text.lower()):
        raise PushGone(token)

    logger.warning("FCM failed (status=%s) token=%s: %s", resp.status_code, token[:12], resp.text[:200])
    return False


def send_to_devices(db: Session, user_id: str, payload: dict) -> int:
    """Все устройства пользователя. Мёртвые токены удаляются.

    Форма и контракт скопированы с `send_to_user` из sender.py намеренно: два
    транспорта должны выглядеть одинаково снаружи, иначе диспетчер обрастёт
    условиями, а вместе с ними и местами, где один из каналов молча выпадет.
    """
    if not configured():
        return 0

    rows = db.query(DeviceToken).filter(DeviceToken.user_id == user_id).all()
    delivered = 0
    dirty = False
    for row in rows:
        try:
            if send_fcm(row.token, payload):
                delivered += 1
        except PushGone:
            db.delete(row)
            dirty = True
    if dirty:
        db.commit()
    return delivered
