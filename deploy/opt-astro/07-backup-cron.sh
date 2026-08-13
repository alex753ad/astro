#!/usr/bin/env bash
# Ежедневный дамп БД: pg_dump -> gzip -> шифрование -> проверка -> выгрузка
# в объектное хранилище -> ротация (14 дней локально).
# Рассчитан на systemd-таймер astro-backup.timer (ставится 08-setup-automation.sh),
# но можно запускать и вручную из /opt/astro:  ./07-backup-cron.sh
#
# ── Зачем шифрование и выгрузка ──────────────────────────────────────────────
# Дамп содержит все ПДн пользователей, bcrypt-хеши паролей и платёжную историю,
# а лежал он рядом с самой БД, на том же диске, открытым текстом. Компрометация
# или отказ этого диска означали одновременно и утечку, и потерю бэкапов —
# то есть бэкапов фактически не было.
#
# ── Что нужно настроить один раз ─────────────────────────────────────────────
#   BACKUP_AGE_RECIPIENTS — публичные ключи age через запятую (или файл через
#     BACKUP_AGE_RECIPIENTS_FILE). Приватный ключ на сервере не хранится:
#     сервер умеет только зашифровать, расшифровать — нет. Это и есть смысл.
#     Сгенерировать пару на СВОЁЙ машине:  age-keygen -o astro-backup.key
#     В .env кладём только строку "age1..." из вывода.
#   BACKUP_S3_TARGET  — например s3://astro-backups/db (rclone remote или
#     s3-совместимый бакет Timeweb Object Storage). Пусто — выгрузка пропускается.
#   BACKUP_S3_PROFILE — профиль aws-cli/rclone, если их несколько.
#
# Без BACKUP_AGE_RECIPIENTS скрипт откажется работать: молча складывать
# незашифрованные ПДн — ровно то поведение, от которого уходим.
#
# set -e намеренно не используется — при любой ошибке идём в fail(), которая
# сама шлёт алерт в Telegram и завершает скрипт с кодом 1.
set -uo pipefail

BACKUP_DIR="backups"
KEEP_DAYS=14
STAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/daily_${STAMP}.dump.gz"
ENC_FILE="${DUMP_FILE}.age"

get_env_var() { grep -E "^${1}=" .env 2>/dev/null | head -1 | cut -d= -f2-; }

notify_telegram() {
  local text="$1" token chat_id cfg
  token="$(get_env_var TELEGRAM_BOT_TOKEN)"
  chat_id="$(get_env_var TELEGRAM_SUPPORT_CHAT_ID)"
  [[ -n "$token" && -n "$chat_id" ]] || return 0
  # Токен уходит в файл конфигурации, а не в аргументы: всё, что стоит в
  # командной строке, видно в `ps` любому пользователю системы на время запроса.
  cfg="$(mktemp)"
  chmod 600 "$cfg"
  printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$token" > "$cfg"
  curl -sS -m 10 -X POST --config "$cfg" \
    --data-urlencode "chat_id=${chat_id}" \
    --data-urlencode "text=${text}" >/dev/null 2>&1 || true
  rm -f "$cfg"
}

fail() {
  echo "ERROR: $*" >&2
  notify_telegram "🔴 astro: ежедневный бэкап БД упал на $(hostname): $*"
  exit 1
}

[[ -f docker-compose.yml ]] || fail "docker-compose.yml не найден. Запускайте из /opt/astro."
[[ -f .env ]] || fail ".env не найден."

pg_cid="$(docker compose ps -q postgres)"
[[ -n "$pg_cid" ]] || fail "контейнер postgres не запущен."

PG_USER="$(get_env_var POSTGRES_USER)"
PG_DB="$(get_env_var POSTGRES_DB)"
[[ -n "$PG_USER" && -n "$PG_DB" ]] || fail "POSTGRES_USER/POSTGRES_DB не найдены в .env"

AGE_RECIPIENTS="$(get_env_var BACKUP_AGE_RECIPIENTS)"
AGE_RECIPIENTS_FILE="$(get_env_var BACKUP_AGE_RECIPIENTS_FILE)"
S3_TARGET="$(get_env_var BACKUP_S3_TARGET)"

command -v age >/dev/null 2>&1 || fail "age не установлен: sudo apt-get install -y age"
[[ -n "$AGE_RECIPIENTS" || -n "$AGE_RECIPIENTS_FILE" ]] \
  || fail "BACKUP_AGE_RECIPIENTS не задан в .env — незашифрованные дампы с ПДн не делаем."

mkdir -p "$BACKUP_DIR"
# Каталог с дампами не должен читаться кем попало на сервере.
chmod 700 "$BACKUP_DIR"

