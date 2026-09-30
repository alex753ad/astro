#!/usr/bin/env bash
# check_push_tick_channels.sh — доходил ли тик пушей (прогноз дня, планер,
# транзиты, Луна) до тех, у кого только приложение (только чтение).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_push_tick_channels.sh
#
# Повод (30.09.2026): run_push_tick (backend/push/cron.py) отбирал людей по
# push_subscriptions — это только браузер. У кого лишь device_tokens (FCM,
# приложение), тот в тик не попадал. Если находка верна: у группы
# «только приложение» в push_sent_log нет видов тика (кроме пилотных
# farewell/dormant*, их шлёт другой крон), а в логе api нет «push send» по их id.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_push_tick_channels-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

PSQL='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
sql() { docker compose exec -T postgres sh -c "$PSQL"; }

echo "== сколько людей в каждом канале"
sql <<'SQL'
with ch as (
  select u.id,
         exists(select 1 from push_subscriptions s where s.user_id = u.id) as web,
         exists(select 1 from device_tokens d where d.user_id = u.id) as app
  from users u
)
select case when web and app then 'браузер и приложение'
            when web then 'только браузер'
            when app then 'только приложение' end as канал,
       count(*) as людей
from ch where web or app group by 1 order by 1;
SQL

echo "== push_sent_log за 14 дней по каналам и видам (пилот отдельно)"
sql <<'SQL'
with ch as (
  select u.id,
         exists(select 1 from push_subscriptions s where s.user_id = u.id) as web,
         exists(select 1 from device_tokens d where d.user_id = u.id) as app
  from users u
)
select case when web and app then 'браузер и приложение'
            when web then 'только браузер'
            else 'только приложение' end as канал,
       case when l.kind = 'farewell' or l.kind like 'dormant%' or l.kind = 'exit_eom'
            then 'пилот: ' || l.kind else l.kind end as вид,
       count(*) as записей, max(l.sent_at) as последняя
from push_sent_log l join ch on ch.id = l.user_id
where (web or app) and l.sent_at > now() - interval '14 days'
group by 1, 2 order by 1, 2;
SQL

echo "== люди только с приложением: когда токен заведён и когда был последний пуш тика"
sql <<'SQL'
select left(u.id::text, 8) as user, d.created_at as токен_с, d.last_seen_at,
       u.push_daily_forecast as прогноз, u.push_planner as планер,
       (select max(sent_at) from push_sent_log l where l.user_id = u.id
          and l.kind <> 'farewell' and l.kind not like 'dormant%' and l.kind <> 'exit_eom') as последний_пуш_тика
from device_tokens d join users u on u.id = d.user_id
where not exists(select 1 from push_subscriptions s where s.user_id = u.id)
order by d.created_at;
SQL

echo "== лог api за 72 часа: тик и отправки"
IDS=$(sql <<'SQL' | grep -Eo '[0-9a-f-]{36}' | sort -u
select d.user_id from device_tokens d
where not exists(select 1 from push_subscriptions s where s.user_id = d.user_id);
SQL
)
APILOG=$(docker compose logs api --since 72h 2>/dev/null)
echo "тиков (Push tick: users=…): $(grep -c 'Push tick: users=' <<<"$APILOG")"
echo "последний: $(grep 'Push tick: users=' <<<"$APILOG" | tail -1)"
echo "строк «push send»: $(grep -c 'push send user=' <<<"$APILOG")"
HIT=0
for id in $IDS; do
  n=$(grep -c "user=$id" <<<"$APILOG")
  [ "$n" -gt 0 ] && { echo "  упоминаний тиком у ${id:0:8}: $n"; HIT=1; }
done
[ "$HIT" -eq 0 ] && echo "у людей только с приложением строк тика нет ни одной (ни send, ни skip)"
echo "== конец. Лог: /opt/astro/$LOG"
