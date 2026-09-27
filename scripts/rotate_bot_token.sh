#!/usr/bin/env bash
# rotate_bot_token.sh — заменить токен @Aristeatimebot на сервере после /revoke.
#
# Порядок:
#   1. @BotFather → /revoke → @Aristeatimebot → скопировать НОВЫЙ токен.
#      С этого момента старый не работает, и сервер ничего не отправит,
#      пока не выполнен шаг 2.
#   2. cd /opt/astro/app && git pull --ff-only && bash scripts/rotate_bot_token.sh
#   3. Uptime Kuma → Settings → Notifications: вписать новый токен руками
#      (там свой экземпляр, этот скрипт его не трогает).
#
# Что делает: спрашивает токен скрытым вводом (не попадает ни в терминал, ни в
# историю, ни в аргументы процессов) → getMe: это ровно @Aristeatimebot →
# копия .env → замена ОДНОЙ строки TELEGRAM_BOT_TOKEN → пересоздание api,
# worker, beat, bot (restart env_file не перечитывает) → getMe и тестовое
# сообщение в канал поддержки изнутри api. Меняет .env — запускать только
# осознанно, после /revoke.

set -uo pipefail
EXPECTED="Aristeatimebot"
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/rotate_bot_token-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
die() { echo "СТОП: $*"; echo "== конец (с ошибкой). Лог: /opt/astro/$LOG"; exit 1; }

read -rs -p "Новый токен @$EXPECTED из @BotFather: " TOKEN </dev/tty; echo
[ -n "$TOKEN" ] || die "токен пуст"

# Токен уходит в python через stdin, а не аргументом: аргументы видны в ps.
NAME=$(printf '%s' "$TOKEN" | python3 -c '
import json, sys, urllib.request
t = sys.stdin.read().strip()
try:
    print(json.load(urllib.request.urlopen("https://api.telegram.org/bot" + t + "/getMe", timeout=30))["result"]["username"])
except Exception as e:
    print("ОШИБКА:" + type(e).__name__)
')
[ "$NAME" = "$EXPECTED" ] || die "getMe для введённого токена: $NAME, а нужен @$EXPECTED. .env не тронут."
echo "getMe: @$NAME — токен верный"

BAK=".env.bak-$(date +%Y%m%d-%H%M%S)"
cp -p .env "$BAK" && chmod 600 "$BAK" || die "не удалось сделать копию .env"
echo "копия: /opt/astro/$BAK"

printf '%s' "$TOKEN" | python3 -c '
import sys
from pathlib import Path
new = sys.stdin.read().strip()
p = Path("/opt/astro/.env")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
idx = [i for i, l in enumerate(lines) if l.startswith("TELEGRAM_BOT_TOKEN=")]
assert len(idx) == 1, "строк TELEGRAM_BOT_TOKEN= в .env: %d" % len(idx)
old = lines[idx[0]]
lines[idx[0]] = "TELEGRAM_BOT_TOKEN=" + new + ("\n" if old.endswith("\n") else "")
assert lines[idx[0]] != old, "замена не применилась (токен тот же?)"
p.write_text("".join(lines), encoding="utf-8")
print("строка TELEGRAM_BOT_TOKEN заменена")
' || die "замена в .env не прошла — .env не изменён (копия: $BAK)"
TOKEN=""

echo "== пересоздаю api worker beat bot"
docker compose up -d --no-deps --force-recreate api worker beat bot </dev/null || die "docker compose up упал; вернуть: cp $BAK .env"

for i in $(seq 1 30); do
  st=$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q api)" 2>/dev/null)
  [ "$st" = "healthy" ] && break
  sleep 5
done
echo "api: ${st:-неизвестно}"
[ "$st" = "healthy" ] || die "api не стал healthy за 150 с; вернуть: cp $BAK .env && docker compose up -d --no-deps --force-recreate api worker beat bot"

echo "== проверка изнутри api"
docker compose exec -T api python - <<'PYEOF'
import asyncio, json, os, urllib.request
t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
print("getMe:", "@" + json.load(urllib.request.urlopen("https://api.telegram.org/bot" + t + "/getMe", timeout=30))["result"]["username"])
from backend.notifications.telegram import send_support_message
print("тест в канал:", asyncio.run(send_support_message("Проверка после перевыпуска токена (rotate_bot_token.sh)")))
PYEOF
echo "worker видит новый токен: $(docker compose exec -T worker python -c 'import os,json,urllib.request;t=os.environ.get("TELEGRAM_BOT_TOKEN","");print(json.load(urllib.request.urlopen("https://api.telegram.org/bot"+t+"/getMe",timeout=30))["result"]["username"])' </dev/null 2>&1 | tail -1)"
echo "Не забыть: Uptime Kuma → Settings → Notifications — новый токен руками."
echo "Копию $BAK удалить, когда всё проверено: в ней старый (отозванный) токен и остальные секреты."
echo "== конец. Лог: /opt/astro/$LOG"
