#!/usr/bin/env bash
# Единый установщик задач 4-6: Uptime Kuma + nginx-доступ к нему по
# basic-auth, systemd-таймеры ежедневного бэкапа и еженедельной чистки
# образов, обновлённый api-healthcheck (уже в docker-compose.yml).
# Идемпотентен — повторный запуск ничего не ломает.
# Запускать от deploy, из /opt/astro:  ./08-setup-automation.sh
set -euo pipefail

HTPASSWD_FILE="/etc/nginx/.htpasswd-status"
HTPASSWD_USER="admin"
NGINX_SITE_SRC="nginx/status.astreatime.conf"
NGINX_SITE_DST="/etc/nginx/sites-available/status.astreatime.conf"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/status.astreatime.conf"
SYSTEMD_SRC_DIR="systemd"
SYSTEMD_DST_DIR="/etc/systemd/system"
UNITS=(astro-backup.service astro-backup.timer astro-prune.service astro-prune.timer)

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f docker-compose.yml ]] || die "docker-compose.yml не найден. Запускайте из /opt/astro."
[[ -f .env ]] || die ".env не найден."
[[ -f "$NGINX_SITE_SRC" ]] || die "'$NGINX_SITE_SRC' не найден рядом со скриптом."

# ---------------------------------------------------------------------------
# htpasswd (apache2-utils) — идемпотентно
# ---------------------------------------------------------------------------
log "Проверяю apache2-utils (htpasswd)"
if ! command -v htpasswd >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y apache2-utils
else
  echo "  уже установлен"
fi

# ---------------------------------------------------------------------------
# Basic-auth для status.astreatime.ru — генерируем один раз, если файла ещё нет
# ---------------------------------------------------------------------------
log "Проверяю $HTPASSWD_FILE"
if [[ -f "$HTPASSWD_FILE" ]]; then
  echo "  уже существует — не трогаю (пароль не перегенерирую, чтобы не сломать уже сохранённый доступ)"
else
  generated_password="$(openssl rand -base64 18)"
  sudo htpasswd -bc "$HTPASSWD_FILE" "$HTPASSWD_USER" "$generated_password"
  cat <<EOF

  Создан доступ к status.astreatime.ru:
    логин:  $HTPASSWD_USER
    пароль: $generated_password

  Сохраните пароль сейчас — второй раз он нигде не выводится и не хранится
  в открытом виде (только bcrypt-хэш в $HTPASSWD_FILE).
EOF
fi

# ---------------------------------------------------------------------------
# Uptime Kuma — поднимаем контейнер, остальные не трогаем
# ---------------------------------------------------------------------------
log "Поднимаю uptime-kuma"
docker compose up -d --no-deps uptime-kuma

# ---------------------------------------------------------------------------
# nginx: status.astreatime.ru
# ---------------------------------------------------------------------------
log "Устанавливаю nginx-конфиг для status.astreatime.ru"
sudo cp "$NGINX_SITE_SRC" "$NGINX_SITE_DST"
sudo ln -sf "$NGINX_SITE_DST" "$NGINX_SITE_LINK"
sudo nginx -t
sudo systemctl reload nginx

# ---------------------------------------------------------------------------
# systemd: таймеры бэкапа и чистки образов
# ---------------------------------------------------------------------------
log "Устанавливаю systemd-юниты: ${UNITS[*]}"
chmod +x 07-backup-cron.sh prune-and-diskcheck.sh
for unit in "${UNITS[@]}"; do
  sudo cp "${SYSTEMD_SRC_DIR}/${unit}" "${SYSTEMD_DST_DIR}/${unit}"
done
sudo systemctl daemon-reload
sudo systemctl enable --now astro-backup.timer astro-prune.timer

log "Готово"
cat <<EOF

Статус таймеров:
$(systemctl list-timers 'astro-*' --no-pager 2>/dev/null || true)

Дальше руками (см. README):
  1. DNS: A-запись status.astreatime.ru -> IP этого сервера (если ещё нет).
  2. Открыть http://status.astreatime.ru, ввести логин/пароль из вывода выше
     (или сохранённый ранее), пройти мастер первого запуска Uptime Kuma.
  3. В Uptime Kuma добавить монитор на https://www.astreatime.ru/health
     и настроить Telegram-уведомление (см. README).

EOF
