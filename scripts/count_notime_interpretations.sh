#!/usr/bin/env bash
# count_notime_interpretations.sh — сколько готовых разборов карты у карт БЕЗ
# времени рождения и сколько стоила бы их перегенерация (только чтение;
# ничего не меняет). Шаг 3 аудита (04.10.2026): с него промпт разбора не
# получает домов и ASC, а готовые разборы НЕ перегенерируются без решения
# владельца.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/count_notime_interpretations.sh
#
# Оценка цены — DeepSeek v4-pro, $0.66 вход / $1.98 выход за миллион токенов
# (вне часов пик; в пик вдвое, interpretation/router.py). Выход — по длине
# текста: ~3 символа на токен у русского текста; вход — ~3000 токенов на
# запрос (промпт с картой). Порядок величины, не бухгалтерия.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/count_notime_interpretations-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

PSQL='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
sql() { docker compose exec -T postgres sh -c "$PSQL"; }

echo "== карты без времени рождения"
sql <<'SQL'
select count(*) as карт, count(distinct user_id) as людей
from natal_charts where time_unknown;
SQL

echo "== разборы этих карт (все строки и последний на карту и тариф)"
sql <<'SQL'
with r as (
  select i.*, row_number() over (partition by i.chart_id, coalesce(i.tier, '?')
                                 order by i.created_at desc) as rn
  from interpretations i join natal_charts c on c.id = i.chart_id
  where c.time_unknown
)
select coalesce(tier, 'до 29.09 (без тарифа)') as тариф,
       engine as движок,
       count(*) as всего_строк,
       count(*) filter (where rn = 1) as последних,
       round(avg(length(content))) as символов_в_среднем,
       round(sum(case when rn = 1 and engine <> 'template'
                      then 3000 * 0.66e-6 + length(content) / 3.0 * 1.98e-6 else 0 end)::numeric, 2)
         as "перегенерация_$"
from r group by 1, 2 order by 1, 2;
SQL

echo "== итог: перегенерация последних разборов (без шаблонных)"
sql <<'SQL'
with r as (
  select i.*, row_number() over (partition by i.chart_id, coalesce(i.tier, '?')
                                 order by i.created_at desc) as rn
  from interpretations i join natal_charts c on c.id = i.chart_id
  where c.time_unknown
)
select count(*) filter (where rn = 1 and engine <> 'template') as генераций,
       round(sum(case when rn = 1 and engine <> 'template'
                      then 3000 * 0.66e-6 + length(content) / 3.0 * 1.98e-6 else 0 end)::numeric, 2)
         as "вне_пика_$",
       round(2 * sum(case when rn = 1 and engine <> 'template'
                          then 3000 * 0.66e-6 + length(content) / 3.0 * 1.98e-6 else 0 end)::numeric, 2)
         as "в_пик_$"
from r;
SQL
