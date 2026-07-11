"""Web Push отправка через pywebpush + VAPID.

ENV:
  VAPID_PUBLIC_KEY   — публичный ключ (base64url), фронт получает через API
  VAPID_PRIVATE_KEY  — приватный ключ (raw base64url)
  VAPID_SUBJECT      — mailto:... или https://... (контакт для push-сервисов)
"""
from __future__ import annotations

import json
import logging
import os

from sqlalchemy.orm import Session

from backend.models import PushSubscription

logger = logging.getLogger("astro.push")


def vapid_public_key() -> str:
    return os.getenv("VAPID_PUBLIC_KEY", "")


def _vapid_private_key() -> str:
    return os.getenv("VAPID_PRIVATE_KEY", "")


def _vapid_subject() -> str:
    return os.getenv("VAPID_SUBJECT", "mailto:admin@astreatime.ru")


def send_web_push(sub: PushSubscription, payload: dict) -> bool:
    """Отправить один пуш. Возвращает True при успехе.

    При 404/410 (подписка мертва) бросает PushGone — вызывающий удаляет запись.
    """
    from pywebpush import webpush, WebPushException

    if not _vapid_private_key():
        logger.warning("VAPID_PRIVATE_KEY не задан — пуш не отправлен")
        return False

    subscription_info = {
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_vapid_private_key(),
            vapid_claims={"sub": _vapid_subject()},
            timeout=10,
        )
        return True
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushGone(sub.endpoint) from e
        logger.warning("Push failed (status=%s) endpoint=%s: %s", status, sub.endpoint[:40], e)
        return False
    except Exception as e:
        logger.warning("Push send error endpoint=%s: %s", sub.endpoint[:40], e)
        return False


class PushGone(Exception):
    """Подписка больше не действительна (404/410) — нужно удалить."""


def send_to_user(db: Session, user_id: str, payload: dict) -> int:
    """Отправить пуш на все устройства пользователя. Мёртвые подписки удаляются.

    Возвращает число успешных доставок.
    """
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    delivered = 0
    dirty = False
    for sub in subs:
        try:
            if send_web_push(sub, payload):
                delivered += 1
        except PushGone:
            db.delete(sub)
            dirty = True
    if dirty:
        db.commit()
    return delivered
