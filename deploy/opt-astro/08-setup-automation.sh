#!/usr/bin/env bash
# Единый установщик задач 4-6: Uptime Kuma + nginx-доступ к нему по
# basic-auth, systemd-таймеры ежедневного бэкапа и еженедельной чистки
# образов, обновлённый api-healthcheck (уже в docker-compose.yml).
# Идемпотентен — повторный запуск ничего не ломает.
# Запускать от deploy, из /opt/astro:  ./08-setup-automation.sh
set -euo pipefail

HTPASSWD_FILE="/etc/nginx/.htpasswd-status"
HTPASSWD_USER="admin"
STATUS_DOMAIN="status.astreatime.ru"
NGINX_SITE_SRC="nginx/status.astreatime.conf"
NGINX_SITE_DST="/etc/nginx/sites-available/status.astreatime.conf"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/status.astreatime.conf"
NGINX_SNIPPETS_SRC="nginx/snippets"
NGINX_SNIPPETS_DST="/etc/nginx/snippets"
CERT_DIR="/etc/letsencrypt/live/${STATUS_DOMAIN}"
ACME_WEBROOT="/var/www/html"
SYSTEMD_SRC_DIR="systemd"
SYSTEMD_DST_DIR="/etc/systemd/system"
UNITS=(
  astro-backup.service astro-backup.timer
  astro-prune.service astro-prune.timer
  astro-onboarding-emails.service astro-onboarding-emails.timer
  astro-pilot-tick.service astro-pilot-tick.timer
)

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
# age — шифрование ежедневных бэкапов (07-backup-cron.sh). Без него скрипт
# бэкапа падает на первой же проверке command -v age, а до сих пор ни один
# шаг провижининга его не ставил — на новом сервере бэкапы не работали бы
# вообще, молча (если бы не Telegram-алерт из fail() в 07-backup-cron.sh).
# ---------------------------------------------------------------------------
log "Проверяю age (шифрование бэкапов)"
if ! command -v age >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y age
else
  echo "  уже установлен"
fi

# ---------------------------------------------------------------------------
# Ключ age для шифрования бэкапов — идемпотентно, только если получатель ещё
# не задан в .env. Приватную часть на сервере не оставляем: печатаем один раз
# в терминал (как пароль basic-auth ниже) и сразу удаляем файл — иначе
# компрометация сервера давала бы доступ и к бэкапам, а весь смысл
# асимметричной схемы (сервер может зашифровать, расшифровать — нет) в этом
# и заключается. Существующий ключ НИКОГДА не перегенерируем: его потеря
# означает потерю всех бэкапов, а не просто неудобство.
# ---------------------------------------------------------------------------
log "Проверяю ключ age для бэкапов"
if grep -qE '^BACKUP_AGE_RECIPIENTS(_FILE)?=.+' .env 2>/dev/null; then
  echo "  получатель уже задан в .env — не трогаю"
else
  echo "  не найден — генерирую новую пару"
  key_file="$(mktemp)"
  chmod 600 "$key_file"
  age-keygen -o "$key_file" 2>/dev/null
  public_key="$(sed -n 's/^# public key: //p' "$key_file")"
  private_key="$(grep '^AGE-SECRET-KEY-' "$key_file")"
  rm -f "$key_file"
  printf '\nBACKUP_AGE_RECIPIENTS=%s\n' "$public_key" >> .env
  cat <<EOF

  Сгенерирован новый ключ age. Приватный ключ ниже НИГДЕ на сервере не
  сохранён и второй раз не выводится — сохраните его прямо сейчас вне
  сервера (менеджер паролей, свой диск):

  ${private_key}

  Публичная часть уже записана в .env (BACKUP_AGE_RECIPIENTS=${public_key}).
  Без сохранённого приватного ключа расшифровать бэкапы будет невозможно —
  это не восстанавливается.

EOF
fi

# ---------------------------------------------------------------------------
# Basic-auth для status.astreatime.ru — генерируем один раз, если файла ещё нет
# ---------------------------------------------------------------------------
log "Проверяю $HTPASSWD_FILE"
# Пароли, созданные до перевода поддомена на TLS, ходили по открытому HTTP и
# считаются скомпрометированными. Маркер нужен, чтобы ротация случилась ровно
# один раз, а не на каждом прогоне идемпотентного скрипта.
ROTATE_MARKER="/etc/nginx/.htpasswd-status.rotated-for-tls"

if [[ -f "$HTPASSWD_FILE" && -f "$ROTATE_MARKER" ]]; then
  echo "  уже существует и ротирован после перехода на TLS — не трогаю"
