"""Отправка сообщений в служебный Telegram-канал поддержки (обратная связь).

ENV:
  TELEGRAM_BOT_TOKEN        — токен бота (@BotFather), уже используется ботом пилота
  TELEGRAM_SUPPORT_CHAT_ID  — chat_id канала/чата поддержки (для каналов отрицательный, -100...)
"""
from __future__ import annotations

import asyncio
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

# Паузы перед повторами, когда соединение не установилось (решение владельца
# 30.09.2026). Повтор — только на ConnectTimeout/ConnectError: запрос до
# Telegram не дошёл, дубля в чате не будет. ReadTimeout не повторяется —
# сообщение могло уже лечь в чат.
_RETRY_PAUSES = (5, 30)


def _client() -> httpx.AsyncClient:
    """Клиент к Telegram — только по IPv6.

    ⚠️ 30.09.2026 с сервера api.telegram.org закрыт по IPv4 (таймаут на
    каждом соединении) и открыт по IPv6 (0,14 с) — scripts/check_telegram.sh.
    httpx идёт по адресам из DNS по очереди, IPv4 первым, и ждёт на нём весь
    таймаут: каждая отправка стоила 15 с, а утренняя самопроверка 30.09 не
    дошла вовсе. local_address="::" привязывает сокет к IPv6 — IPv4 не
    пробуется. Пропадёт IPv6 у сервера — отправка встанет совсем; по IPv4 она
    сейчас не работает всё равно. Откроют IPv4 — эту строку можно убрать,
    проверка тем же скриптом.
    """
    return httpx.AsyncClient(timeout=15.0, transport=httpx.AsyncHTTPTransport(local_address="::"))


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

    for attempt, pause in enumerate((*_RETRY_PAUSES, None), 1):
        try:
            return await _send_once(token, chat_id, text, photo_path)
        except (httpx.ConnectTimeout, httpx.ConnectError) as e:
            if pause is None:
                _log_failure(e, token)
                return False
            logger.warning("Telegram: нет соединения (%s), попытка %d, повтор через %d с",
                           type(e).__name__, attempt, pause)
            await asyncio.sleep(pause)
        except Exception as e:
            _log_failure(e, token)
            return False
    return False  # недостижимо: последняя попытка выходит выше


async def _send_once(token: str, chat_id: str, text: str, photo_path: str | None) -> bool:
    async with _client() as client:
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


def _log_failure(e: Exception, token: str) -> None:
    # %r, а не %s: у сетевых исключений httpx (ConnectTimeout, ConnectError,
    # ReadTimeout) str() бывает ПУСТЫМ. 27.09.2026 лог на проде гласил
    # «Telegram support notify failed:» — и больше ничего: ни типа, ни
    # причины, разбор начался вслепую.
    # ⚠️ Токен вырезается: HTTPStatusError несёт URL запроса, а в нём
    # /bot<токен>/ — прежняя строка писала токен в лог на каждом 4xx.
    detail = repr(e).replace(token, "***")
    logger.warning("Telegram support notify failed: %s: %s", type(e).__name__, detail)
