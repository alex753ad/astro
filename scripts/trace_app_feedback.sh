#!/usr/bin/env bash
# trace_app_feedback.sh — куда пропадают обращения из приложения (только чтение).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/trace_app_feedback.sh
#
# Ничего не меняет и ничего не отправляет. Вывод дублируется в
# /opt/astro/diag/trace_app_feedback-<время>.log.
#
# Повод (27.09.2026): обращения из приложения («Оплата и поддержка» →
# Написать) не доходят в канал, жалобы с веба доходят, переотправка #13 тем же
# кодом дошла. Смотрим по шагам: дошёл ли запрос до nginx и с каким кодом,
# записался ли в feedback, что api написал про отправку.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/trace_app_feedback-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

echo "== 1. обращения за сутки (время UTC; 16:00 МСК = 13:00 UTC)"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select f.id, f.created_at, f.screen, u.email, left(coalesce(f.message, chr(8212)), 40) as message, f.context from feedback f left join users u on u.id = f.user_id where f.created_at > now() - interval '"'"'1 day'"'"' order by f.id desc limit 20;"' </dev/null

echo "== 2. nginx: POST /api/v1/feedback за сутки (код ответа и клиент)"
for f in /var/log/nginx/access.log /var/log/nginx/access.log.1; do
  { cat "$f" 2>/dev/null || sudo -n cat "$f" 2>/dev/null || echo "нет доступа к $f"; } \
    | grep -E 'POST /api/v1/feedback|нет доступа' | tail -20
done

echo "== 3. api: всё про обращения и Telegram за 12 часов"
docker compose logs api --since 12h --timestamps </dev/null 2>&1 \
  | grep -iE "feedback|telegram|Обращение|support|Traceback|Error" | tail -60

echo "== 4. api: запросы к /feedback в логе uvicorn за 12 часов"
docker compose logs api --since 12h --timestamps </dev/null 2>&1 | grep '/api/v1/feedback' | tail -20

echo "== 5. контейнер api: когда создан и видит ли переменные бота"
docker compose ps api </dev/null
docker inspect --format 'created {{.Created}}  started {{.State.StartedAt}}' "$(docker compose ps -q api </dev/null)"
echo "token задан: $(docker compose exec -T api sh -c '[ -n "$TELEGRAM_BOT_TOKEN" ] && echo да || echo НЕТ' </dev/null)"
echo "chat_id:     $(docker compose exec -T api printenv TELEGRAM_SUPPORT_CHAT_ID </dev/null)"

echo "== конец. Лог: /opt/astro/$LOG"
