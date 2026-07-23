"""Отправка сообщений в служебный Telegram-канал поддержки (обратная связь).

ENV:
  TELEGRAM_BOT_TOKEN        — токен бота (@BotFather), уже используется ботом пилота
  TELEGRAM_SUPPORT_CHAT_ID  — chat_id канала/чата поддержки (для каналов отрицательный, -100...)
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("astro.notifications.telegram")

_API_BASE = "https://api.telegram.org"


def _bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _support_chat_id() -> str:
    return os.getenv("TELEGRAM_SUPPORT_CHAT_ID", "")


async def send_support_message(text: str, photo_path: str | None = None) -> bool:
    """Отправить сообщение (и опционально фото) в служебный чат поддержки.

    Любая ошибка логируется и проглатывается — недоступность Telegram не должна
    ронять сохранение жалобы в БД. Возвращает True при успешной отправке.
    """
    token = _bot_token()
    chat_id = _support_chat_id()
    if not token or not chat_id:
        logger.warning("Telegram support notify skipped: TELEGRAM_BOT_TOKEN/TELEGRAM_SUPPORT_CHAT_ID не заданы")
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if photo_path:
                with open(photo_path, "rb") as f:
                    resp = await client.post(
                        f"{_API_BASE}/bot{token}/sendPhoto",
                        data={"chat_id": chat_id, "caption": text[:1024]},
                        files={"photo": f},
                    )
            else:
                resp = await client.post(
                    f"{_API_BASE}/bot{token}/sendMessage",
                    data={"chat_id": chat_id, "text": text[:4096]},
                )
            if resp.status_code >= 400:
                logger.warning("Telegram API response: %s", resp.text)
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.warning("Telegram support notify failed: %s", e)
        return False
