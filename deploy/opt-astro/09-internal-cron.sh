#!/usr/bin/env bash
# Дёргает один из /api/v1/internal/* эндпоинтов по расписанию (systemd-таймер).
# Запускать из /opt/astro:  ./09-internal-cron.sh <path>
#   ./09-internal-cron.sh /api/v1/internal/onboarding-emails
#   ./09-internal-cron.sh /api/v1/internal/pilot-tick
#
# Зачем отдельный скрипт, а не всё в Celery Beat: эти две ручки не Celery-задачи,
# а обычные HTTP-эндпоинты за require_internal_secret (backend/authz.py) —
# переделывать их в задачи ради унификации того не стоило. Раньше их не вызывал
# вообще никто: при переезде с Railway (там это были cron-контейнеры) замена
# на VPS не была сделана, и /internal/onboarding-emails, /internal/pilot-tick
# висели мёртвым кодом — письма удержания 2/7 дня и весь жизненный цикл
# пилотной программы просто не отправлялись.
set -uo pipefail

PATH_SEGMENT="${1:?использование: ./09-internal-cron.sh /api/v1/internal/<endpoint>}"
API_URL="http://127.0.0.1:8000${PATH_SEGMENT}"

cd "$(dirname "$0")" || exit 1
[[ -f .env ]] || { echo "ERROR: .env не найден. Запускайте из /opt/astro." >&2; exit 1; }

get_env_var() { grep -E "^${1}=" .env 2>/dev/null | head -1 | cut -d= -f2-; }

SECRET="$(get_env_var INTERNAL_SECRET)"
if [[ -z "$SECRET" ]]; then
  echo "ERROR: INTERNAL_SECRET не задан в .env — ручка отдаст 503." >&2
  exit 1
fi

response="$(curl -sS -m 60 -o /tmp/internal-cron-response.json -w "%{http_code}" \
  -X POST "$API_URL" -H "X-Internal-Secret: ${SECRET}")"

if [[ "$response" -lt 200 || "$response" -ge 300 ]]; then
  echo "ERROR: ${PATH_SEGMENT} вернул HTTP ${response}: $(cat /tmp/internal-cron-response.json 2>/dev/null)" >&2
  exit 1
fi

echo "OK: ${PATH_SEGMENT} -> HTTP ${response}: $(cat /tmp/internal-cron-response.json 2>/dev/null)"
