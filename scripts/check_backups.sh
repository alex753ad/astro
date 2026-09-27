#!/usr/bin/env bash
# check_backups.sh — можно ли восстановиться из бэкапа и почему дамп 26.09
# меньше дампа 25.09 на 19%.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_backups.sh
#
# Спросит закрытый ключ age скрытым вводом (из «ключ для бэкап.txt» на машине
# владельца). Для каждого из трёх файлов — последний, за 25.09 и за 26.09 —
# расшифровка в /dev/shm, gzip -t, pg_restore -l, и число строк по каждой
# таблице: pg_restore отдаёт данные SQL-текстом, строки считаются в блоках
# COPY. В базу НИЧЕГО не восстанавливается и не пишется — прод не тронут.
# Временные файлы удаляются при любом исходе.
#
# Успех по последнему бэкапу пишет метку diag/backup_restore_ok с публичным
# ключом введённого закрытого: по ней remove_backup_key.sh убеждается, что
# ключ владельца — ТОТ ЖЕ, что лежит на сервере, прежде чем удалять серверный.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_backups-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

TMP=$(mktemp -d /dev/shm/backupcheck.XXXX); chmod 700 "$TMP"
cleanup() { rm -rf "$TMP"; docker compose exec -T postgres sh -c 'rm -f /tmp/bc_*.dump' </dev/null >/dev/null 2>&1; }
trap cleanup EXIT

read -rs -p "Закрытый ключ age (строка AGE-SECRET-KEY-…) и Enter: " KEY </dev/tty; echo
[ -n "$KEY" ] || { echo "ключ не введён — выход"; exit 1; }
printf '%s\n' "$KEY" > "$TMP/key"; chmod 600 "$TMP/key"; KEY=""
PUB=$(age-keygen -y "$TMP/key" 2>/dev/null) || { echo "это не ключ age — выход"; exit 1; }
echo "публичный ключ введённого: $PUB"
echo "получатель в .env:         $(grep -E '^BACKUP_AGE_RECIPIENTS=' .env | cut -d= -f2-)"

LAST=$(ls -1t backups/daily_*.dump.gz.age 2>/dev/null | head -1)
D25=$(ls -1 backups/daily_20260925_*.dump.gz.age 2>/dev/null | head -1)
D26=$(ls -1 backups/daily_20260926_*.dump.gz.age 2>/dev/null | head -1)

# $1 — файл, $2 — метка. Печатает итог, строки «таблица число» кладёт в $TMP/$2.counts.
check_one() {
  local f="$1" tag="$2"
  echo "== $tag: $f ($(du -h "$f" | cut -f1))"
  age -d -i "$TMP/key" -o "$TMP/$tag.gz" "$f" 2>"$TMP/err" || { echo "   ⚠️ не расшифровывается: $(cat "$TMP/err")"; return 1; }
  gzip -t "$TMP/$tag.gz" || { echo "   ⚠️ gzip битый"; return 1; }
  gunzip -c "$TMP/$tag.gz" > "$TMP/$tag.dump"; rm -f "$TMP/$tag.gz"
  docker compose cp "$TMP/$tag.dump" "postgres:/tmp/bc_$tag.dump" </dev/null >/dev/null || { echo "   ⚠️ не скопировать в контейнер"; return 1; }
  rm -f "$TMP/$tag.dump"
  local toc
  toc=$(docker compose exec -T postgres pg_restore -l "/tmp/bc_$tag.dump" </dev/null 2>&1) || { echo "   ⚠️ pg_restore -l: $toc" | head -3; return 1; }
  echo "   расшифровка, gzip, оглавление: OK ($(echo "$toc" | grep -c 'TABLE DATA') таблиц с данными)"
  docker compose exec -T postgres sh -c "pg_restore --data-only -f - /tmp/bc_$tag.dump" </dev/null \
    | awk '/^COPY /{t=$2; n=0; inb=1; next} inb && /^\\\.$/{print t, n; inb=0; next} inb{n++}' \
    | LC_ALL=C sort > "$TMP/$tag.counts"
  echo "   строк всего: $(awk '{s+=$2} END{print s+0}' "$TMP/$tag.counts")"
}

OK_LAST=0
[ -n "$LAST" ] && check_one "$LAST" last && OK_LAST=1
[ -n "$D25" ] && check_one "$D25" d25
[ -n "$D26" ] && check_one "$D26" d26

if [ -s "$TMP/d25.counts" ] && [ -s "$TMP/d26.counts" ]; then
  echo "== таблицы, где число строк 25.09 → 26.09 изменилось"
  LC_ALL=C join -a1 -a2 -e 0 -o 0,1.2,2.2 "$TMP/d25.counts" "$TMP/d26.counts" \
    | awk '$2 != $3 {printf "   %-40s %8d → %-8d (%+d)\n", $1, $2, $3, $3-$2}'
  echo "== сейчас в базе по этим таблицам"
  LC_ALL=C join -a1 -a2 -e 0 -o 0,1.2,2.2 "$TMP/d25.counts" "$TMP/d26.counts" | awk '$2 != $3 {print $1}' | while read -r t; do
    n=$(docker compose exec -T postgres sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'select count(*) from $t'" </dev/null 2>&1)
    echo "   $t: $n"
  done
fi

if [ "$OK_LAST" = 1 ]; then
  printf 'date=%s\npub=%s\nfile=%s\n' "$(date -u +%FT%TZ)" "$PUB" "$LAST" > diag/backup_restore_ok
  echo "метка diag/backup_restore_ok записана — можно запускать remove_backup_key.sh"
else
  rm -f diag/backup_restore_ok
  echo "⚠️ последний бэкап НЕ прошёл проверку — ключ с сервера не удалять"
fi
echo "== конец. Лог: /opt/astro/$LOG"
