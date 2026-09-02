#!/usr/bin/env bash
# Сборка и развёртывание фронтенда на этом же сервере (вместо Vercel).
# Запускать от deploy, из /opt/astro:  ./04-frontend-deploy.sh
set -euo pipefail

APP_DIR="app"
FRONTEND_SRC_DIR="${APP_DIR}/frontend"
DIST_TARGET="frontend/dist"
BUILD_ENV_FILE="frontend.env"
NGINX_DIR_SRC="${APP_DIR}/deploy/opt-astro/nginx"
NGINX_SITE_SRC="${NGINX_DIR_SRC}/astreatime.conf"
NGINX_SITE_DST="/etc/nginx/sites-available/astreatime.conf"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/astreatime.conf"
# Защитные заголовки и CSP лежат отдельными файлами: add_header не наследуется
# в location, где есть свой add_header, поэтому их приходится include-ить в
# каждый блок, а не писать один раз в server.
NGINX_SNIPPETS_SRC="${NGINX_DIR_SRC}/snippets"
NGINX_SNIPPETS_DST="/etc/nginx/snippets"
# Директивы уровня http (server_tokens, TLS-политика, зоны limit_req) — внутрь
# server{} их положить нельзя, отсюда отдельный файл в conf.d.
NGINX_CONFD_SRC="${NGINX_DIR_SRC}/conf.d/00-astro-hardening.conf"
NGINX_CONFD_DST="/etc/nginx/conf.d/00-astro-hardening.conf"
NODE_MIN_MAJOR=20
# Куда складывать копии конфигов перед перезаписью. Один каталог на запуск,
# имя — временная метка, чтобы прогоны не затирали друг друга.
NGINX_BACKUP_ROOT="nginx-backup"
# Сколько прогонов хранить. Каталог создаётся на КАЖДЫЙ запуск, включая
# --nginx-check, который ничего не доставляет, — без ротации их копилось
# неограниченно.
NGINX_BACKUP_KEEP=10

# --nginx-check: только проверить конфиг nginx и откатиться. Ни сборки, ни
# публикации dist, ни reload. Нужен, чтобы прогнать путь
# «бэкап -> копирование -> nginx -t -> откат» на живом сервере, ничего не
# сломав: после него состояние /etc/nginx побайтно прежнее.
NGINX_CHECK_ONLY=false
case "${1:-}" in
  --nginx-check) NGINX_CHECK_ONLY=true ;;
  "") ;;
  *) echo "Неизвестный аргумент: $1" >&2
     echo "Использование: $0 [--nginx-check]" >&2
     exit 2 ;;
