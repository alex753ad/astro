#!/usr/bin/env bash
# check_offsite.sh — настроена ли копия бэкапов вне сервера и не шире ли ключи,
# чем нужно.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_offsite.sh
#
# Берёт BACKUP_S3_* из /opt/astro/.env. Проверяет:
#   1. список объектов (ListBucket)  — ОБЯЗАН работать;
#   2. загрузку пробного файла       — ОБЯЗАНА работать (остаётся в бакете как
#      offsite-check-<время>.txt, 20 байт; удалит правило жизненного цикла,
#      если оно на весь бакет, иначе — вручную в консоли);
#   3. чтение объекта (GetObject)    — ОБЯЗАНО быть запрещено;
#   4. удаление объекта (DeleteObject) — ОБЯЗАНО быть запрещено (пробуется на
#      том же пробном файле — бэкапы не трогаются).
# Бэкапы не читает и не удаляет.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_offsite-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
get_env_var() { grep -E "^${1}=" .env 2>/dev/null | head -1 | cut -d= -f2-; }
for _k in ENDPOINT REGION BUCKET ACCESS_KEY_ID SECRET_ACCESS_KEY; do
  export "BACKUP_S3_${_k}=$(get_env_var "BACKUP_S3_${_k}")"
done

python3 - <<'PYEOF'
import sys, time
sys.path.insert(0, "/opt/astro/app/backend")
import offsite_s3 as s3

cfg = s3.config_from_env()
if cfg is None:
    sys.exit("BACKUP_S3_* в .env заданы не все — копия вне сервера не настроена")
print("бакет:", cfg["bucket"], "endpoint:", cfg["endpoint"])

def attempt(name, fn, must):
    try:
        fn()
        ok = must == "работать"
        print(("OK  " if ok else "⚠️  ") + name + ": разрешено" + ("" if ok else " — ключи ШИРЕ нужного"))
    except Exception as e:
        ok = must == "запрещено"
        print(("OK  " if ok else "⚠️  ") + name + ": отказ — " + str(e)[:160])
    return ok

probe = "offsite-check-%d.txt" % int(time.time())
items = []
res = [
    attempt("список (ListBucket)", lambda: items.extend(s3.list_objects(cfg)), "работать"),
    attempt("загрузка (PutObject)", lambda: s3.put_object(cfg, probe, b"offsite check probe\n"), "работать"),
    attempt("чтение (GetObject)", lambda: s3._request(cfg, "GET", probe), "запрещено"),
    attempt("удаление (DeleteObject)", lambda: s3._request(cfg, "DELETE", probe), "запрещено"),
]
daily = sorted((ts, k) for k, ts in items if k.startswith("daily_"))
print("бэкапов в хранилище:", len(daily), ("последний: %s %s" % (daily[-1][1], daily[-1][0].strftime("%d.%m %H:%M UTC")) if daily else ""))
print("ИТОГ:", "всё как задумано" if all(res) else "есть расхождения — см. ⚠️ выше")
PYEOF
echo "== конец. Лог: /opt/astro/$LOG"
