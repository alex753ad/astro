#!/usr/bin/env bash
# Ежедневный дамп БД: pg_dump -> gzip -> проверка целостности -> ротация (14 дней).
# Рассчитан на systemd-таймер astro-backup.timer (ставится 08-setup-automation.sh),
# но можно запускать и вручную из /opt/astro:  ./07-backup-cron.sh
#
# set -e намеренно не используется — при любой ошибке идём в fail(), которая
# сама шлёт алерт в Telegram и завершает скрипт с кодом 1.
set -uo pipefail

BACKUP_DIR="backups"
KEEP_DAYS=14
DUMP_FILE="${BACKUP_DIR}/daily_$(date +%Y%m%d_%H%M%S).dump.gz"

get_env_var() { grep -E "^${1}=" .env 2>/dev/null | head -1 | cut -d= -f2-; }

notify_telegram() {
  local text="$1" token chat_id
  token="$(get_env_var TELEGRAM_BOT_TOKEN)"
  chat_id="$(get_env_var TELEGRAM_SUPPORT_CHAT_ID)"
  [[ -n "$token" && -n "$chat_id" ]] || return 0
  curl -sS -m 10 -X POST "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${chat_id}" \
    --data-urlencode "text=${text}" >/dev/null 2>&1 || true
}

fail() {
  echo "ERROR: $*" >&2
  notify_telegram "🔴 astro: ежедневный бэкап БД упал на $(hostname): $*"
  exit 1
}

[[ -f docker-compose.yml ]] || fail "docker-compose.yml не найден. Запускайте из /opt/astro."
[[ -f .env ]] || fail ".env не найден."

pg_cid="$(docker compose ps -q postgres)"
[[ -n "$pg_cid" ]] || fail "контейнер postgres не запущен."

PG_USER="$(get_env_var POSTGRES_USER)"
PG_DB="$(get_env_var POSTGRES_DB)"
[[ -n "$PG_USER" && -n "$PG_DB" ]] || fail "POSTGRES_USER/POSTGRES_DB не найдены в .env"

mkdir -p "$BACKUP_DIR"

docker compose exec -T postgres pg_dump -Fc -U "$PG_USER" "$PG_DB" | gzip > "$DUMP_FILE" \
  || fail "pg_dump | gzip завершились с ошибкой"

[[ -s "$DUMP_FILE" ]] || fail "дамп получился пустым: $DUMP_FILE"

gzip -t "$DUMP_FILE" || fail "дамп не проходит проверку gzip -t (архив битый): $DUMP_FILE"

# pg_restore -l только читает оглавление архива (список таблиц/объектов),
# ничего не восстанавливает — безопасная проверка, что это валидный
# custom-format дамп pg_dump, а не просто непустой файл мусора.
if ! gunzip -c "$DUMP_FILE" | docker compose exec -T postgres pg_restore -l - >/dev/null 2>&1; then
  fail "дамп не проходит проверку pg_restore -l (не читается как валидный дамп): $DUMP_FILE"
fi

echo "OK: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"

deleted=0
while IFS= read -r -d '' old; do
  rm -f "$old"
  deleted=$((deleted + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'daily_*.dump.gz' -mtime "+${KEEP_DAYS}" -print0)
echo "Ротация: удалено файлов старше ${KEEP_DAYS}д: ${deleted}"
