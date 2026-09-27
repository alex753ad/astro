#!/usr/bin/env bash
# investigate_chart_deletions.sh — какие карты и разборы исчезли между дампами
# 25.09 и 26.09.2026 (natal_charts 77→72, interpretations 9→5), чьи они и каким
# путём удалены.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/investigate_chart_deletions.sh
#
# Только чтение. Спросит закрытый ключ age (как check_backups.sh), расшифрует два
# дампа в /dev/shm и прочитает из них ТОЛЬКО id, user_id и время создания —
# ни имён, ни дат и мест рождения скрипт не печатает. Временные файлы удаляются.
#
# Пути удаления в коде (все четыре идут через nginx):
#   DELETE /api/v1/profile/charts/{id}  — человек удаляет одну карту
#   DELETE /api/v1/profile/data         — человек удаляет все свои карты
#   DELETE /api/v1/auth/me              — человек удаляет аккаунт (карты каскадом)
#   DELETE /api/v1/admin/users/{id}     — админ удаляет пользователя (+ admin_audit_log)
# Разборы удаляются каскадом вместе с картой.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/investigate_chart_deletions-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

TMP=$(mktemp -d /dev/shm/chartdel.XXXX); chmod 700 "$TMP"
cleanup() { rm -rf "$TMP"; docker compose exec -T postgres sh -c 'rm -f /tmp/cd_*.dump' </dev/null >/dev/null 2>&1; }
trap cleanup EXIT

read -rs -p "Закрытый ключ age (AGE-SECRET-KEY-…) и Enter: " KEY </dev/tty; echo
[ -n "$KEY" ] || { echo "ключ не введён — выход"; exit 1; }
printf '%s\n' "$KEY" > "$TMP/key"; chmod 600 "$TMP/key"; KEY=""

for tag in 25 26; do
  f=$(ls -1 backups/daily_202609${tag}_*.dump.gz.age 2>/dev/null | head -1)
  [ -n "$f" ] || { echo "нет дампа за ${tag}.09"; exit 1; }
  echo "дамп ${tag}.09: $f"
  age -d -i "$TMP/key" "$f" | gunzip -c > "$TMP/d$tag.dump" || { echo "не расшифровать $f"; exit 1; }
  docker compose cp "$TMP/d$tag.dump" "postgres:/tmp/cd_$tag.dump" </dev/null >/dev/null
  rm -f "$TMP/d$tag.dump"
  for t in natal_charts interpretations users; do
    docker compose exec -T postgres pg_restore --data-only -t "$t" -f - "/tmp/cd_$tag.dump" </dev/null > "$TMP/$t.$tag.sql"
  done
done
rm -f "$TMP/key"

python3 - "$TMP" > "$TMP/report.txt" <<'PYEOF'
import json, sys
tmp = sys.argv[1]

