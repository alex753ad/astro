#!/usr/bin/env bash
# Однокомандное обновление прод-стека.
# Запускать от deploy, из /opt/astro:  ./05-update.sh [--backend-only|--frontend-only]
set -euo pipefail

APP_DIR="app"
BACKUP_DIR="backups"
FRONTEND_DEPLOY_SCRIPT="./04-frontend-deploy.sh"
REGISTRY_RETRY_MAX=3
REGISTRY_RETRY_DELAY=20

DO_BACKEND=true
DO_FRONTEND=true
FORCE_FRONTEND=false
MODE="both"

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Использование: ./05-update.sh [--backend-only|--frontend-only]

Без флагов (по умолчанию, "оба"):
  git pull, пересборка + рестарт api/bot, и пересборка фронтенда —
  но фронтенд пересобирается ТОЛЬКО если в пришедших коммитах менялся
  app/frontend/.

--backend-only   git pull + пересборка/рестарт только api и bot.
--frontend-only  только пересборка фронтенда, безусловно (без бэкенд-шагов;
                 04-frontend-deploy.sh сделает git pull сам).
EOF
}

for arg in "$@"; do
  case "$arg" in
    --backend-only)  DO_BACKEND=true;  DO_FRONTEND=false; MODE="backend" ;;
    --frontend-only) DO_BACKEND=false; DO_FRONTEND=true;  FORCE_FRONTEND=true; MODE="frontend" ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "неизвестный флаг: $arg" ;;
  esac
done

[[ -f docker-compose.yml ]] || die "docker-compose.yml не найден в текущем каталоге. Запускайте из /opt/astro."
[[ -f .env ]] || die ".env не найден в текущем каталоге."

# Ретраи на 429 от Docker Hub при пуллинге базового образа во время сборки.
# Стримит вывод живьём (tee) и одновременно проверяет его на признаки rate-limit.
run_with_registry_retry() {
  local attempt=1 log_file rc
  log_file="$(mktemp)"
  trap 'rm -f "$log_file"' RETURN
  while true; do
    if "$@" 2>&1 | tee "$log_file"; then
      return 0
    fi
    rc=${PIPESTATUS[0]}
    if grep -qiE "429|too many requests|toomanyrequests|rate limit" "$log_file"; then
      if (( attempt >= REGISTRY_RETRY_MAX )); then
        die "Docker Hub всё ещё возвращает 429 после ${REGISTRY_RETRY_MAX} попыток. Подождите несколько минут и запустите ./05-update.sh ещё раз."
      fi
      echo "  Docker Hub вернул 429 (попытка ${attempt}/${REGISTRY_RETRY_MAX}), жду ${REGISTRY_RETRY_DELAY}s..."
      sleep "$REGISTRY_RETRY_DELAY"
      attempt=$((attempt + 1))
      continue
    fi
    return "$rc"
  done
}

# ---------------------------------------------------------------------------
# git pull — кроме чистого --frontend-only, где пуллом займётся сам
# 04-frontend-deploy.sh
# ---------------------------------------------------------------------------
frontend_changed=false
if [[ "$MODE" != "frontend" ]]; then
  log "git pull в $APP_DIR"
  [[ -d "$APP_DIR" ]] || die "каталог '$APP_DIR' не найден."
  git -C "$APP_DIR" fetch --quiet
  before_rev="$(git -C "$APP_DIR" rev-parse HEAD)"
  git -C "$APP_DIR" pull --ff-only
  after_rev="$(git -C "$APP_DIR" rev-parse HEAD)"

  if [[ "$before_rev" == "$after_rev" ]]; then
    echo "  уже на актуальном коммите ($after_rev), изменений нет"
  else
    echo "  $before_rev -> $after_rev"
    if ! git -C "$APP_DIR" diff --quiet "$before_rev" "$after_rev" -- frontend/; then
      frontend_changed=true
      echo "  затронут app/frontend/"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Бэкенд: дамп БД -> сборка -> пересоздание api/bot (postgres и redis не трогаем)
# ---------------------------------------------------------------------------
if $DO_BACKEND; then
  log "Бэкенд: дамп БД перед пересборкой"
  pg_cid="$(docker compose ps -q postgres)"
  if [[ -z "$pg_cid" ]]; then
    die "контейнер postgres не запущен — пересобирать бэкенд без бэкапа БД не буду. Поднимите 'docker compose up -d postgres redis' и повторите."
  fi

  get_env_var() { grep -E "^${1}=" .env | head -1 | cut -d= -f2-; }
  PG_USER="$(get_env_var POSTGRES_USER)"
  PG_DB="$(get_env_var POSTGRES_DB)"
  [[ -n "$PG_USER" && -n "$PG_DB" ]] || die "POSTGRES_USER/POSTGRES_DB не найдены в .env"

  mkdir -p "$BACKUP_DIR"
  dump_file="${BACKUP_DIR}/pre-update_$(date +%Y%m%d_%H%M%S).dump"
  docker compose exec -T postgres pg_dump -Fc -U "$PG_USER" "$PG_DB" > "$dump_file"
  [[ -s "$dump_file" ]] || die "pg_dump создал пустой файл — пересборку не продолжаю"
  echo "  дамп: $dump_file ($(du -h "$dump_file" | cut -f1))"

  log "Бэкенд: собираю образ (api, bot)"
  run_with_registry_retry docker compose build api bot

  log "Бэкенд: пересоздаю api и bot из новой сборки (работавшие контейнеры не трогались до этого момента)"
  docker compose up -d --no-deps api bot
  echo "  готово"
fi

# ---------------------------------------------------------------------------
# Фронтенд: только если менялся app/frontend/, либо запрошено явно
# ---------------------------------------------------------------------------
if $DO_FRONTEND; then
  if $FORCE_FRONTEND || $frontend_changed; then
    log "Фронтенд: пересобираю"
    [[ -x "$FRONTEND_DEPLOY_SCRIPT" ]] || die "$FRONTEND_DEPLOY_SCRIPT не найден или не исполняемый"
    "$FRONTEND_DEPLOY_SCRIPT"
  else
    echo -e "\nФронтенд не менялся — пересборку пропускаю."
  fi
fi

log "Готово"
