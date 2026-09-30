#!/usr/bin/env bash
# check_push_settings.sh — что лежит на сервере в настройках push у одного
# аккаунта и были ли PATCH /push/settings (только чтение; ничего не меняет).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_push_settings.sh <почта>
#
# Повод (30.09.2026): на первом запуске приложения «Прогноз дня» и «Планер»
# показаны выключенными. Экран (MoreNotificationsView.jsx) рисует тумблеры
# ровно по GET /push/settings, а записать false может только PATCH — значит,
# ответ либо в строке users, либо в журнале nginx. Почта в выводе маскируется.

set -uo pipefail
EMAIL="${1:-}"
if [ -z "$EMAIL" ]; then echo "укажи почту: bash scripts/check_push_settings.sh <почта>"; exit 1; fi
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_push_settings-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

# SQL — через stdin, а не -c: в -c psql не подставляет :'email'.
PSQL='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v email="$EMAIL" -f -'

echo "== users: настройки push (почта маскирована)"
docker compose exec -T -e EMAIL="$EMAIL" postgres sh -c "$PSQL" <<'SQL'
select id, left(email, 2) || '***' as email, tier, created_at, updated_at,
       push_daily_forecast, push_planner, push_key_transits, push_moon_phases,
       push_daily_time, push_quiet_from
from users where lower(trim(email)) = lower(trim(:'email'));
SQL

echo "== device_tokens этого аккаунта"
docker compose exec -T -e EMAIL="$EMAIL" postgres sh -c "$PSQL" <<'SQL'
select d.platform, d.created_at, d.last_seen_at
from device_tokens d join users u on u.id = d.user_id
where lower(trim(u.email)) = lower(trim(:'email'));
SQL

echo "== nginx: все PATCH /api/v1/push/settings (время, IP без последнего октета, код)"
LOGS=$(ls /var/log/nginx/access.log* 2>/dev/null)
if [ -z "$LOGS" ]; then
  echo "журналов nginx нет"
elif [ ! -r /var/log/nginx/access.log ]; then
  echo "⚠️ нет прав на чтение /var/log/nginx — повтори с sudo"
else
  for L in $LOGS; do
    case "$L" in *.gz) zcat "$L" 2>/dev/null ;; *) cat "$L" 2>/dev/null ;; esac
  done | grep -E '"PATCH /api/v1/push/settings' \
       | awk '{ip=$1; sub(/\.[0-9]+$/, ".x", ip); print $4, ip, $9}' | tr -d '[' | sort \
       || true
  echo "(конец списка; пусто — таких запросов в журнале нет)"
  echo "журналы: $(ls -l --time-style=+%F /var/log/nginx/access.log* 2>&1 | awk '{print $6, $7}' | tr '\n' ' ')"
fi
echo "== конец. Лог: /opt/astro/$LOG"