else
  action="Создан"
  [[ -f "$HTPASSWD_FILE" ]] && action="Заменён (прежний ходил по открытому HTTP)"
  generated_password="$(openssl rand -base64 18)"
  sudo htpasswd -bc "$HTPASSWD_FILE" "$HTPASSWD_USER" "$generated_password"
  sudo touch "$ROTATE_MARKER"
  cat <<EOF

  ${action} доступ к ${STATUS_DOMAIN}:
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
#
# Панель обязана жить за TLS: basic-auth передаёт логин и пароль в заголовке
# base64 при КАЖДОМ запросе, и по открытому HTTP их читает любой на пути.
# Поэтому порядок такой: сертификат -> конфиг с 443. Если сертификата нет и
# получить не вышло — панель наружу не публикуется вовсе (только ACME-челлендж),
# а не откатывается на HTTP.
# ---------------------------------------------------------------------------
log "Проверяю TLS-сертификат для ${STATUS_DOMAIN}"

install_acme_only_vhost() {
  sudo tee "$NGINX_SITE_DST" >/dev/null <<EOF
# Временный конфиг: сертификата ещё нет. Наружу отдаём только ACME-челлендж,
# панель не публикуем — по HTTP это означало бы пароль открытым текстом.
server {
    listen 80;
    listen [::]:80;
    server_name ${STATUS_DOMAIN};

    location /.well-known/acme-challenge/ { root ${ACME_WEBROOT}; }
    location / { return 403; }
}
EOF
  sudo ln -sf "$NGINX_SITE_DST" "$NGINX_SITE_LINK"
  sudo nginx -t && sudo systemctl reload nginx
}

if [[ ! -f "${CERT_DIR}/fullchain.pem" ]]; then
  echo "  сертификата нет — выпускаю через certbot (webroot)"
  if ! command -v certbot >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y certbot
  fi
  sudo mkdir -p "$ACME_WEBROOT"
  install_acme_only_vhost
  sudo certbot certonly --webroot -w "$ACME_WEBROOT" -d "$STATUS_DOMAIN" \
       --non-interactive --agree-tos --register-unsafely-without-email \
    || echo "  !! certbot не справился (нет A-записи ${STATUS_DOMAIN}?)"
else
  echo "  сертификат на месте"
fi

log "Устанавливаю nginx-конфиг для ${STATUS_DOMAIN}"
if [[ -f "${CERT_DIR}/fullchain.pem" ]]; then
  # Сниппет с защитными заголовками — конфиг его include-ит, без него nginx -t упадёт.
  sudo mkdir -p "$NGINX_SNIPPETS_DST"
  sudo cp "$NGINX_SNIPPETS_SRC"/*.conf "$NGINX_SNIPPETS_DST/"
  sudo cp "$NGINX_SITE_SRC" "$NGINX_SITE_DST"
  sudo ln -sf "$NGINX_SITE_DST" "$NGINX_SITE_LINK"
  sudo nginx -t
  sudo systemctl reload nginx
else
  cat <<EOF

  !! ${STATUS_DOMAIN} остался закрытым (403): без сертификата публиковать
     панель по HTTP нельзя — basic-auth уехал бы открытым текстом.
     Заведите A-запись ${STATUS_DOMAIN} -> IP сервера и запустите скрипт снова.
     Пока панель доступна туннелем:
       ssh -L 3001:127.0.0.1:3001 <user>@<server>   ->  http://localhost:3001

EOF
fi

# ---------------------------------------------------------------------------
# systemd: таймеры бэкапа, чистки образов и служебных /internal/* эндпоинтов
# (onboarding-emails, pilot-tick — единственные внутренние ручки, которые не
# покрыты Celery Beat, потому что это обычный HTTP за X-Internal-Secret, а не
# Celery-задача; lunar-returns и weekly-digest уже в beat_schedule).
# ---------------------------------------------------------------------------
log "Устанавливаю systemd-юниты: ${UNITS[*]}"
chmod +x 07-backup-cron.sh prune-and-diskcheck.sh 09-internal-cron.sh
for unit in "${UNITS[@]}"; do
  sudo cp "${SYSTEMD_SRC_DIR}/${unit}" "${SYSTEMD_DST_DIR}/${unit}"
done
sudo systemctl daemon-reload
sudo systemctl enable --now \
  astro-backup.timer astro-prune.timer \
  astro-onboarding-emails.timer astro-pilot-tick.timer

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
