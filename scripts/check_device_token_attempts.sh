#!/usr/bin/env bash
# check_device_token_attempts.sh — доходит ли до сервера регистрация токена
# FCM из приложения и чем кончается (только чтение; ничего не меняет).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_device_token_attempts.sh
#
# Повод (30.09.2026): в device_tokens пусто, хотя в APK №120 тумблер включён.
# В приложении (lib/devicePush.js, registerDevice) два места сбоя сводятся в
# один итог «устройство»: FCM не выдал токен ИЛИ POST /push/device не прошёл.
# Различить их можно только здесь:
#   • в nginx нет ни одного POST /api/v1/push/device — сбой на телефоне (FCM);
#   • есть, но с 4xx/5xx — сбой на сервере или в авторизации.
# Сама ручка (push/router.py, register_device) при ошибке ничего не пишет,
# поэтому смотрим журнал доступа, а не журнал приложения. OPTIONS — это
# preflight CORS из WebView: если он есть, а POST за ним нет, POST отрезал CORS.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_device_token_attempts-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

PSQL='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
sql() { docker compose exec -T postgres sh -c "$PSQL"; }

echo "== device_tokens: сколько и последние 10 (без самих токенов)"
sql <<'SQL'
select count(*) as всего from device_tokens;
select left(user_id, 8) as user, platform, created_at, last_seen_at
from device_tokens order by created_at desc limit 10;
SQL

echo "== nginx: все запросы к /api/v1/push/device (время, метод, IP без последнего октета, код, WebView?)"
LOGS=$(ls /var/log/nginx/access.log* 2>/dev/null)
if [ -z "$LOGS" ]; then
  echo "журналов nginx нет"
elif [ ! -r /var/log/nginx/access.log ]; then
  echo "⚠️ нет прав на чтение /var/log/nginx — повтори с sudo"
else
  LINES=$(for L in $LOGS; do
    case "$L" in *.gz) zcat "$L" 2>/dev/null ;; *) cat "$L" 2>/dev/null ;; esac
  done | grep -E '"[A-Z]+ /api/v1/push/device')
  if [ -z "$LINES" ]; then
    echo "(пусто — ни одного запроса к /push/device: до сервера регистрация не доходит)"
  else
    # combined: $4 время, $6 метод, $9 код; агент — 6-е поле по кавычкам.
    awk -F'"' '{split($1,a," "); split($3,b," "); ip=a[1]; sub(/\.[0-9]+$/, ".x", ip);
                split($2,r," "); wv=($6 ~ /; wv\)/) ? "WebView" : "не WebView";
                print a[4], r[1], ip, b[1], wv}' <<<"$LINES" | tr -d '[' | sort
    echo "-- итого по методу и коду:"
    awk -F'"' '{split($2,r," "); split($3,b," "); print r[1], b[1]}' <<<"$LINES" | sort | uniq -c
  fi
  echo "журналы: $(ls -l --time-style=+%F /var/log/nginx/access.log* 2>&1 | awk '{print $6, $7}' | tr '\n' ' ')"
fi

echo "== лог api за 7 дней: строки про /push/device и ошибки роутера push"
APILOG=$(docker compose logs api --since 168h 2>/dev/null)
grep -E 'push/device|astro\.push\.router' <<<"$APILOG" | tail -50
echo "(строк: $(grep -cE 'push/device|astro\.push\.router' <<<"$APILOG"))"

echo "== конец. Лог: /opt/astro/$LOG"