esac

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$APP_DIR" ]] || die "каталог '$APP_DIR' не найден. Запускайте из /opt/astro."
[[ -f "$NGINX_SITE_SRC" ]] || die "'$NGINX_SITE_SRC' не найден рядом со скриптом."
[[ -d "$NGINX_SNIPPETS_SRC" ]] || die "'$NGINX_SNIPPETS_SRC' не найден — конфиг сайта его include-ит."
[[ -f "$NGINX_CONFD_SRC" ]] || die "'$NGINX_CONFD_SRC' не найден — в нём зоны limit_req и TLS-политика."
# Всё до nginx — Node, git pull, сборка и публикация dist — в режиме
# --nginx-check пропускается: он проверяет ТОЛЬКО конфиг и обязан не
# оставлять следов. Проверяется тот конфиг, что сейчас лежит в
# app/deploy/opt-astro/nginx/ — при необходимости обновите app/ заранее.
if ! $NGINX_CHECK_ONLY; then

  # ---------------------------------------------------------------------------
  # Node.js LTS из NodeSource — идемпотентно
  # ---------------------------------------------------------------------------
  log "Проверяю Node.js"
  need_node_install=true
  if command -v node >/dev/null 2>&1; then
    node_major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
    if [[ "$node_major" =~ ^[0-9]+$ ]] && (( node_major >= NODE_MIN_MAJOR )); then
      echo "  Node.js уже установлен: $(node --version) — пропускаю установку"
      need_node_install=false
    else
      echo "  установлен Node.js устаревшей версии ($(node --version) < v${NODE_MIN_MAJOR}) — переустанавливаю LTS"
    fi
  else
    echo "  Node.js не найден"
  fi

  if $need_node_install; then
    echo "  устанавливаю Node.js LTS из NodeSource"
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
    echo "  установлено: $(node --version)"
  fi

  # ---------------------------------------------------------------------------
  # git pull
  # ---------------------------------------------------------------------------
  log "Обновляю $APP_DIR (git pull)"
  git -C "$APP_DIR" fetch --quiet
  before_rev="$(git -C "$APP_DIR" rev-parse HEAD)"
  git -C "$APP_DIR" pull --ff-only
  after_rev="$(git -C "$APP_DIR" rev-parse HEAD)"
  if [[ "$before_rev" == "$after_rev" ]]; then
    echo "  уже на актуальном коммите ($after_rev), изменений нет"
  else
    echo "  $before_rev -> $after_rev"
  fi

  # ---------------------------------------------------------------------------
  # Сборка фронтенда
  # ---------------------------------------------------------------------------
  log "Собираю фронтенд"

  if [[ -f "$BUILD_ENV_FILE" ]]; then
    echo "  подключаю build-переменные из $BUILD_ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    source "$BUILD_ENV_FILE"
    set +a
  else
    echo "  файл $BUILD_ENV_FILE не найден рядом со скриптом (см. README про VITE_GOOGLE_CLIENT_ID)"
  fi

  if [[ -z "${VITE_GOOGLE_CLIENT_ID:-}" ]]; then
    echo "  ПРЕДУПРЕЖДЕНИЕ: VITE_GOOGLE_CLIENT_ID не задан — соберу без него, вход через Google Calendar на фронте не заработает"
  fi

  export NODE_OPTIONS="--max-old-space-size=2048"

  (
    cd "$FRONTEND_SRC_DIR"
    npm ci
    npm run build
    # Сборка, из которой вырезана фича, не должна доехать до nginx. Vite
    # подставляет VITE_* как константы времени сборки: при пустом значении
    # весь код за проверкой на эту переменную выбрасывается как недостижимый,
    # а npm run build при этом возвращает 0. Скрипт грепает dist на строки,
    # которые обязаны там быть, и падает, если их нет; проверки, чья
    # переменная не задана, он пропускает сам. Скрипт под set -euo pipefail,
    # поэтому ненулевой код остановит деплой до публикации dist.
    npm run assert-bundle
  )

  # ---------------------------------------------------------------------------
  # Публикация dist (атомарная замена, чтобы nginx не отдавал наполовину
  # скопированный каталог)
  # ---------------------------------------------------------------------------
  # Всё через sudo, целиком. Раньше здесь не было sudo нигде, и это выглядело
  # согласованно — но один запуск скрипта целиком под sudo делал
  # /opt/astro/frontend/dist root-овым, после чего следующий запуск от deploy
  # умирал на `rm -rf "$DIST_TARGET"`. «Никогда не sudo» такое не лечит: deploy
  # не может удалить root-овый каталог. «Всегда sudo» лечит — root перезапишет
  # любого владельца. nginx каталог только читает, владелец ему безразличен.
  log "Публикую сборку в $DIST_TARGET"
  sudo mkdir -p "$(dirname "$DIST_TARGET")"
  sudo rm -rf "${DIST_TARGET}.new"
  sudo cp -r "${FRONTEND_SRC_DIR}/dist" "${DIST_TARGET}.new"
  sudo rm -rf "$DIST_TARGET"
  sudo mv "${DIST_TARGET}.new" "$DIST_TARGET"
  echo "  готово: $DIST_TARGET"
fi

# ---------------------------------------------------------------------------
# nginx: установить конфиг, отключить дефолтный сайт, проверить, перечитать
# ---------------------------------------------------------------------------
log "Обновляю конфиг nginx"

# Порядок здесь важнее содержимого. Раньше было: cp, cp, cp, nginx -t. При
# set -euo pipefail неудачная проверка убивала скрипт УЖЕ ПОСЛЕ перезаписи —
# в памяти оставался рабочий конфиг, на диске лежал сломанный, и сайт падал
# при следующем reload или перезагрузке, когда связь с деплоем никто уже не
# вспомнит. Теперь: бэкап -> копирование -> проверка -> откат при провале.

BACKUP_DIR="${NGINX_BACKUP_ROOT}/$(date +%Y%m%d-%H%M%S)"
# sudo, потому что наполняется каталог тоже через sudo (`sudo cp -p` ниже:
# читать /etc/nginx/* от deploy нельзя). Создание без sudo при наполнении с
# sudo — ровно та поломка, из-за которой скрипт переставал работать: один
# запуск целиком под sudo делал nginx-backup root-овым, и следующий запуск от
# deploy умирал здесь, на mkdir, ДО копирования конфигов. `sudo mkdir -p`
# отрабатывает при любом владельце.
sudo mkdir -p "$BACKUP_DIR"

