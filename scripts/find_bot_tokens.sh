#!/usr/bin/env bash
# find_bot_tokens.sh — какие Telegram-боты настроены на сервере и где.
#
# Только чтение: печатает ИМЯ бота (getMe) и место, токены не печатает.
#   cd /opt/astro/app && git pull --ff-only && bash scripts/find_bot_tokens.sh
#
# Повод (27.09.2026): в канале поддержки был @astreyatimelinebot, а сервер с
# 02.09 пишет от @Aristeatimebot. Ищем все места, где остался токен бота:
# .env-файлы, systemd-юниты и уведомления Uptime Kuma (их вписывают руками в
# интерфейсе, в репозитории их нет).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/find_bot_tokens-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

KUMA=$(mktemp)
docker compose cp uptime-kuma:/app/data/kuma.db "$KUMA" </dev/null >/dev/null 2>&1 || : > "$KUMA"

python3 - "$KUMA" <<'PYEOF'
import glob, json, re, sqlite3, sys, urllib.request
TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")
found = {}
def add(tok, where):
    found.setdefault(tok, set()).add(where)
files = ["/opt/astro/.env", "/opt/astro/frontend.env", "/opt/astro/app/.env"] + glob.glob("/etc/systemd/system/astro*")
for f in files:
    try:
        for i, line in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
            for tok in TOKEN.findall(line):
                key = line.split("=", 1)[0].strip() if "=" in line else "строка %d" % i
                add(tok, "%s (%s)" % (f, key))
    except OSError:
        pass
try:
    db = sqlite3.connect(sys.argv[1])
    for name, cfg in db.execute("select name, config from notification"):
        for tok in TOKEN.findall(cfg or ""):
            add(tok, "Uptime Kuma, уведомление «%s»" % name)
except Exception as e:
    print("Uptime Kuma: не прочитать (%s)" % type(e).__name__)
if not found:
    print("токенов не найдено")
for tok, places in found.items():
    try:
        name = "@" + json.load(urllib.request.urlopen("https://api.telegram.org/bot" + tok + "/getMe", timeout=30))["result"]["username"]
    except Exception as e:
        name = "getMe не прошёл (%s) — токен отозван или неверен" % type(e).__name__
    print(name)
    for p in sorted(places):
        print("   ", p)
PYEOF
rm -f "$KUMA"
echo "== конец. Лог: /opt/astro/$LOG"
