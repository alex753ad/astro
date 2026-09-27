#!/usr/bin/env bash
# diag_login.sh — почему не входит ни один аккаунт и не работает сброс пароля
# (только чтение; ничего не меняет и ничего не отправляет).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/diag_login.sh
#
# Вывод дублируется в /opt/astro/diag/diag_login-<время>.log. Почты в выводе
# маскируются; пароли и хеши не печатаются — только «есть/нет».

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/diag_login-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

echo "== 1. ревизия схемы и версия кода"
docker compose exec -T api alembic current </dev/null 2>&1 | tail -1
docker compose exec -T api printenv GIT_SHA </dev/null

echo "== 2. запросы входа/сброса за 3 часа: путь и код ответа (uvicorn)"
docker compose logs api --since 3h --timestamps </dev/null 2>&1 \
  | grep -E '/api/v1/auth/(login|forgot-password|reset-password|refresh|register)' \
  | sed -E 's/.*(POST|GET) ([^ ]+) HTTP[^"]*" ([0-9]+).*/\1 \2 \3/' | sort | uniq -c | sort -rn | head -20
echo "-- последние 15 строк входа/сброса целиком"
docker compose logs api --since 3h --timestamps </dev/null 2>&1 \
  | grep -E '/api/v1/auth/(login|forgot-password|reset-password)' | tail -15

echo "== 3. ошибки api за 3 часа (auth, email, Traceback)"
docker compose logs api --since 3h --timestamps </dev/null 2>&1 \
  | grep -iE 'Traceback|Error|reset email failed|resend|login_guard|Password reset' | tail -30

echo "== 4. аккаунты: сколько, у скольких есть пароль, последние 10 (почта маскирована)"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select count(*) as users,
       count(*) filter (where hashed_password is null) as no_password,
       count(*) filter (where not is_active) as inactive
from users;"' </dev/null
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select left(email, 3) || '"'"'***@'"'"' || split_part(email, '"'"'@'"'"', 2) as email,
       (hashed_password is not null) as has_pw, left(hashed_password, 4) as pw_kind,
       is_active, token_version, created_at, updated_at, tier
from users order by updated_at desc nulls last limit 10;"' </dev/null

echo "== 5. блокировки входа по неудачам (login_guard в Redis)"
docker compose exec -T redis sh -c 'redis-cli --scan --pattern "*login*" | head -20; echo "ключей: $(redis-cli --scan --pattern "*login*" | wc -l)"' </dev/null

echo "== 6. worker: чистка анонимных карт и письма за 12 часов"
docker compose logs worker --since 12h --timestamps </dev/null 2>&1 \
  | grep -E 'purge_expired_anonymous_charts|send_claim_welcome|Resend|email' | tail -15

echo "== 7. проверка входа тем же кодом без пароля: что видит сервер по почте"
echo "   (если нужно — впиши почту: bash scripts/diag_login.sh you@mail.ru)"
if [ -n "${1:-}" ]; then
docker compose exec -T -e CHECK_EMAIL="$1" api python - <<'PYEOF'
import os
from backend.database import SessionLocal
from backend.models import User
e = os.environ["CHECK_EMAIL"]
db = SessionLocal()
exact = db.query(User).filter(User.email == e).first()
ci = db.query(User).filter(User.email.ilike(e)).all()
print("точное совпадение почты:", bool(exact), "| без учёта регистра:", len(ci))
for u in ci:
    print("  есть пароль:", bool(u.hashed_password), "активен:", u.is_active,
          "token_version:", u.token_version, "почта в базе совпадает по регистру:", u.email == e)
PYEOF
fi

echo "== конец. Лог: /opt/astro/$LOG"
