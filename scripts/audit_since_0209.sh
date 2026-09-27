#!/usr/bin/env bash
# audit_since_0209.sh — что происходило с 02.09.2026, пока серверные сигналы
# не доходили до канала поддержки (сервер писал от @Aristeatimebot, а в канале
# был @astreyatimelinebot). Проверяются ФАКТЫ, а не уведомления.
#
# Только чтение. Меняет ровно одно — и только если введён ключ на шаге 1в:
# расшифровывает последний бэкап во временный файл в /dev/shm, читает его
# оглавление (pg_restore -l, в базу ничего не пишется) и удаляет файл.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/audit_since_0209.sh
#
# ⚠️ Сверка с ЮKassa и самопроверка появились только 24.09.2026 (493b7cd):
# до этой даты им нечего показывать. Логи контейнеров ротируются (10 МБ × 3),
# поэтому, насколько далеко они назад, скрипт печатает отдельно.

set -uo pipefail
SINCE="2026-09-02"
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/audit_since_0209-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

echo "######## 1. БЭКАПЫ"
echo "== 1а. файлы в /opt/astro/backups (хранятся ${KEEP_DAYS:-14} дней — старше удаляются ротацией)"
ls -l --time-style=+"%F %T" backups/ 2>&1 | grep -E "daily_|\.key|total" || echo "файлов бэкапа нет"
python3 - <<'PYEOF'
import datetime as dt, glob, os
files = sorted(glob.glob("/opt/astro/backups/daily_*.dump.gz.age"))
days = {dt.date.fromtimestamp(os.path.getmtime(f)) for f in files}
today = dt.date.today()
start = max(dt.date(2026, 9, 2), today - dt.timedelta(days=14))
missing = [d for d in (start + dt.timedelta(n) for n in range((today - start).days + 1)) if d not in days]
print("дней с бэкапом с %s: %d, без бэкапа: %s" % (start, len(days & {start + dt.timedelta(n) for n in range((today - start).days + 1)}),
      ", ".join(str(d) for d in missing) or "нет"))
if start > dt.date(2026, 9, 2):
    print("до %s файлов быть не может (ротация 14 дней) — эти дни только по журналу ниже" % start)
leftover = glob.glob("/opt/astro/backups/daily_*.dump.gz")
print("незашифрованные дампы на диске:", len(leftover))
PYEOF
[ -f backups/astro-backup.key ] && echo "⚠️ приватный ключ бэкапов лежит НА СЕРВЕРЕ: backups/astro-backup.key" || echo "приватного ключа на сервере нет (так и должно быть)"
echo "копия вне сервера (BACKUP_S3_TARGET): $(grep -qE '^BACKUP_S3_TARGET=.+' .env && echo задана || echo 'не задана — копии только на этом диске')"

echo "== 1б. журнал запусков astro-backup с $SINCE"
journalctl -u astro-backup.service --since "$SINCE" --no-pager -o short-iso 2>&1 \
  | grep -E "OK:|ERROR|Ошибка|ошибк|fail|Failed|Ротация|No journal|not seeing|Permission" | tail -60
systemctl list-timers 'astro-*' --all --no-pager 2>&1 | head -12

echo "== 1в. можно ли восстановиться из последнего бэкапа (только чтение)"
LAST=$(ls -1t backups/daily_*.dump.gz.age 2>/dev/null | head -1)
if [ -z "$LAST" ]; then
  echo "последнего бэкапа нет"
else
  echo "последний: $LAST ($(du -h "$LAST" | cut -f1))"
  KEY=""
  if [ -r /dev/tty ]; then
    read -rs -p "Вставь приватный ключ age (AGE-SECRET-KEY-…) и Enter; пусто — пропустить: " KEY </dev/tty; echo
  fi
  if [ -z "$KEY" ]; then
    echo "пропущено: без ключа расшифровать нельзя (ключ хранится вне сервера)"
  else
    TMP=$(mktemp -d /dev/shm/restorecheck.XXXX); chmod 700 "$TMP"
    trap 'rm -rf "$TMP"; docker compose exec -T postgres rm -f /tmp/restore_check.dump </dev/null >/dev/null 2>&1' EXIT
    printf '%s\n' "$KEY" > "$TMP/k"; chmod 600 "$TMP/k"; KEY=""
    if age -d -i "$TMP/k" -o "$TMP/d.gz" "$LAST" && gzip -t "$TMP/d.gz" && gunzip -c "$TMP/d.gz" > "$TMP/d.dump"; then
      rm -f "$TMP/k" "$TMP/d.gz"
      docker compose cp "$TMP/d.dump" postgres:/tmp/restore_check.dump </dev/null >/dev/null
      TOC=$(docker compose exec -T postgres pg_restore -l /tmp/restore_check.dump </dev/null)
      echo "расшифровка и gzip: OK"
      echo "оглавление: $(echo "$TOC" | grep -c 'TABLE DATA') таблиц с данными"
      for t in users natal_charts payment_events feedback alembic_version; do
        echo "$TOC" | grep -q "TABLE DATA public $t " && echo "   $t — есть" || echo "   $t — НЕТ"
      done
    else
      echo "⚠️ расшифровать или распаковать не удалось (неверный ключ или битый файл)"
    fi
  fi
