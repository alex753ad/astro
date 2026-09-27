#!/usr/bin/env bash
# diag_support.sh — почему обращение в поддержку не дошло до Telegram.
#
# Запуск на сервере (только чтение; последний шаг шлёт ОДНО тестовое
# сообщение в чат поддержки):
#   cd /opt/astro/app && git pull --ff-only && bash scripts/diag_support.sh
#
# Вывод дублируется в /opt/astro/diag/diag_support-<время>.log.
#
# ⚠️ У каждого `docker compose exec -T` стоит `</dev/null`: без него exec
# читает stdin и съедает всё, что идёт следом (так 27.09.2026 блок,
# вставленный в терминал, выполнил первую команду из пяти).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/diag_support-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

echo "== 1. ревизия схемы"
docker compose exec -T api alembic current </dev/null 2>&1 | tail -1

echo "== 2. последние обращения"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select f.id, f.created_at, f.screen, u.email, f.context from feedback f left join users u on u.id = f.user_id order by f.id desc limit 5;"' </dev/null

echo "== 3. логи api за 6 часов"
docker compose logs api --since 6h </dev/null 2>&1 | grep -iE "telegram|feedback|Обращение|support" | tail -40

echo "== 4. чат поддержки в api и worker"
echo "api:    $(docker compose exec -T api printenv TELEGRAM_SUPPORT_CHAT_ID </dev/null)"
echo "worker: $(docker compose exec -T worker printenv TELEGRAM_SUPPORT_CHAT_ID </dev/null)"

echo "== 5. тест тем же кодом, что шлёт обращения"
docker compose exec -T api python - <<'PYEOF'
import asyncio, json, logging, os, sys, urllib.error, urllib.parse, urllib.request
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
c = os.environ.get("TELEGRAM_SUPPORT_CHAT_ID", "")
print("token задан:", bool(t), " chat_id:", repr(c))
def call(m, **p):
    try:
        return json.load(urllib.request.urlopen("https://api.telegram.org/bot" + t + "/" + m, data=urllib.parse.urlencode(p).encode(), timeout=15))
    except urllib.error.HTTPError as e:
        return json.load(e)
    except Exception as e:
        return {"ok": False, "description": repr(e).replace(t, "***")}
print("bot:", call("getMe").get("result", {}).get("username"))
r = call("getChat", chat_id=c)
print("getChat:", r.get("ok"), (r.get("result") or {}).get("title") or (r.get("result") or {}).get("username"), r.get("description"))
from backend.notifications.telegram import send_support_message
print("send_support_message:", asyncio.run(send_support_message("Проверка: тест send_support_message с сервера (diag_support.sh)")))
PYEOF

echo "== конец. Лог: /opt/astro/$LOG"
