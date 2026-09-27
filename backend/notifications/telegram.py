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

# ⚠️ Токен бота — часть ПУТИ запроса (/bot<токен>/sendMessage), а httpx на
# уровне INFO пишет каждый запрос с полным URL. `main.py` ставит корню INFO,
# и 27.09.2026 токен оказался в `docker compose logs api` — и в выводе
# диагностики, который владелец вставил в чат. Уровень поднимается здесь, а
# не в main.py: этим модулем шлют и api, и worker (самопроверка), и beat.
logging.getLogger("httpx").setLevel(logging.WARNING)

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
            # Факт доставки: номер сообщения в чате. 27.09.2026 «не дошло»
            # разбиралось по логу, где было видно только «200 OK», — ни в
            # какой чат и каким сообщением, сказать было нечем.
            try:
                result = resp.json().get("result") or {}
            except ValueError:
                result = {}
            logger.info("Telegram: доставлено в чат %s, message_id=%s",
                        (result.get("chat") or {}).get("id", chat_id), result.get("message_id"))
            return True
    except Exception as e:
        # %r, а не %s: у сетевых исключений httpx (ConnectTimeout, ConnectError,
        # ReadTimeout) str() бывает ПУСТЫМ. 27.09.2026 лог на проде гласил
        # «Telegram support notify failed:» — и больше ничего: ни типа, ни
        # причины, разбор начался вслепую.
        # ⚠️ Токен вырезается: HTTPStatusError несёт URL запроса, а в нём
        # /bot<токен>/ — прежняя строка писала токен в лог на каждом 4xx.
        detail = repr(e).replace(token, "***")
        logger.warning("Telegram support notify failed: %s: %s", type(e).__name__, detail)
        return False
