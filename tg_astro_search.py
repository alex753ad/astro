"""
Поиск Telegram-каналов по астрологии и смежным темам.
Сохраняет результаты в CSV и выводит в консоль.

Установка:
    pip install telethon

Запуск:
    python tg_astro_search.py
"""

import asyncio
import csv
import json

from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel

# ── Настройки ──────────────────────────────────────────────
API_ID   = 34459491               # ← вставь api_id (число)
API_HASH = "6ed884d55382d388167e792b8884f554"              # ← вставь api_hash (строка)
PHONE    = "+79081978742"              # ← номер телефона: "+79991234567"
PASSWORD = "Hkm88spn!"              # ← пароль двухшаговой проверки (или оставь "")
SESSION  = "astro_search"

OUTPUT_CSV  = "astro_channels.csv"
OUTPUT_JSON = "astro_channels.json"

QUERIES = [
    "астрология", "astrology", "натальная карта", "гороскоп", "horoscope",
    "транзиты", "ведическая астрология", "джйотиш", "jyotish",
    "таро", "tarot", "таролог",
    "нумерология", "numerology",
    "эзотерика", "esoteric", "магия", "ведьма", "witchcraft",
    "астропсихология", "психология знаков", "знак зодиака",
]

MIN_SUBSCRIBERS = 100
# ──────────────────────────────────────────────────────────


async def search_channels(client, query: str) -> list[dict]:
    results = []
    try:
        found = await client(SearchRequest(q=query, limit=50))
        for chat in found.chats:
            if not isinstance(chat, Channel) or chat.megagroup:
                continue
            subs = getattr(chat, "participants_count", 0) or 0
            if subs < MIN_SUBSCRIBERS:
                continue
            results.append({
                "id": chat.id,
                "username": f"@{chat.username}" if chat.username else "—",
                "title": chat.title,
                "subscribers": subs,
                "query": query,
                "link": f"https://t.me/{chat.username}" if chat.username else "—",
            })
    except Exception as e:
        print(f"  [!] Ошибка при поиске '{query}': {e}")
    return results


def dedup(channels: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for ch in channels:
        if ch["id"] not in seen:
            seen.add(ch["id"])
            out.append(ch)
    return out


def save_csv(channels: list[dict], path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "username", "subscribers", "link", "query"])
        writer.writeheader()
        for ch in channels:
            writer.writerow({k: ch[k] for k in ["title", "username", "subscribers", "link", "query"]})
    print(f"✅ CSV сохранён: {path}")


def save_json(channels: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON сохранён: {path}")


def print_table(channels: list[dict]):
    print(f"\n{'─'*80}")
    print(f"{'НАЗВАНИЕ':<35} {'USERNAME':<22} {'ПОДПИСЧИКИ':>12}")
    print(f"{'─'*80}")
    for ch in sorted(channels, key=lambda x: x["subscribers"], reverse=True):
        print(f"{ch['title'][:34]:<35} {ch['username'][:21]:<22} {ch['subscribers']:>12,}")
    print(f"{'─'*80}")
    print(f"Итого: {len(channels)} уникальных каналов")


async def main():
    if not API_ID or not API_HASH or not PHONE:
        print("❌ Заполни API_ID, API_HASH и PHONE в начале скрипта!")
        return

    client = TelegramClient(SESSION, API_ID, API_HASH)

    # Автологин: передаём телефон и пароль, код из Telegram введёшь один раз
    await client.start(
        phone=lambda: PHONE,
        password=lambda: PASSWORD if PASSWORD else input("Пароль двухшаговой проверки: "),
    )

    print(f"✅ Авторизован\n🔍 Ищу каналы по {len(QUERIES)} запросам...\n")

    all_channels = []
    async with client:
        for i, query in enumerate(QUERIES, 1):
            print(f"[{i}/{len(QUERIES)}] '{query}' ...", end=" ", flush=True)
            found = await search_channels(client, query)
            print(f"{len(found)} каналов")
            all_channels.extend(found)
            await asyncio.sleep(2)

    unique = dedup(all_channels)
    print_table(unique)
    save_csv(unique, OUTPUT_CSV)
    save_json(unique, OUTPUT_JSON)


if __name__ == "__main__":
    asyncio.run(main())
