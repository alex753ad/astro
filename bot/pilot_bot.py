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
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pilot_bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_IDS = [c.strip() for c in os.getenv("PILOT_CHANNEL_IDS", "").split(",") if c.strip()]
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")
CHANNEL_LINKS = [c.strip() for c in os.getenv("CHANNEL_LINKS", "").split(",") if c.strip()]

_OK_STATUSES = {"member", "administrator", "creator"}

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


async def _is_member(user_id: int, channel_id: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in _OK_STATUSES
    except Exception as e:
        # частая причина: бот не админ в канале, либо неверный id
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
    rows = [[InlineKeyboardButton(text=f"Канал {i+1}", url=link)]
            for i, link in enumerate(CHANNEL_LINKS)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
async def on_start(message: Message):
    uid = message.from_user.id

    # 1) проверка подписки на все каналы
    checks = await asyncio.gather(*[_is_member(uid, cid) for cid in CHANNEL_IDS])
    if not CHANNEL_IDS or not all(checks):
        await message.answer(
            "Чтобы открыть бесплатный месяц Astrea, подпишитесь на оба канала, "
            "а затем снова напишите /start.",
            reply_markup=_subscribe_keyboard(),
        )
        return

    # 2) запрос одноразовой ссылки у бэкенда
    status, data = await _request_link(uid)
    if status == 409:
        await message.answer("Вы уже активировали бесплатный месяц — повторно нельзя.")
        return
    if status != 200 or "claim_url" not in data:
        await message.answer("Не удалось создать ссылку. Попробуйте позже.")
        logger.warning("pilot-token issue failed: status=%s data=%s", status, data)
        return

    # 3) выдаём ссылку
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть Astrea Premium", url=data["claim_url"])]
    ])
    await message.answer(
        "Готово! Нажмите кнопку ниже — откроется Astrea, и мы включим вам "
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