docker compose exec -T postgres pg_dump -Fc -U "$PG_USER" "$PG_DB" | gzip > "$DUMP_FILE" \
  || fail "pg_dump | gzip завершились с ошибкой"

[[ -s "$DUMP_FILE" ]] || fail "дамп получился пустым: $DUMP_FILE"

gzip -t "$DUMP_FILE" || fail "дамп не проходит проверку gzip -t (архив битый): $DUMP_FILE"

# pg_restore -l только читает оглавление архива (список таблиц/объектов),
# ничего не восстанавливает — безопасная проверка, что это валидный
# custom-format дамп pg_dump, а не просто непустой файл мусора.
#
# custom-format (-Fc) требует seekable-файл — pg_restore -l не умеет читать
# его из потока (`-` / stdin). Прежняя версия скармливала поток напрямую и
# падала на ЛЮБОМ дампе, включая полностью корректный, — то есть проверка
# была нерабочей с самого начала. Пишем во временный файл внутри контейнера.
if ! gunzip -c "$DUMP_FILE" | docker compose exec -T postgres sh -c \
    'cat > /tmp/_check.dump && pg_restore -l /tmp/_check.dump >/dev/null 2>&1; rc=$?; rm -f /tmp/_check.dump; exit $rc'; then
  fail "дамп не проходит проверку pg_restore -l (не читается как валидный дамп): $DUMP_FILE"
fi

# ---------------------------------------------------------------------------
# Шифрование. Проверки выше делались на открытом дампе — иначе они проверяли бы
# только то, что age умеет писать файлы.
# ---------------------------------------------------------------------------
if [[ -n "$AGE_RECIPIENTS_FILE" ]]; then
  age -R "$AGE_RECIPIENTS_FILE" -o "$ENC_FILE" "$DUMP_FILE" \
    || fail "age -R завершился с ошибкой (файл получателей: $AGE_RECIPIENTS_FILE)"
else
  # Получателей может быть несколько через запятую — каждому свой -r.
  age_args=()
  IFS=',' read -ra _recipients <<< "$AGE_RECIPIENTS"
  for r in "${_recipients[@]}"; do
    r="$(echo "$r" | xargs)"
    [[ -n "$r" ]] && age_args+=(-r "$r")
  done
  age "${age_args[@]}" -o "$ENC_FILE" "$DUMP_FILE" || fail "age завершился с ошибкой"
fi

[[ -s "$ENC_FILE" ]] || fail "зашифрованный файл пуст: $ENC_FILE"
chmod 600 "$ENC_FILE"

# Открытый дамп на диске не оставляем — ради этого всё и затевалось.
shred -u "$DUMP_FILE" 2>/dev/null || rm -f "$DUMP_FILE"

echo "OK: $ENC_FILE ($(du -h "$ENC_FILE" | cut -f1))"

# ---------------------------------------------------------------------------
# Выгрузка за пределы хоста. Бэкап на том же диске, что и БД, не спасает от
# самого частого сценария — отказа или компрометации этого диска.
# ---------------------------------------------------------------------------
if [[ -n "$S3_TARGET" ]]; then
  if command -v rclone >/dev/null 2>&1 && [[ "$S3_TARGET" != s3://* ]]; then
    rclone copy "$ENC_FILE" "$S3_TARGET" --quiet \
      || fail "rclone copy в $S3_TARGET не удался"
  elif command -v aws >/dev/null 2>&1; then
    aws s3 cp "$ENC_FILE" "${S3_TARGET%/}/$(basename "$ENC_FILE")" --only-show-errors \
      || fail "aws s3 cp в $S3_TARGET не удался"
  else
    fail "BACKUP_S3_TARGET задан, но ни rclone, ни aws-cli не установлены."
  fi
  echo "Выгружено: ${S3_TARGET%/}/$(basename "$ENC_FILE")"
else
  echo "!! BACKUP_S3_TARGET не задан — копия осталась только на этом сервере."
fi

deleted=0
while IFS= read -r -d '' old; do
  rm -f "$old"
  deleted=$((deleted + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 \( -name 'daily_*.dump.gz' -o -name 'daily_*.dump.gz.age' \) -mtime "+${KEEP_DAYS}" -print0)
echo "Ротация: удалено файлов старше ${KEEP_DAYS}д: ${deleted}"

# Раз в квартал восстановление обязано проверяться руками: бэкап, который
# никогда не разворачивали, — это не бэкап, а надежда. Порядок:
#   age -d -i astro-backup.key daily_*.dump.gz.age | gunzip > restore.dump
#   ./03-db-restore.sh restore.dump   (на тестовом сервере, не на проде)