# Список «куда пишем» -> «как называется копия». Бэкапим ровно те файлы,
# которые собираемся перезаписать, а не каталог целиком: в /etc/nginx/snippets
# могут лежать чужие файлы, и трогать их мы не должны ни при записи, ни при
# откате.
declare -a NGINX_TARGETS=()
NGINX_TARGETS+=("$NGINX_SITE_DST")
NGINX_TARGETS+=("$NGINX_CONFD_DST")
for f in "$NGINX_SNIPPETS_SRC"/*.conf; do
  NGINX_TARGETS+=("$NGINX_SNIPPETS_DST/$(basename "$f")")
done

# Разделяем «был файл» и «файла не было». Откат для первых — вернуть копию,
# для вторых — удалить созданное. Без этого частичный откат оставил бы
# половину нового конфига поверх старого, а это хуже, чем не откатываться:
# зоны limit_req и сам сайт обязаны меняться вместе.
declare -a NGINX_EXISTED=()
declare -a NGINX_CREATED=()
for dst in "${NGINX_TARGETS[@]}"; do
  if sudo test -f "$dst"; then
    sudo cp -p "$dst" "$BACKUP_DIR/$(basename "$dst")"
    NGINX_EXISTED+=("$dst")
  else
    NGINX_CREATED+=("$dst")
  fi
done
echo "  копии прежних конфигов: $(pwd)/$BACKUP_DIR (${#NGINX_EXISTED[@]} шт.)"

# Ротация. Имена каталогов — временные метки формата %Y%m%d-%H%M%S, поэтому
# лексикографическая сортировка совпадает с хронологической, и никаких дат
# парсить не нужно. Только что созданный каталог тоже считается — он самый
# свежий и остаётся всегда.
#
# Ротация идёт ПОСЛЕ создания и наполнения текущей копии, а не до: если
# удаление вдруг упадёт, копия, ради которой всё затевалось, уже на месте.
# `sudo rm`, потому что внутри лежат root-овые файлы от `sudo cp -p`.
prune_nginx_backups() {
  local stale count
  stale="$(find "$NGINX_BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | head -n "-${NGINX_BACKUP_KEEP}")"
  [[ -n "$stale" ]] || return 0
  count="$(printf '%s\n' "$stale" | wc -l)"
  echo "  ротация: удаляю старых копий — ${count}, оставляю последние ${NGINX_BACKUP_KEEP}"
  printf '%s\n' "$stale" | while IFS= read -r d; do
    [[ -n "$d" ]] && sudo rm -rf "$d"
  done
}
prune_nginx_backups

rollback_nginx() {
  echo "  ОТКАТ: возвращаю прежние конфиги" >&2
  local dst
  for dst in "${NGINX_EXISTED[@]:-}"; do
    [[ -n "$dst" ]] || continue
    sudo cp -p "$BACKUP_DIR/$(basename "$dst")" "$dst"
  done
  for dst in "${NGINX_CREATED[@]:-}"; do
    [[ -n "$dst" ]] || continue
    sudo rm -f "$dst"
  done
  # Убеждаемся, что вернули рабочее состояние, а не второе сломанное.
  if sudo nginx -t; then
    echo "  откат выполнен, конфиг на диске снова валиден" >&2
  else
    echo "  ВНИМАНИЕ: после отката nginx -t ТОЖЕ не проходит." >&2
    echo "  Значит конфиг был сломан ещё до этого запуска." >&2
    echo "  Копии лежат в $(pwd)/$BACKUP_DIR" >&2
  fi
}

# Сначала сниппеты и http-уровень: сайт их include-ит, и без них nginx -t упадёт.
sudo mkdir -p "$NGINX_SNIPPETS_DST"
sudo cp "$NGINX_SNIPPETS_SRC"/*.conf "$NGINX_SNIPPETS_DST/"
sudo cp "$NGINX_CONFD_SRC" "$NGINX_CONFD_DST"
sudo cp "$NGINX_SITE_SRC" "$NGINX_SITE_DST"
sudo ln -sf "$NGINX_SITE_DST" "$NGINX_SITE_LINK"

default_link_removed=false
if [[ -L /etc/nginx/sites-enabled/default ]]; then
  echo "  отключаю дефолтный сайт nginx (sites-enabled/default)"
  sudo rm -f /etc/nginx/sites-enabled/default
  default_link_removed=true
fi

echo "  nginx -t"
# ЧЕРЕЗ if, а не голой командой: при set -e ненулевой код прервал бы скрипт
# здесь же, и до отката управление не дошло бы — то есть ровно тот сценарий,
# ради которого всё это и написано.
if ! sudo nginx -t; then
  rollback_nginx
  die "nginx -t не прошёл на новом конфиге. Прежний возвращён, nginx не перечитывался (работает старый конфиг из памяти). Разбирайтесь с $NGINX_SITE_SRC и повторяйте."
fi

if $NGINX_CHECK_ONLY; then
  log "Режим --nginx-check: конфиг валиден, откатываю и выхожу"
  rollback_nginx
  if $default_link_removed; then
    echo "  ВНИМАНИЕ: символическая ссылка sites-enabled/default была удалена и НЕ восстановлена." >&2
    echo "  Это единственное, что --nginx-check меняет необратимо." >&2
  fi
  echo
  echo "Проверка пройдена: новый конфиг валиден на этом сервере."
  echo "Состояние /etc/nginx возвращено к прежнему, nginx не перечитывался."
  echo "Копии: $(pwd)/$BACKUP_DIR"
  exit 0
fi

echo "  systemctl reload nginx"
sudo systemctl reload nginx

log "Готово"
cat <<EOF

Фронтенд собран и опубликован: $(pwd)/$DIST_TARGET
nginx перечитан, конфиг: $NGINX_SITE_DST

EOF
