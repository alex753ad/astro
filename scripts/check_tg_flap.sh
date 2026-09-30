#!/usr/bin/env bash
# check_tg_flap.sh — мигает ли связь с api.telegram.org: 5 минут, раз в 10 с,
# с хоста (curl) и из контейнера bot (python), по IPv6 и по IPv4 отдельно.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_tg_flap.sh
#
# Только чтение: токен не используется, сообщений не шлёт, ничего не меняет.
# Повод (30.09.2026): check_ipv6.sh — из контейнеров IPv6 до Telegram прошёл
# за 0,09 с, а curl -6 с хоста в том же прогоне упал по таймауту; утром шаг 7
# check_support_bot.sh из bot тоже упал по IPv6. Одиночный замер не отличает
# «IPv6 нестабилен» от «разовый сбой» — нужна серия.
# Хост и bot меряются одновременно (bot — в фоне), каждая попытка — TCP+TLS,
# таймаут соединения 5 с. Итог — доля успешных по каждому пути.
# ⚠️ `</dev/null` у docker compose — иначе съедает stdin (см. diag_support.sh).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
STAMP=$(date +%Y%m%d-%H%M%S)
LOG="diag/check_tg_flap-$STAMP.log"
BOTLOG="diag/check_tg_flap-$STAMP-bot.tmp"
exec > >(tee "$LOG") 2>&1
echo "сейчас $(date -u +%FT%TZ), 30 раундов по 10 с"
ROUNDS=30

docker compose exec -T -e ROUNDS="$ROUNDS" bot python - </dev/null >"$BOTLOG" 2>&1 <<'PYEOF' &
import os, socket, ssl, time
from datetime import datetime, timezone
ctx = ssl.create_default_context()
ips = {name: socket.getaddrinfo("api.telegram.org", 443, fam, socket.SOCK_STREAM)[0][4][0]
       for fam, name in ((socket.AF_INET6, "IPv6"), (socket.AF_INET, "IPv4"))}
start = time.monotonic()
for i in range(int(os.environ["ROUNDS"])):
    time.sleep(max(0, start + i * 10 - time.monotonic()))
    for name, ip in ips.items():
        t = time.monotonic()
        try:
            with socket.create_connection((ip, 443), timeout=5) as raw:
                with ctx.wrap_socket(raw, server_hostname="api.telegram.org"):
                    pass
            res = f"OK {time.monotonic() - t:.2f}с"
        except Exception as e:
            res = f"СБОЙ {type(e).__name__} {time.monotonic() - t:.2f}с"
        print(f"{datetime.now(timezone.utc):%H:%M:%S} bot  {name} {ip}: {res}", flush=True)
PYEOF
BOTPID=$!

HOSTRES=""
start=$(date +%s)
for i in $(seq 0 $((ROUNDS - 1))); do
  wait_s=$(( start + i * 10 - $(date +%s) )); [ "$wait_s" -gt 0 ] && sleep "$wait_s"
  for fam in 6 4; do
    full=$(curl -"$fam" -sS -o /dev/null --connect-timeout 5 --max-time 10 \
      -w '\n%{remote_ip} %{time_appconnect}' https://api.telegram.org/ 2>&1 | tr -d '\r')
    out=$(tail -1 <<<"$full")
    if [[ "$out" =~ ^[0-9a-f:.]+\ [0-9.]+$ ]] && [ "${out#* }" != "0.000000" ]; then
      res="OK ${out#* }с (${out% *})"; HOSTRES+="host IPv$fam OK"$'\n'
    else
      res="СБОЙ $(head -1 <<<"$full")"; HOSTRES+="host IPv$fam СБОЙ"$'\n'
    fi
    echo "$(date -u +%H:%M:%S) host IPv$fam: $res"
  done
done

wait "$BOTPID"
echo "== bot (в том же интервале)"
cat "$BOTLOG"

echo "== итог: успешных из $ROUNDS"
for p in "host IPv6" "host IPv4"; do
  echo "$p: $(grep -c "^$p OK" <<<"$HOSTRES")"
done
for fam in IPv6 IPv4; do
  echo "bot  $fam: $(grep -cE "bot  $fam .*: OK" "$BOTLOG")"
done
rm -f "$BOTLOG"
echo "== конец. Лог: /opt/astro/$LOG"
