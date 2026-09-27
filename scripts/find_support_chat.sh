#!/usr/bin/env bash
# find_support_chat.sh — какой chat_id у @aristeatimesupport видит серверный бот.
#
# Только чтение: getChat, ничего не отправляет и .env не меняет.
#   cd /opt/astro/app && git pull --ff-only && bash scripts/find_support_chat.sh
#
# Повод (27.09.2026): бот добавлен в чат, а на -1004348383427 Telegram отвечает
# «chat not found». У обычной группы id вида -4348383427, приставка -100 — только
# у каналов и супергрупп; проверяются оба написания и имя чата.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/find_support_chat-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

docker compose exec -T api python - <<'PYEOF'
import json, os, urllib.error, urllib.parse, urllib.request
t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
def get_chat(cid):
    for attempt in range(3):
        try:
            r = json.load(urllib.request.urlopen("https://api.telegram.org/bot" + t + "/getChat",
                          data=urllib.parse.urlencode({"chat_id": cid}).encode(), timeout=30))
        except urllib.error.HTTPError as e:
            r = json.load(e)
        except Exception as e:
            r = {"ok": False, "description": type(e).__name__}
            continue
        break
    res = r.get("result") or {}
    return "OK  id=%s type=%s title=%s" % (res.get("id"), res.get("type"), res.get("title") or res.get("username")) if r.get("ok") else "нет: " + str(r.get("description"))
print("сейчас в .env:", repr(os.environ.get("TELEGRAM_SUPPORT_CHAT_ID", "")))
for cid in ("-1004348383427", "-4348383427", "@aristeatimesupport"):
    print("%-20s %s" % (cid, get_chat(cid)))
PYEOF

echo "== конец. Лог: /opt/astro/$LOG"