fi

echo
echo "######## 2. СВЕРКА С ЮKASSA"
echo "== 2а. как далеко назад логи worker"
docker compose logs -t --no-log-prefix worker </dev/null 2>/dev/null | head -1 | cut -c1-19
echo "== 2б. строки итога сверки в логах (задача есть с 24.09)"
docker compose logs -t --no-log-prefix worker </dev/null 2>&1 | grep -E "Сверка:|reconcile_payments.*succeeded" | cut -c1-300 | tail -20
echo "== 2в. сверка заново, только чтение: успешные платежи ЮKassa с $SINCE против payment_events"
docker compose exec -T api python - <<'PYEOF'
import asyncio
from datetime import datetime, timezone
from backend.database import SessionLocal
from backend.models import PaymentEvent
from backend.payments.reconcile import list_succeeded, _no_tier_problem

since = datetime(2026, 9, 2, tzinfo=timezone.utc)
now = datetime.now(timezone.utc).replace(tzinfo=None)
payments = asyncio.run(list_succeeded(since))
db = SessionLocal()
if payments is None:
    print("⚠️ API ЮKassa не ответил — сверить нельзя")
else:
    print("успешных платежей в ЮKassa:", len(payments))
    for p in payments:
        pid = str(p.get("id"))
        ev = db.query(PaymentEvent).filter(PaymentEvent.inv_id == pid).first()
        amount = (p.get("amount") or {}).get("value")
        if ev is None:
            print("  ⚠️ %s %s ₽ %s — в ЮKassa есть, в базе НЕТ" % (pid, amount, p.get("created_at", "")[:10]))
        else:
            problem = _no_tier_problem(db, ev, p, now)
            print("  %s %s %s ₽ %s — %s" % ("⚠️" if problem else "ok", pid, amount, p.get("created_at", "")[:10],
                                          problem or "в базе, тариф в порядке"))
evs = db.query(PaymentEvent).filter(PaymentEvent.created_at >= since.replace(tzinfo=None)).order_by(PaymentEvent.created_at).all()
print("записей payment_events с 02.09:", len(evs))
for e in evs:
    print("  %s %s %s ₽ тариф=%s период=%s%s" % (f"{e.created_at:%d.%m %H:%M}", e.inv_id, e.amount, e.tier, e.period,
          "" if e.period or (e.amount or 0) < 0 else "  ← не начислен"))
PYEOF

echo
echo "######## 3. САМОПРОВЕРКА (задача есть с 24.09)"
echo "⚠️ При сбое отправки selfcheck.settle снимает инцидент и текст проблемы не пишет — история только в логах Celery."
echo "== 3а. результаты selfcheck с непустыми проблемами (логи worker)"
docker compose logs -t --no-log-prefix worker </dev/null 2>&1 | grep -E "tasks\.selfcheck_(daily|hourly).*succeeded" \
  | grep -vE ": \{('[a-z_]+': None(, )?)*\}$" | cut -c1-400 | tail -30
echo "== 3б. сколько раз за сутки не ушло в Telegram (api + worker + beat)"
docker compose logs -t --no-log-prefix api worker beat </dev/null 2>&1 | grep "Telegram support notify failed" | cut -c1-10 | sort | uniq -c
echo "== 3в. текущее состояние (без запросов к модели)"
docker compose exec -T api python - <<'PYEOF'
from backend.config import get_settings
from backend.forecast import stats
from backend.selfcheck import budget_state, problem_fallback_share, read_feedback, problem_dislike_share, stats_line
spent, limit = budget_state()
summary = stats.summarize(stats.read_window())
print("ключ DeepSeek:", "есть" if get_settings().deepseek_api_key else "НЕТ")
print(stats_line(summary, spent, limit))
print("доля запасных:", problem_fallback_share(summary) or "в норме")
fb = read_feedback()
print("👎:", (problem_dislike_share(fb) or "в норме") if fb is not None else "не прочитано")
PYEOF
echo "== 3г. открытые инциденты в Redis (тем же клиентом, что у самопроверки)"
docker compose exec -T api python - <<'PYEOF'
from backend.beat_watchdog import _sync_redis
r = _sync_redis()
keys = sorted(r.scan_iter("astro:incident:*"))
print("открытых:", len(keys))
for k in keys[:20]:
    print("  ", k, "—", str(r.get(k))[:200])
PYEOF

echo
echo "######## 4. ДИСК"
df -h / | tail -1
df -i / | tail -1 | awk '{print "inode занято: " $5}'
du -sh backups 2>/dev/null
docker system df 2>&1
echo "== журнал astro-prune с $SINCE"
journalctl -u astro-prune.service --since "$SINCE" --no-pager -o short-iso 2>&1 | grep -iE "свободного|reclaimed|Docker image prune|⚠|ERROR|No journal|Permission" | tail -15

echo "== конец. Лог: /opt/astro/$LOG"
