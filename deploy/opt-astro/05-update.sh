#!/usr/bin/env bash
# Однокомандное обновление прод-стека.
# Запускать от deploy, из /opt/astro:  ./05-update.sh [--backend-only|--frontend-only]
set -euo pipefail

APP_DIR="app"
BACKUP_DIR="backups"
FRONTEND_DEPLOY_SCRIPT="./04-frontend-deploy.sh"
# Пути, изменение которых требует запуска 04-frontend-deploy.sh. Это НЕ только
# frontend/: тот же скрипт — единственный, кто кладёт на сервер конфиг nginx,
# сниппеты (security-headers, csp) и conf.d/00-astro-hardening.conf. Пока здесь
# стоял один frontend/, коммит, трогающий только deploy/opt-astro/nginx/, флага
# не поднимал, и конфиг на прод не уезжал вообще никогда — так он и отстал на
# четыре недели (обнаружено 31.08.2026). Повторный запуск не помогал: pull уже
# пустой, шаг пропускался, джоб зеленел.
FRONTEND_PATHS=(frontend/ deploy/opt-astro/nginx/)
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
  но фронтенд пересобирается ТОЛЬКО если менялся app/frontend/ либо
  app/deploy/opt-astro/nginx/ (второе — потому что конфиг nginx на сервер
  кладёт тот же 04-frontend-deploy.sh).

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

# ---------------------------------------------------------------------------
# Preflight: переменные, без которых контейнеры не поднимутся вовсе.
# Лучше отказаться сразу и внятно, чем на середине деплоя получить
# "REDIS_PASSWORD не задан" из подстановки в compose или падение api на старте
# из-за прод-guard'ов в main.py.
# ---------------------------------------------------------------------------
_env_has() { grep -qE "^${1}=.+" .env; }
for _required in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL \
                 REDIS_PASSWORD REDIS_URL JWT_SECRET INTERNAL_SECRET \
                 YOOKASSA_SHOP_ID YOOKASSA_SECRET_KEY; do
  _env_has "$_required" || die "в .env не задан ${_required} — деплой остановлен."
done
grep -qE '^REDIS_URL=redis://:[^@]+@' .env \
  || die "REDIS_URL без пароля — Redis теперь запускается с requirepass, приложение не подключится."

# ЮKassa. Те же правила, что и в прод-гварде backend/main.py — проверка
# только в приложении означает, что о проблеме узнаёшь на середине деплоя,
# когда старый контейнер уже погашен (так прод падал дважды, см. CLAUDE.md).
#
# 23.08.2026: обе переменные добавлены в обязательный список выше, поэтому
# сюда мы доходим, только когда обе заданы, и проверка «ровно одна из двух»
# ниже недостижима. Оставлена намеренно — страхует, если обязательность
# когда-нибудь снова смягчат, и держит отдельную внятную формулировку.
# Не удалять как «мёртвый код».
# (`&& die` здесь нельзя: при set -e несработавший grep уронил бы скрипт молча.)
_yk_id=0;  _env_has YOOKASSA_SHOP_ID    && _yk_id=1  || true
_yk_key=0; _env_has YOOKASSA_SECRET_KEY && _yk_key=1 || true
[[ "$_yk_id" == "$_yk_key" ]] \
  || die "ЮKassa настроена наполовину: в .env задана только одна из YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY. Задайте обе или ни одной."
if grep -qE '^YOOKASSA_SECRET_KEY=test_' .env; then
  die "YOOKASSA_SECRET_KEY — тестовый ключ (test_...) в боевом .env: подписки выдавались бы без реальной оплаты."
