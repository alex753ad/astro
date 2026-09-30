"""bot/pilot_bot.py — Telegram-воркер входа в пилот.

Отдельный процесс (Railway worker). При /start:
  1) проверяет членство пользователя в ОБОИХ каналах (getChatMember);
  2) если подписан на оба — запрашивает у бэкенда одноразовую ссылку и шлёт её;
  3) иначе — просит подписаться, с кнопками на каналы.

Зависимости:  aiogram>=3.4  httpx
Запуск:       python -m bot.pilot_bot   (или через Procfile: worker: python -m bot.pilot_bot)

ENV:
  TELEGRAM_BOT_TOKEN   — токен бота (@BotFather). ПЕРЕВЫПУСТИТЬ, т.к. светился в чате.
  PILOT_CHANNEL_IDS    — id каналов через запятую, напр. "-1004475404200,-1001851972750"
  BACKEND_URL          — базовый URL бэкенда (Railway), напр. https://astro-production-abcc.up.railway.app
  INTERNAL_SECRET      — общий секрет для /api/v1/internal/*
  CHANNEL_LINKS        — (опц.) ссылки-приглашения через запятую для кнопок
  CHANNEL_NAMES        — (опц.) названия каналов через запятую, в том же
                          порядке что CHANNEL_LINKS; без неё кнопки подписаны
                          "Канал N"
"""
from __future__ import annotations

import asyncio
import logging
import os

import socket

import aiohttp
import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pilot_bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_IDS = [c.strip() for c in os.getenv("PILOT_CHANNEL_IDS", "").split(",") if c.strip()]
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")
CHANNEL_LINKS = [c.strip() for c in os.getenv("CHANNEL_LINKS", "").split(",") if c.strip()]
CHANNEL_NAMES = [c.strip() for c in os.getenv("CHANNEL_NAMES", "").split(",") if c.strip()]

_OK_STATUSES = {"member", "administrator", "creator"}

# Паузы перед повторами — как у сигналов (backend/notifications/telegram.py).
# Повтор только когда соединение не установилось: запрос до Telegram не
# дошёл, дубля ответа не будет. Таймаут чтения не повторяется.
_RETRY_PAUSES = (5, 30)
_CONNECT_ERRORS = (aiohttp.ClientConnectorError, aiohttp.ConnectionTimeoutError)


class _RetryOnConnect(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        for attempt, pause in enumerate((*_RETRY_PAUSES, None), 1):
            try:
                return await make_request(bot, method)
            except TelegramNetworkError as e:
                # aiogram заворачивает ошибки aiohttp в TelegramNetworkError;
                # что именно случилось — только в __cause__.
                if pause is None or not isinstance(e.__cause__, _CONNECT_ERRORS):
                    raise
                logger.warning("Telegram %s: нет соединения (%s), попытка %d, повтор через %d с",
                               type(method).__name__, type(e.__cause__).__name__, attempt, pause)
                await asyncio.sleep(pause)


class _Session(AiohttpSession):
    """Отдельный таймаут на установку соединения — 5 с (как у сигналов,
    backend/notifications/telegram.py, `_client`; причина там же).

    aiogram передаёт в aiohttp только общий таймаут запроса числом (у
    getUpdates — 60+ с), и повисшее соединение ждало его целиком, прежде
    чем сработает повтор. sock_connect aiohttp превращает в
    ConnectionTimeoutError — он в `_CONNECT_ERRORS`, то есть повторяется.
    ClientTimeout вместо числа aiogram (проверено на 3.27/3.30) отдаёт в
    session.post как есть.
    """

    async def make_request(self, bot, method, timeout=None):
        total = self.timeout if timeout is None else timeout
        return await super().make_request(bot, method, aiohttp.ClientTimeout(total=total, sock_connect=5))


def _session() -> AiohttpSession:
    """Сессия aiogram — только по IPv6.

    ⚠️ С сервера api.telegram.org закрыт по IPv4 (30.09.2026,
    scripts/check_telegram.sh) — та же причина, что у сигналов в
    backend/notifications/telegram.py. У aiogram свой клиент (aiohttp), и
    правка там его не касается. family=AF_INET6 — aiohttp берёт из DNS только
    AAAA. `_connector_init` — не публичный API aiogram (проверено на 3.30):
    при обновлении aiogram убедиться, что словарь ещё передаётся в
    TCPConnector. Откроют IPv4 — строку можно убрать.
    """
    session = _Session()
    session._connector_init["family"] = socket.AF_INET6
    session.middleware(_RetryOnConnect())
    return session


bot = Bot(BOT_TOKEN, session=_session())
dp = Dispatcher()


async def _is_member(user_id: int, channel_id: str) -> bool:
    try:
        member = await asyncio.wait_for(
            bot.get_chat_member(chat_id=channel_id, user_id=user_id), timeout=5
        )
        return member.status in _OK_STATUSES
    except Exception as e:
        # частая причина: бот не админ в канале, либо неверный id; также ловит
        # asyncio.TimeoutError — без него сетевая заминка вешала /start на ~60с
        logger.warning("getChatMember failed channel=%s: %s", channel_id, e)
        return False


async def _request_link(tg_user_id: int) -> tuple[int, dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{BACKEND_URL}/api/v1/internal/pilot-token",
            headers={"X-Internal-Secret": INTERNAL_SECRET},
            json={"tg_user_id": str(tg_user_id)},
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {}


def _subscribe_keyboard() -> InlineKeyboardMarkup | None:
    if not CHANNEL_LINKS:
        return None
    rows = [
        [InlineKeyboardButton(
            text=CHANNEL_NAMES[i] if i < len(CHANNEL_NAMES) else f"Канал {i+1}",
            url=link,
        )]
        for i, link in enumerate(CHANNEL_LINKS)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
async def on_start(message: Message):
    uid = message.from_user.id

    # 1) проверка подписки на все каналы
    checks = await asyncio.gather(*[_is_member(uid, cid) for cid in CHANNEL_IDS])
    if not CHANNEL_IDS or not all(checks):
        await message.answer(
            "Чтобы открыть бесплатный месяц Aristea, подпишись на оба канала, "
            "а затем снова напиши /start.",
            reply_markup=_subscribe_keyboard(),
        )
        return

    # 2) запрос одноразовой ссылки у бэкенда
    status, data = await _request_link(uid)
    if status == 409:
        await message.answer("Бесплатный месяц уже активирован — повторно нельзя.")
        return
    if status != 200 or "claim_url" not in data:
        await message.answer("Не удалось создать ссылку. Попробуй чуть позже.")
        logger.warning("pilot-token issue failed: status=%s data=%s", status, data)
        return

    # 3) выдаём ссылку
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть Aristea Premium", url=data["claim_url"])]
    ])
    await message.answer(
        "Готово! Нажми кнопку ниже — откроется Aristea, и мы включим тебе "
        "Premium на 30 дней.\n\nСсылка одноразовая и действует ограниченное время.\n\n"
        "Доступ к скачиванию PDF в приложении открыт.",
        reply_markup=kb,
    )


async def main():
    if not CHANNEL_IDS:
        logger.warning("PILOT_CHANNEL_IDS пуст — проверка подписки всегда провалится.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
