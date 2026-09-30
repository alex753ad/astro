#!/usr/bin/env bash
# check_activity_days.sh — идёт ли запись активных дней для удержания
# (только чтение; ничего не меняет). Правило — docs/retention.md.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_activity_days.sh
#
# Строки за сегодня (по Москве — день в таблице московский, backend/activity.py)
# по платформам: отдельно обычные люди и отдельно администраторы с тестовыми
# аккаунтами (revenue_excluded) — последние в удержание не входят, но пишутся
# так же, поэтому на них видно, что запись идёт, даже если чужих входов не было.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_activity_days-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

PSQL='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
sql() { docker compose exec -T postgres sh -c "$PSQL"; }

echo "== user_activity_days за сегодня ($(TZ=Europe/Moscow date +%F) МСК)"
sql <<'SQL'
select case when u.is_admin or u.revenue_excluded
            then 'админы и тестовые' else 'обычные' end as кто,
       a.platform as платформа,
       count(*) as строк
from user_activity_days a join users u on u.id = a.user_id
where a.day = (now() at time zone 'Europe/Moscow')::date
group by 1, 2 order by 1 desc, 2;
SQL

echo "== по дням с начала записи"
sql <<'SQL'
select day as день,
       count(*) filter (where platform = 'app') as приложение,
       count(*) filter (where platform = 'web') as сайт
from user_activity_days group by day order by day desc limit 14;
SQL
echo "Пусто сегодня — зайди на сайт или в приложение под своим входом и запусти ещё раз."
