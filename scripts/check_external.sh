#!/usr/bin/env bash
# check_external.sh — связь по IPv4 и IPv6 со всеми внешними сервисами бэкенда.
#
# Запуск на сервере (только чтение; ключи не используются и не печатаются,
# запросов с данными не шлёт — только соединение и TLS):
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_external.sh
#
# Вывод дублируется в /opt/astro/diag/check_external-<время>.log.
#
# Повод: 30.09.2026 api.telegram.org оказался закрыт по IPv4 и открыт по IPv6
# (check_telegram.sh). httpx идёт в IPv4 первым и ждёт весь таймаут — сервис
# «работает», но каждый запрос теряет секунды или падает. Проверяем, кого ещё
# это касается. Список хостов — все внешние адреса из backend/ (без тестов)
# плюс хосты SDK: Sentry — из SENTRY_DSN (печатается только хост).
# Код ответа неважен (401/404/302 — сервис доступен); важно, что соединение
# есть и за сколько. 000 — соединения нет. Нет AAAA — IPv6 «нет адреса»
# (getent ahostsv6 без AAAA отдаёт ::ffff:-адреса IPv4 — их отбрасываем).
# ⚠️ `</dev/null` у exec — иначе exec съедает stdin (см. diag_support.sh).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_external-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
echo "сейчас $(date -u +%FT%TZ)"

SENTRY_HOST=$(docker compose exec -T api printenv SENTRY_DSN </dev/null 2>/dev/null | sed -nE 's#^[a-z]+://[^@]*@([^/:]+).*#\1#p')

HOSTS=(
  "api.telegram.org       Telegram (сигналы, бот поддержки)"
  "api.deepseek.com       DeepSeek (разборы, прогнозы)"
  "api.openai.com         OpenAI (запасной движок)"
  "api.anthropic.com      Anthropic (общий календарь)"
  "api.yookassa.ru        ЮKassa (платежи)"
  "yoomoney.ru            ЮMoney"
  "fcm.googleapis.com     FCM (пуши)"
  "oauth2.googleapis.com  Google OAuth / токены FCM"
  "accounts.google.com    Google вход"
  "www.googleapis.com     Google Календарь, профиль"
  "api.resend.com         Resend (письма)"
  "nominatim.openstreetmap.org  Nominatim (геокодинг)"
  "storage.yandexcloud.net      Бэкап за пределами сервера"
  "${SENTRY_HOST:-sentry.io}    Sentry${SENTRY_HOST:+ (из SENTRY_DSN)}"
)

probe() {  # probe <семейство> <хост> → одна строка итога; вторая попытка — если первая не соединилась
  local fam=$1 host=$2 out
  if [ "$fam" = 6 ] && [ -z "$(getent ahostsv6 "$host" | grep -v "::ffff:" | head -1)" ]; then echo "нет адреса"; return; fi
  if [ "$fam" = 4 ] && [ -z "$(getent ahostsv4 "$host" | head -1)" ]; then echo "нет адреса"; return; fi
  for try in 1 2; do
    out=$(curl -"$fam" -s -o /dev/null --connect-timeout 6 --max-time 12 \
      -w '%{http_code} %{time_connect} %{time_total}' "https://$host/" 2>/dev/null)
    set -- $out
    if [ "${1:-000}" != 000 ]; then printf 'ок (код %s, соединение %sс)' "$1" "$2"; return; fi
  done
  echo "НЕТ СВЯЗИ (2 попытки по 6 с)"
}

printf '%-30s | %-34s | %-34s | %s\n' "хост" "IPv4" "IPv6" "что это"
for line in "${HOSTS[@]}"; do
  host=${line%% *}; what=$(echo "${line#"$host"}" | sed 's/^ *//')
  printf '%-30s | %-34s | %-34s | %s\n' "$host" "$(probe 4 "$host")" "$(probe 6 "$host")" "$what"
done

echo "== лог сохранён: /opt/astro/$LOG"
