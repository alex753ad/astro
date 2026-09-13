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
    return os.getenv("VAPID_SUBJECT", "mailto:admin@aristeatime.ru")


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
    """Отправить пуш во ВСЕ каналы пользователя. Мёртвые адреса удаляются.

    Единственный шов между «что сказать» и «как доставить». Его зовут все
    четыре потребителя — тик планировщика, кнопка «Отправить тест» и две
    рассылки пилотной программы, — поэтому мобильный канал подключён здесь и
    достался им всем сразу, без правок в отборе, текстах и дедупе.

    Возвращает СУММАРНОЕ число успешных доставок по всем каналам.

    ⚠️ Число это не для статистики: в `_process_user` по нему решается,
    отмечать ли событие в `push_sent_log`. Вернуть только веб-доставки значило
    бы не отметить событие, доставленное в приложение, — и следующий тик
    отправил бы его заново.

    ⚠️ «Все каналы», а не «лучший из»: у человека с браузерной подпиской И
    приложением уведомление придёт дважды. Это решение владельца 13.09.2026 и
    продолжение уже действующей конвенции — веб и сегодня шлёт на каждую
    подписку отдельно, то есть два браузера дают два пуша. Дедуп между
    каналами живёт НА УСТРОЙСТВЕ (см. docs/HISTORY-push.md): приложение,
    получившее токен FCM, не планирует своих локальных уведомлений.
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

    # Импорт внутри функции: fcm.py импортирует PushGone отсюда, и на уровне
    # модуля это был бы цикл.
    from backend.push.fcm import send_to_devices

    return delivered + send_to_devices(db, user_id, payload)
