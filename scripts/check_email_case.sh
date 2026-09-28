#!/usr/bin/env bash
# check_email_case.sh — есть ли аккаунты, почта которых отличается только
# регистром или пробелами (только чтение; ничего не меняет).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_email_case.sh
#
# Повод (28.09.2026): вход стал без учёта регистра. Если такие пары есть,
# вход по почте в «чужом» регистре их не выберет наугад (backend/auth/emails.py),
# а что с ними делать — решает владелец. Почты в выводе маскируются.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_email_case-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

echo "== аккаунты, совпадающие по lower(trim(email)) (почта маскирована)"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select left(lower(trim(email)), 2) || '"'"'***@'"'"' || split_part(lower(trim(email)), '"'"'@'"'"', 2) as email,
       count(*) as accounts,
       string_agg('"'"'id='"'"' || id || '"'"' создан '"'"' || created_at::date || '"'"' тариф '"'"' || tier, '"'"' | '"'"') as rows
from users group by lower(trim(email)) having count(*) > 1;"' </dev/null

echo "== почты с заглавными буквами или пробелами по краям (сколько)"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select count(*) filter (where email <> lower(email)) as with_upper,
       count(*) filter (where email <> trim(email)) as with_spaces,
       count(*) as total from users;"' </dev/null

echo "== конец. Лог: /opt/astro/$LOG"