fi

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
    if ! git -C "$APP_DIR" diff --quiet "$before_rev" "$after_rev" -- "${FRONTEND_PATHS[@]}"; then
      frontend_changed=true
      echo "  затронут ${FRONTEND_PATHS[*]}"
    fi
  fi

  # 04-frontend-deploy.sh синхронизируется здесь же и ЭТО ВАЖНО: он единственный,
  # кто кладёт на сервер конфиг nginx, сниппеты, conf.d и собранный dist. До
  # 31.08.2026 его в списке не было — на сервере годами исполнялась копия,
  # положенная руками, и любая правка этого файла в репозитории туда не
  # доезжала вообще никак (ни повторным запуском, ни новым коммитом).
  #
  # Порядок работает в нашу пользу: синхронизация идёт ЗДЕСЬ, а вызов
  # "$FRONTEND_DEPLOY_SCRIPT" — в самом конце скрипта. 04 запускается отдельным
  # процессом и читает уже обновлённый файл, то есть новая версия подхватывается
  # в ТОМ ЖЕ запуске.
  log "Синхронизирую копии деплой-скриптов из $APP_DIR/deploy/opt-astro/ (temp + atomic mv)"
  dest_dir="$(pwd)"
  for f in 05-update.sh 04-frontend-deploy.sh docker-compose.yml 07-backup-cron.sh; do
    tmp="$(mktemp "${dest_dir}/.${f}.XXXXXX")"
    if ! cp "$APP_DIR/deploy/opt-astro/$f" "$tmp"; then
      rm -f "$tmp"
      die "не удалось скопировать $f во временный файл — рабочая копия не тронута."
    fi
    case "$f" in
      05-update.sh|04-frontend-deploy.sh|07-backup-cron.sh) chmod +x "$tmp" ;;
    esac
    mv -f "$tmp" "${dest_dir}/$f"
  done
  echo "  синхронизировано: 05-update.sh, 04-frontend-deploy.sh, docker-compose.yml, 07-backup-cron.sh"
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

  # Текущий образ помечаем как rollback-кандидат ДО пересборки — "docker compose
  # build" перезапишет тег astro-app:latest, другого способа вернуться к
  # работавшей версии контейнера потом не будет.
  have_rollback_image=false
  if docker image inspect astro-app:latest >/dev/null 2>&1; then
    docker tag astro-app:latest astro-app:rollback
    have_rollback_image=true
  fi

  log "Бэкенд: собираю образ (api, bot, worker, beat)"
  run_with_registry_retry docker compose build api bot worker beat

  # rollback: возвращает тег astro-app:latest на образ, работавший до этого
  # деплоя, и пересоздаёт api/bot/worker/beat из него. Откатывает только
  # контейнеры — применённые alembic-миграции вперёд не отменяются
  # (down-миграции на проде с живыми данными — отдельный, осознанный ручной
  # шаг, не то, что должно происходить автоматически).
  #
  # Определена ДО первого docker compose up: у bot есть
  # `depends_on: api: condition: service_healthy`, и compose ждёт healthy api
  # ВНУТРИ ОДНОГО ВЫЗОВА up (--no-deps только про соседние сервисы вне
  # списка, не про порядок между перечисленными). Если api не поднимется,
  # сам `up` вернёт ненулевой код — с `set -e` это раньше убивало скрипт
  # прежде, чем он успевал дойти до отката: новый (нездоровый) контейнер уже
  # заменил собой старый рабочий, а откатиться было нечем.
  rollback() {
    if ! $have_rollback_image; then
      echo "  нет предыдущего образа для отката (это был первый деплой) — откатывать нечего" >&2
      return
    fi
    echo "  откатываю astro-app:latest на предыдущий образ и пересоздаю api/bot/worker/beat" >&2
    docker tag astro-app:rollback astro-app:latest
    docker compose up -d --no-deps api bot worker beat
  }

  log "Бэкенд: пересоздаю api, bot, worker, beat из новой сборки (работавшие контейнеры не трогались до этого момента)"
  if ! docker compose up -d --no-deps api bot worker beat; then
    rollback
    die "api/bot/worker/beat не поднялись новой сборкой (не прошёл healthcheck) — выполнен откат на предыдущий образ."
  fi

  log "Бэкенд: применяю миграции (alembic upgrade head)"
  if ! docker compose exec -T api alembic upgrade head; then
    rollback
    die "alembic upgrade head упал — выполнен откат на предыдущий образ."
  fi

  log "Бэкенд: жду healthy"
  healthy=false
  # api healthcheck: interval 30s, retries 5, start_period 15s — до 180с в худшем
  # случае, поэтому ждём с запасом дольше, чем интервал самого healthcheck.
  for _ in $(seq 1 40); do
    api_cid="$(docker compose ps -q api)"
    status="$(docker inspect --format='{{.State.Health.Status}}' "$api_cid" 2>/dev/null || echo "unknown")"
    if [[ "$status" == "healthy" ]]; then
      healthy=true
      break
    fi
    sleep 5
  done
  if ! $healthy; then
    rollback
    die "api не стал healthy за 200с — выполнен откат на предыдущий образ."
  fi

  log "Бэкенд: проверяю /health и /health/db"
  if ! curl -sS -m 5 -f http://127.0.0.1:8000/health >/dev/null || \
     ! curl -sS -m 5 -f http://127.0.0.1:8000/health/db >/dev/null; then
    rollback
    die "/health или /health/db не отвечают после деплоя — выполнен откат на предыдущий образ."
  fi
  echo "  готово"
fi

# ---------------------------------------------------------------------------
# Фронтенд: только если менялся app/frontend/ или app/deploy/opt-astro/nginx/,
# либо запрошено явно
# ---------------------------------------------------------------------------
if $DO_FRONTEND; then
  if $FORCE_FRONTEND || $frontend_changed; then
    log "Фронтенд: пересобираю"
    [[ -x "$FRONTEND_DEPLOY_SCRIPT" ]] || die "$FRONTEND_DEPLOY_SCRIPT не найден или не исполняемый"
    "$FRONTEND_DEPLOY_SCRIPT"
  else
    echo -e "\nФронтенд и конфиг nginx не менялись — пересборку пропускаю."
  fi
fi

log "Готово"
