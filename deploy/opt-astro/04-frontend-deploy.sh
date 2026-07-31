#!/usr/bin/env bash
# Сборка и развёртывание фронтенда на этом же сервере (вместо Vercel).
# Запускать от deploy, из /opt/astro:  ./04-frontend-deploy.sh
set -euo pipefail

APP_DIR="app"
FRONTEND_SRC_DIR="${APP_DIR}/frontend"
DIST_TARGET="frontend/dist"
BUILD_ENV_FILE="frontend.env"
NGINX_SITE_SRC="nginx/astreatime.conf"
NGINX_SITE_DST="/etc/nginx/sites-available/astreatime.conf"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/astreatime.conf"
NODE_MIN_MAJOR=20

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$APP_DIR" ]] || die "каталог '$APP_DIR' не найден. Запускайте из /opt/astro."
[[ -f "$NGINX_SITE_SRC" ]] || die "'$NGINX_SITE_SRC' не найден рядом со скриптом."

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
)

# ---------------------------------------------------------------------------
# Публикация dist (атомарная замена, чтобы nginx не отдавал наполовину
# скопированный каталог)
# ---------------------------------------------------------------------------
log "Публикую сборку в $DIST_TARGET"
mkdir -p "$(dirname "$DIST_TARGET")"
rm -rf "${DIST_TARGET}.new"
cp -r "${FRONTEND_SRC_DIR}/dist" "${DIST_TARGET}.new"
rm -rf "$DIST_TARGET"
mv "${DIST_TARGET}.new" "$DIST_TARGET"
echo "  готово: $DIST_TARGET"

# ---------------------------------------------------------------------------
# nginx: установить конфиг, отключить дефолтный сайт, проверить, перечитать
# ---------------------------------------------------------------------------
log "Обновляю конфиг nginx"
sudo cp "$NGINX_SITE_SRC" "$NGINX_SITE_DST"
sudo ln -sf "$NGINX_SITE_DST" "$NGINX_SITE_LINK"

if [[ -L /etc/nginx/sites-enabled/default ]]; then
  echo "  отключаю дефолтный сайт nginx (sites-enabled/default)"
  sudo rm -f /etc/nginx/sites-enabled/default
fi

echo "  nginx -t"
sudo nginx -t
echo "  systemctl reload nginx"
sudo systemctl reload nginx

log "Готово"
cat <<EOF

Фронтенд собран и опубликован: $(pwd)/$DIST_TARGET
nginx перечитан, конфиг: $NGINX_SITE_DST

EOF
