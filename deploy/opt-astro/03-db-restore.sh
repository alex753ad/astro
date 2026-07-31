#!/usr/bin/env bash
# Перенос БД Railway -> локальный Postgres в docker-compose.yml.
# Запускать от deploy, из /opt/astro:  ./03-db-restore.sh '<railway-connection-string>'
#
# api и bot НЕ поднимаются этим скриптом ни на одном шаге — backend/main.py
# делает Base.metadata.create_all() при старте, и на пустой БД это создаст
# таблицы в обход Alembic. Порядок обязателен: этот скрипт -> вручную
# проверить результат -> только потом `docker compose up -d api bot`.
set -euo pipefail

HEALTH_TIMEOUT=60
BACKUP_DIR="backups"
EXPECTED_ALEMBIC_VERSION="040_feedback_user_agent"
EXPECTED_USERS_COUNT="15"

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }
warn() { echo "ПРЕДУПРЕЖДЕНИЕ: $*" >&2; }
die() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Аргумент: строка подключения Railway. Не хардкодится, нигде не печатается.
# ---------------------------------------------------------------------------
if [[ $# -lt 1 || -z "${1:-}" ]]; then
  cat >&2 <<'EOF'
Использование: ./03-db-restore.sh '<railway-connection-string>'

Пример формата: postgresql://user:password@host:port/dbname

Строка подключения передаётся первым аргументом и нигде не логируется
и не выводится этим скриптом.
EOF
  exit 1
fi

[[ -f docker-compose.yml ]] || die "docker-compose.yml не найден в текущем каталоге. Запускайте из /opt/astro."
[[ -f .env ]] || die ".env не найден в текущем каталоге. Запускайте из /opt/astro."

RAILWAY_URL="$1"
shift || true

if [[ ! "$RAILWAY_URL" =~ ^postgres(ql)?://([^:@/]+)(:([^@/]*))?@([^:@/]+)(:([0-9]+))?/([^?]+) ]]; then
  die "не удалось разобрать строку подключения. Ожидается формат postgresql://user:password@host:port/dbname"
fi
RW_USER="${BASH_REMATCH[2]}"
RW_PASS="${BASH_REMATCH[4]}"
RW_HOST="${BASH_REMATCH[5]}"
RW_PORT="${BASH_REMATCH[7]:-5432}"
RW_DB="${BASH_REMATCH[8]}"
unset RAILWAY_URL

# Передаём Railway-креды в контейнер только через переменные окружения
# (PGUSER/PGPASSWORD/...), никогда как аргумент командной строки —
# аргументы видны в `ps`, переменные окружения процесса — нет.
export PGUSER="$RW_USER" PGPASSWORD="$RW_PASS" PGHOST="$RW_HOST" PGPORT="$RW_PORT" PGDATABASE="$RW_DB"
trap 'unset PGUSER PGPASSWORD PGHOST PGPORT PGDATABASE RW_USER RW_PASS RW_HOST RW_PORT RW_DB' EXIT

get_env_var() { grep -E "^${1}=" .env | head -1 | cut -d= -f2-; }
LOCAL_PG_USER="$(get_env_var POSTGRES_USER)"
LOCAL_PG_DB="$(get_env_var POSTGRES_DB)"
[[ -n "$LOCAL_PG_USER" && -n "$LOCAL_PG_DB" ]] || die "POSTGRES_USER/POSTGRES_DB не найдены в .env"

# ---------------------------------------------------------------------------
# Шаг 1: поднять только postgres и redis, дождаться healthy
# ---------------------------------------------------------------------------
log "Шаг 1/7: поднимаю postgres и redis (api и bot не трогаю)"
docker compose up -d postgres redis

wait_healthy() {
  local service="$1" waited=0 cid status
  cid="$(docker compose ps -q "$service")"
  [[ -n "$cid" ]] || die "контейнер сервиса '$service' не найден после 'docker compose up -d'"
  echo "  ожидаю healthy для '$service' (таймаут ${HEALTH_TIMEOUT}s)..."
  while true; do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo unknown)"
    [[ "$status" == "healthy" ]] && { echo "  -> $service: healthy"; return 0; }
    if (( waited >= HEALTH_TIMEOUT )); then
      die "'$service' не стал healthy за ${HEALTH_TIMEOUT}s (последний статус: $status)"
    fi
    sleep 2
    waited=$((waited + 2))
  done
}
wait_healthy postgres
wait_healthy redis

# ---------------------------------------------------------------------------
# Шаг 2: сравнить мажорные версии Railway и локального Postgres
# ---------------------------------------------------------------------------
log "Шаг 2/7: сверяю версии Postgres (Railway vs локальный контейнер)"

local_version_num="$(docker compose exec -T postgres \
  psql -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" -tAc "SHOW server_version_num;" | tr -d '[:space:]')"
[[ "$local_version_num" =~ ^[0-9]+$ ]] || die "не удалось получить версию локального Postgres"

railway_version_num="$(docker compose exec -T -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE postgres \
  psql -tAc "SHOW server_version_num;" | tr -d '[:space:]')"
[[ "$railway_version_num" =~ ^[0-9]+$ ]] || die "не удалось подключиться к Railway или получить версию сервера"

local_major=$(( local_version_num / 10000 ))
railway_major=$(( railway_version_num / 10000 ))
echo "  локальный Postgres: major $local_major"
echo "  Railway Postgres:   major $railway_major"

if (( railway_major > local_major )); then
  die "версия Railway (major $railway_major) новее локальной (major $local_major)." \
"pg_dump из локального контейнера не гарантированно снимет дамп с более новой версии сервера. Останавливаюсь, восстановление не выполнялось."
fi
echo "  версии совместимы, продолжаю"

# ---------------------------------------------------------------------------
# Шаг 3: снять дамп (pg_dump внутри контейнера postgres, custom-формат)
# ---------------------------------------------------------------------------
log "Шаг 3/7: снимаю дамп с Railway"
mkdir -p "$BACKUP_DIR"
DUMP_FILE="${BACKUP_DIR}/railway_$(date +%Y%m%d).dump"

if [[ -s "$DUMP_FILE" ]]; then
  echo "  файл $DUMP_FILE уже существует и не пуст — повторно не снимаю (идемпотентность)"
else
  echo "  pg_dump -Fc -> $DUMP_FILE"
  docker compose exec -T -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE postgres \
    pg_dump -Fc > "$DUMP_FILE"
  [[ -s "$DUMP_FILE" ]] || die "pg_dump создал пустой файл — что-то пошло не так"
  echo "  готово, размер: $(du -h "$DUMP_FILE" | cut -f1)"
fi

# ---------------------------------------------------------------------------
# Шаг 4: убедиться, что целевая БД пуста
# ---------------------------------------------------------------------------
log "Шаг 4/7: проверяю, что целевая БД '$LOCAL_PG_DB' пуста"
table_count="$(docker compose exec -T postgres \
  psql -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d '[:space:]')"

if [[ "$table_count" != "0" ]]; then
  die "целевая БД не пуста (таблиц в public: $table_count). Ничего не восстановлено и не перезаписано." \
"Если это повторный запуск после успешного восстановления — так и должно быть, восстанавливать больше не нужно."
fi
echo "  БД пуста, можно восстанавливать"

# ---------------------------------------------------------------------------
# Шаг 5: восстановить дамп
# ---------------------------------------------------------------------------
log "Шаг 5/7: восстанавливаю из $DUMP_FILE"
docker compose exec -T postgres \
  pg_restore --no-owner --no-privileges -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" < "$DUMP_FILE"
echo "  pg_restore завершён"

# ---------------------------------------------------------------------------
# Шаг 6: проверка результата
# ---------------------------------------------------------------------------
log "Шаг 6/7: проверяю результат"

version_num="$(docker compose exec -T postgres \
  psql -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" -tAc "SELECT version_num FROM alembic_version;" | tr -d '[:space:]')"
echo "  alembic_version.version_num = $version_num (ожидается: $EXPECTED_ALEMBIC_VERSION)"
[[ "$version_num" == "$EXPECTED_ALEMBIC_VERSION" ]] || warn "version_num не совпадает с ожидаемым — проверьте вручную"

users_count="$(docker compose exec -T postgres \
  psql -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" -tAc "SELECT count(*) FROM users;" | tr -d '[:space:]')"
echo "  users: $users_count строк (ожидается: $EXPECTED_USERS_COUNT)"
[[ "$users_count" == "$EXPECTED_USERS_COUNT" ]] || warn "число строк в users не совпадает с ожидаемым — проверьте вручную"

echo "  таблицы:"
docker compose exec -T postgres psql -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" -c '\dt'

# ---------------------------------------------------------------------------
# Шаг 7: итог
# ---------------------------------------------------------------------------
log "Шаг 7/7: готово"
cat <<EOF

Восстановление БД завершено.
Дамп: $DUMP_FILE

api и bot НЕ запущены — этот скрипт их не трогает.
Следующий шаг выполняется вручную, отдельной командой:

    docker compose up -d api bot

EOF
