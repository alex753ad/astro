#!/usr/bin/env bash
# check_support_bot.sh — тот ли бот в токене сервера, что в админах канала
# поддержки, и проходит ли отправка по @имени и по числовому id.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_support_bot.sh
#
# Отправляет в канал НЕ БОЛЕЕ двух тестовых сообщений (шаги 4 и 5), .env не
# меняет. Повод (27.09.2026): getChat по «@aristeatimesupport» отдаёт канал
# с id -1004348383427, а по самому этому числу — «chat not found».
#
# Шаги 6–8 (30.09.2026) — доходит ли до Telegram сам бот (контейнер `bot`,
# aiogram): с сервера api.telegram.org закрыт по IPv4, у бота свой клиент
# aiohttp, переведён на IPv6 отдельно от сигналов (bot/pilot_bot.py,
# `_session`). Шаг 7 — getMe, сообщений не шлёт; сравнивает сессию бота и IPv4.
# ⚠️ `</dev/null` у docker compose — иначе съедает stdin (см. diag_support.sh).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_support_bot-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

docker compose exec -T api python - <<'PYEOF'
import json, os, urllib.error, urllib.parse, urllib.request
t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CH = "@aristeatimesupport"
NUM = os.environ.get("TELEGRAM_SUPPORT_CHAT_ID", "")
def call(m, **p):
    for attempt in range(3):
        try:
            return json.load(urllib.request.urlopen("https://api.telegram.org/bot" + t + "/" + m,
                             data=urllib.parse.urlencode(p).encode(), timeout=30))
        except urllib.error.HTTPError as e:
            return json.load(e)
        except Exception as e:
            last = {"ok": False, "description": type(e).__name__}
    return last
def err(r):
    return "ОШИБКА: " + str(r.get("description"))

me = call("getMe").get("result") or {}
print("== 1. бот из токена:", "@" + str(me.get("username")), "id=" + str(me.get("id")))

r = call("getChatAdministrators", chat_id=CH)
print("== 2. админы", CH + ":")
if r.get("ok"):
    for a in r["result"]:
        u = a.get("user") or {}
        print("   @%s id=%s bot=%s status=%s can_post=%s" % (u.get("username"), u.get("id"), u.get("is_bot"),
              a.get("status"), a.get("can_post_messages")))
else:
    print("  ", err(r))

r = call("getChatMember", chat_id=CH, user_id=me.get("id"))
res = r.get("result") or {}
print("== 3. бот из токена в", CH + ":", ("status=%s can_post=%s" % (res.get("status"), res.get("can_post_messages"))) if r.get("ok") else err(r))

r = call("sendMessage", chat_id=CH, text="Проверка 1/2: отправка по @имени (check_support_bot.sh)")
print("== 4. sendMessage chat_id=" + CH + ":", ("OK, chat.id=%s" % (r["result"]["chat"]["id"])) if r.get("ok") else err(r))

r = call("sendMessage", chat_id=NUM, text="Проверка 2/2: отправка по числовому id (check_support_bot.sh)")
print("== 5. sendMessage chat_id=" + repr(NUM) + ":", "OK" if r.get("ok") else err(r))
print("   repr числового id из .env:", repr(NUM), "длина", len(NUM))
PYEOF

echo "== 6. контейнер bot"
docker compose ps bot </dev/null

echo "== 7. из контейнера bot: getMe сессией бота и, для сравнения, по IPv4"
docker compose exec -T bot python - </dev/null <<'PYEOF'
import asyncio, socket, time
import aiogram, aiohttp
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
import bot.pilot_bot as pb

print("aiogram", aiogram.__version__, "aiohttp", aiohttp.__version__)
print("family в сессии бота:", pb.bot.session._connector_init.get("family"), "(AF_INET6 =", int(socket.AF_INET6), ")")

async def probe(name, b):
    t = time.monotonic()
    try:
        me = await b.get_me(request_timeout=15)
        print(f"{name}: OK @{me.username} за {time.monotonic() - t:.2f}с")
    except Exception as e:
        print(f"{name}: {type(e).__name__}: {e} (причина {type(e.__cause__).__name__}) за {time.monotonic() - t:.2f}с")
    finally:
        await b.session.close()

async def main():
    await probe("сессия бота (IPv6, с повтором)", pb.bot)
    s4 = AiohttpSession()
    s4._connector_init["family"] = socket.AF_INET
    await probe("IPv4 без повтора", Bot(pb.BOT_TOKEN, session=s4))

asyncio.run(main())
PYEOF

echo "== 8. лог бота за сутки: запуск, сетевые сбои, повторы"
docker compose logs bot --since 24h --timestamps </dev/null 2>&1 \
  | grep -E "Start polling|Run polling|нет соединения|NetworkError|Failed to fetch|Traceback|Error" | tail -25

echo "== конец. Лог: /opt/astro/$LOG"
