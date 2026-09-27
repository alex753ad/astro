#!/usr/bin/env bash
# remove_backup_key.sh — удалить закрытый ключ бэкапов с сервера.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/remove_backup_key.sh
#
# Ключ бэкап-скрипту не нужен: шифрование идёт на публичный ключ
# (BACKUP_AGE_RECIPIENTS). На сервере он только обесценивает шифрование —
# взломавший сервер получает и бэкапы, и ключ к ним.
#
# Удаляет ТОЛЬКО если:
#   * check_backups.sh успешно расшифровал последний бэкап (метка
#     diag/backup_restore_ok не старше суток);
#   * ключ, которым это сделано (копия владельца), тот же, что на сервере —
#     сравниваются публичные ключи;
#   * .env не ссылается на этот файл;
#   * владелец набрал «удалить».

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/remove_backup_key-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
KEYF="backups/astro-backup.key"
stop() { echo "СТОП: $*"; echo "== конец (ключ НЕ удалён). Лог: /opt/astro/$LOG"; exit 1; }

[ -f "$KEYF" ] || stop "$KEYF нет — удалять нечего"
[ -f diag/backup_restore_ok ] || stop "нет метки успешной проверки — сначала bash scripts/check_backups.sh"
MARK_AGE=$(( $(date +%s) - $(stat -c %Y diag/backup_restore_ok) ))
[ "$MARK_AGE" -lt 86400 ] || stop "метке проверки больше суток — повтори check_backups.sh"
MARK_PUB=$(grep '^pub=' diag/backup_restore_ok | cut -d= -f2-)
SRV_PUB=$(age-keygen -y "$KEYF" 2>/dev/null) || stop "age-keygen не читает $KEYF"
echo "ключ владельца (проверен): $MARK_PUB"
echo "ключ на сервере:           $SRV_PUB"
[ -n "$MARK_PUB" ] && [ "$MARK_PUB" = "$SRV_PUB" ] || stop "ключи РАЗНЫЕ — копия владельца не заменяет серверный"
grep -q "astro-backup.key" .env && stop ".env ссылается на astro-backup.key — сначала убрать ссылку"

read -r -p "Ключ проверен и совпадает. Набери «удалить», чтобы удалить $KEYF: " ANS </dev/tty
[ "$ANS" = "удалить" ] || stop "не подтверждено"
shred -u "$KEYF" 2>/dev/null || rm -f "$KEYF"
[ -f "$KEYF" ] && stop "файл остался на месте"
echo "удалён: $KEYF"
echo "⚠️ Теперь единственная копия ключа — у владельца. Потеряна она — бэкапы не открыть."
echo "== конец. Лог: /opt/astro/$LOG"