def rows(table, tag, want):
    """Строки блока COPY как словари, только колонки из want (если они есть)."""
    out, cols = [], None
    for line in open(f"{tmp}/{table}.{tag}.sql", encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("COPY "):
            cols = [c.strip() for c in line[line.index("(") + 1:line.index(")")].split(",")]
            continue
        if cols is None:
            continue
        if line == chr(92) + ".":
            break
        vals = line.split("\t")
        rec = dict(zip(cols, vals))
        out.append({k: (None if rec.get(k) == chr(92) + "N" else rec.get(k)) for k in want if k in rec})
    return out

charts25 = {r["id"]: r for r in rows("natal_charts", "25", ("id", "user_id", "created_at"))}
charts26 = {r["id"] for r in rows("natal_charts", "26", ("id",))}
int25 = {r["id"]: r for r in rows("interpretations", "25", ("id", "chart_id", "created_at"))}
int26 = {r["id"] for r in rows("interpretations", "26", ("id",))}
users25 = {r["id"] for r in rows("users", "25", ("id",))}
users26 = {r["id"] for r in rows("users", "26", ("id",))}
gone_charts = [charts25[i] for i in charts25 if i not in charts26]
new_charts = [i for i in charts26 if i not in charts25]
gone_int = [int25[i] for i in int25 if i not in int26]
json.dump({
    "gone_charts": gone_charts, "new_charts": new_charts, "gone_int": gone_int,
    "users_gone": sorted(users25 - users26), "users_new": sorted(users26 - users25),
}, open(f"{tmp}/facts.json", "w"))
print("карт в 25.09: %d, в 26.09: %d; исчезло %d, появилось %d" % (len(charts25), len(charts26), len(gone_charts), len(new_charts)))
print("пользователей исчезло: %d, появилось: %d" % (len(users25 - users26), len(users26 - users25)))
print("разборов исчезло: %d" % len(gone_int))
for g in gone_int:
    print("   разбор %s карты %s от %s — карта %s" % (g["id"], g["chart_id"], g.get("created_at"),
          "тоже исчезла (каскад)" if g["chart_id"] in {c["id"] for c in gone_charts} else "НА МЕСТЕ"))
PYEOF
cat "$TMP/report.txt"

echo "== исчезнувшие карты и их владельцы (по текущей базе)"
docker compose cp "$TMP/facts.json" api:/tmp/chartdel_facts.json </dev/null >/dev/null
docker compose exec -T api python - <<'PYEOF'
import json, os
from backend.database import SessionLocal
from backend.models import AdminAuditLog, NatalChart, User

f = json.load(open("/tmp/chartdel_facts.json"))
os.remove("/tmp/chartdel_facts.json")
db = SessionLocal()
def mask(e):
    if not e or "@" not in e:
        return str(e)
    a, d = e.split("@", 1)
    return a[:2] + "***@" + d
by_user = {}
for c in f["gone_charts"]:
    by_user.setdefault(c.get("user_id"), []).append(c)
for uid, cs in by_user.items():
    if uid is None:
        print("анонимные (user_id пуст): %d" % len(cs))
    else:
        u = db.get(User, uid)
        if u is None:
            print("пользователь %s — В БАЗЕ НЕТ (удалён)" % uid)
        else:
            left = db.query(NatalChart).filter(NatalChart.user_id == uid).count()
            print("пользователь %s  %s  тариф=%s  admin=%s  создан=%s  карт сейчас=%d" % (
                uid, mask(u.email), u.tier, getattr(u, "is_admin", None), f"{u.created_at:%d.%m.%Y}" if u.created_at else "?", left))
    for c in cs:
        print("   карта %s создана %s" % (c["id"], c.get("created_at")))
print("пользователи, исчезнувшие между дампами:", f["users_gone"] or "нет")
rows = (db.query(AdminAuditLog).filter(AdminAuditLog.created_at >= "2026-09-25", AdminAuditLog.created_at < "2026-09-27")
        .order_by(AdminAuditLog.created_at).all()) if hasattr(AdminAuditLog, "created_at") else []
print("действия админа 25–26.09:", len(rows))
for r in rows:
    print("   %s %s %s цель=%s" % (r.created_at, mask(r.admin_email), r.action, r.target_user_id))
PYEOF

echo "== nginx: DELETE-запросы 25–26.09 (путь, код, время; IP без последнего октета)"
LOGS=$(ls /var/log/nginx/access.log* 2>/dev/null)
if [ -z "$LOGS" ]; then
  echo "журналов nginx нет"
elif [ ! -r /var/log/nginx/access.log ]; then
  # Без этой ветки пустой вывод выглядел бы как «запросов не было».
  echo "⚠️ нет прав на чтение /var/log/nginx — повтори с sudo: sudo bash scripts/investigate_chart_deletions.sh"
else
  for L in $LOGS; do
    case "$L" in *.gz) zcat "$L" 2>/dev/null ;; *) cat "$L" 2>/dev/null ;; esac
  done | grep -E '"DELETE /api/v1/(profile/charts|profile/data|auth/me|admin/users)' \
       | grep -E '(25|26)/Sep/2026' \
       | awk '{ip=$1; sub(/\.[0-9]+$/, ".x", ip); print $4, ip, $6, $7, $9}' | tr -d '["' | sort \
       || true
  echo "(конец списка; пусто — таких запросов в журнале нет)"
  echo "журналы: $(ls -l --time-style=+%F /var/log/nginx/access.log* 2>&1 | awk '{print $6, $7}' | tr '\n' ' ')"
fi
echo "== конец. Лог: /opt/astro/$LOG"
