#!/usr/bin/env bash
# Еженедельная чистка неиспользуемых Docker-образов + алерт в Telegram,
# если свободного места на диске меньше 20%.
# Рассчитан на systemd-таймер astro-prune.timer (ставится 08-setup-automation.sh),
# но можно запускать и вручную из /opt/astro:  ./prune-and-diskcheck.sh
set -uo pipefail

FREE_PCT_THRESHOLD=20

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

[[ -f .env ]] || { echo "ERROR: .env не найден. Запускайте из /opt/astro." >&2; exit 1; }

echo "Docker image prune (образы без контейнеров, старше 168ч)"
docker image prune -af --filter "until=168h"

used_pct="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
free_pct=$((100 - used_pct))
echo "Свободно на /: ${free_pct}%"

if (( free_pct < FREE_PCT_THRESHOLD )); then
  notify_telegram "⚠️ astro: свободного места на диске ${free_pct}% (порог ${FREE_PCT_THRESHOLD}%) на $(hostname)"
fi
