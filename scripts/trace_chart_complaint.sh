#!/usr/bin/env bash
# trace_chart_complaint.sh — что было у человека на экране карты перед жалобой
# (только чтение; ничего не меняет и не отправляет).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/trace_chart_complaint.sh
#
# По умолчанию — жалоба 30.09.2026 ~21:00 МСК (18:00 UTC): карта 501ede0d…,
# пользователь c381950b…, Android 15, Яндекс Браузер. Другую жалобу — аргументами:
#   bash scripts/trace_chart_complaint.sh <chart_id> <user_id> <UTC-начало> <UTC-конец>
#
# Зачем: у владельца по ссылке «карта не найдена», а сервер отвечает 404 и на
# отсутствующую, и на чужую карту (resolve_chart_access, backend/main.py) —
# по ответу их не различить. Здесь — факт из базы. Данные рождения, имя карты
# и почта не печатаются: только id, владелец, даты и признаки.

set -uo pipefail
CHART="${1:-501ede0d-3028-45c2-853b-ffecc394246a}"
USERID="${2:-c381950b-dca3-4e85-bba4-5de92b2579c2}"
FROM="${3:-2026-09-30T17:00:00Z}"
TO="${4:-2026-09-30T19:00:00Z}"

cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/trace_chart_complaint-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
echo "карта $CHART · пользователь $USERID · окно $FROM … $TO (UTC)"

PSQL='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v chart="$CHART" -v uid="$USERID" -v t0="$FROM" -v t1="$TO" -f -'
sql() { docker compose exec -T -e CHART="$CHART" -e USERID="$USERID" -e FROM="$FROM" -e TO="$TO" postgres sh -c "$PSQL"; }

echo "== 1. жалобы в окне (±1 ч) от этого человека или про эту карту"
echo "   message — как лежит в базе, целиком; длина 0/пусто — человек ничего не написал"
sql <<'SQL'
select f.id, f.created_at, f.screen, f.url, left(coalesce(f.user_id, '—'), 8) as user,
       length(f.message) as длина, f.message, f.user_agent, f.context
from feedback f
where f.created_at between ((:'t0')::timestamptz at time zone 'UTC') - interval '1 hour'
                       and ((:'t1')::timestamptz at time zone 'UTC') + interval '1 hour'
  and (f.user_id = :'uid' or f.url like '%' || :'chart' || '%')
order by f.id;
SQL

echo "== 2. карта: есть ли, чья, анонимная ли"
sql <<'SQL'
select c.id, coalesce(left(c.user_id, 8), 'анонимная') as владелец,
       (c.user_id = :'uid') as карта_этого_человека,
       c.created_at, c.expires_at,
       (c.expires_at is not null and c.expires_at < now()) as анонимная_истекла,
       (c.access_token is not null) as есть_ключ_гостя
from natal_charts c where c.id = :'chart';
select case when count(*) = 0 then 'карты с этим id в базе НЕТ (удалена или не было)' else 'карта есть' end as итог
from natal_charts where id = :'chart';
SQL

echo "== 3. пользователь: есть ли, тариф, его карты"
sql <<'SQL'
select left(u.id, 8) as user, left(u.email, 2) || '***' as email, u.tier, u.created_at
from users u where u.id = :'uid';
select c.id, c.created_at, (c.id = :'chart') as та_самая
from natal_charts c where c.user_id = :'uid' order by c.created_at;
SQL

echo "== 4. admin_audit_log по этой карте и человеку"
sql <<'SQL'
select * from admin_audit_log
where cast(admin_audit_log as text) like '%' || :'chart' || '%'
   or cast(admin_audit_log as text) like '%' || :'uid' || '%'
order by 1 desc limit 20;
SQL

echo "== 5. nginx: все запросы с id карты (время, метод, путь без query, код, IP без последнего октета)"
LOGS=$(ls /var/log/nginx/access.log* 2>/dev/null)
if [ -z "$LOGS" ]; then
  echo "журналов nginx нет"
elif [ ! -r /var/log/nginx/access.log ]; then
  echo "⚠️ нет прав на чтение /var/log/nginx — повтори с sudo"
else
  for L in $LOGS; do
    case "$L" in *.gz) zcat "$L" 2>/dev/null ;; *) cat "$L" 2>/dev/null ;; esac
  done | grep -F "$CHART" \
       | awk -F'"' '{split($1,a," "); split($2,r," "); split($3,b," "); ip=a[1]; sub(/\.[0-9]+$/, ".x", ip);
                     p=r[2]; sub(/\?.*/, "", p); print a[4], r[1], p, b[1], ip}' | tr -d '[' | sort
  echo "(конец; пусто — запросов с этим id в журналах нет)"
  echo "-- POST /api/v1/feedback в окне ±1 ч:"
  for L in $LOGS; do
    case "$L" in *.gz) zcat "$L" 2>/dev/null ;; *) cat "$L" 2>/dev/null ;; esac
  done | grep -F '"POST /api/v1/feedback' \
       | awk -F'"' '{split($1,a," "); split($3,b," "); print a[4], b[1], b[2] " байт"}' | tr -d '[' | sort | tail -20
  echo "журналы: $(ls -l --time-style=+%F /var/log/nginx/access.log* 2>&1 | awk '{print $6, $7}' | tr '\n' ' ')"
fi

echo "== 6. лог api в окне ±1 ч: строки с id карты или пользователя, ошибки"
APILOG=$(docker compose logs api --timestamps \
  --since "$(date -u -d "$FROM - 1 hour" +%Y-%m-%dT%H:%M:%SZ)" \
  --until "$(date -u -d "$TO + 1 hour" +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null)
grep -F -e "$CHART" -e "$USERID" <<<"$APILOG" | tail -60
echo "(строк с id: $(grep -cF -e "$CHART" -e "$USERID" <<<"$APILOG"))"
echo "-- ERROR/Traceback в окне (первые 40):"
grep -E 'ERROR|Traceback|Exception' <<<"$APILOG" | head -40
echo "== конец. Лог: /opt/astro/$LOG"
echo "Sentry: веб не ставит номер пользователя — ищи по url /chart/$CHART и времени."
