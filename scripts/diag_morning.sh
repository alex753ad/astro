#!/usr/bin/env bash
# diag_morning.sh — почему не пришло утреннее сообщение (самопроверка 07:30 МСК,
# tasks.selfcheck_daily, beat: crontab 04:30 UTC).
#
# Запуск на сервере (только чтение, ничего не меняет и ничего не шлёт):
#   cd /opt/astro/app && git pull --ff-only && bash scripts/diag_morning.sh
# Необязательный аргумент — дата в UTC (ГГГГ-ММ-ДД), по умолчанию сегодня.
#
# Вывод дублируется в /opt/astro/diag/diag_morning-<время>.log.
#
# ⚠️ Окно логов задаётся в UTC: `docker compose logs --since/--until` понимает
# RFC3339, а метки времени в логах контейнеров — UTC. 07:25–07:40 МСК =
# 04:25–04:40 UTC. ⚠️ Логи контейнера стираются при его пересоздании (деплой)
# — поэтому шаг 1 показывает время старта: старт позже 04:40 UTC значит, что
# пустые логи окна ничего не говорят, смотреть selfcheck_runs (шаг 4).
# ⚠️ `</dev/null` у каждого exec — иначе exec съедает stdin (см. diag_support.sh).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/diag_morning-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

D="${1:-$(date -u +%F)}"
FROM="${D}T04:25:00Z"
TO="${D}T04:40:00Z"
echo "Дата (UTC): $D, окно $FROM … $TO; сейчас $(date -u +%FT%TZ)"

echo "== 1. контейнеры worker и beat: статус, старт, перезапуски"
docker compose ps worker beat </dev/null
for s in worker beat; do
  id=$(docker compose ps -q "$s" </dev/null)
  [ -n "$id" ] && echo "$s: $(docker inspect -f 'started={{.State.StartedAt}} restarts={{.RestartCount}} status={{.State.Status}}' "$id")"
done

echo "== 2. worker отвечает (celery ping)"
docker compose exec -T worker celery -A backend.celery_app inspect ping --timeout 10 </dev/null 2>&1 | tail -3

echo "== 3. beat отправлял selfcheck-daily (весь день $D)"
docker compose logs beat --since "${D}T00:00:00Z" --timestamps </dev/null 2>&1 \
  | grep -iE "selfcheck|error|Traceback" | tail -20
echo "-- последние строки beat (жив ли планировщик)"
docker compose logs beat --tail 5 --timestamps </dev/null 2>&1

echo "== 4. selfcheck_runs за $D (строка = прогон дошёл до конца)"
docker compose exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"select id, kind, ran_at, problems, unsent from selfcheck_runs where ran_at >= '$D' order by id;\"" </dev/null

echo "== 5. worker в окне $FROM … $TO"
docker compose logs worker --since "$FROM" --until "$TO" --timestamps </dev/null 2>&1 \
  | grep -iE "selfcheck|Task|ERROR|WARNING|Traceback|telegram|httpx" | tail -60

echo "== 6. ошибки Telegram за $D (worker, beat, api)"
for s in worker beat api; do
  echo "-- $s"
  docker compose logs "$s" --since "${D}T00:00:00Z" --timestamps </dev/null 2>&1 \
    | grep -iE "telegram|api.telegram|chat not found|Forbidden|Too Many|сигнал не доставлен|не доставлен" | tail -15
done

echo "== 7. чат канала и токен в worker (значения токена не печатаются)"
echo "TELEGRAM_SUPPORT_CHAT_ID: $(docker compose exec -T worker printenv TELEGRAM_SUPPORT_CHAT_ID </dev/null)"
echo "TELEGRAM_BOT_TOKEN задан: $(docker compose exec -T worker sh -c '[ -n "$TELEGRAM_BOT_TOKEN" ] && echo да || echo нет' </dev/null)"

echo "== лог сохранён: /opt/astro/$LOG"
