#!/usr/bin/env bash
# check_telegram.sh — есть ли связь с api.telegram.org: с хоста и из worker.
#
# Запуск на сервере (только чтение; токен бота не используется и не печатается,
# сообщений не шлёт):
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_telegram.sh
#
# Вывод дублируется в /opt/astro/diag/check_telegram-<время>.log.
#
# Повод: 30.09.2026 утренняя самопроверка не доставлена — ConnectTimeout из
# worker (httpx, таймаут 15 с). Проверяем по-отдельности IPv4 и IPv6: сеть
# astro_net поднята с enable_ipv6, и если адрес Telegram по IPv6 не отвечает,
# клиент, пошедший в AAAA, висит до таймаута, а по IPv4 всё работает.
# Без токена: GET / у api.telegram.org отвечает редиректом — этого хватает,
# чтобы увидеть TCP+TLS и время ответа.
# ⚠️ `</dev/null` у exec — иначе exec съедает stdin (см. diag_support.sh).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_telegram-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
echo "сейчас $(date -u +%FT%TZ)"

echo "== 1. DNS на хосте"
getent ahostsv4 api.telegram.org | awk '{print $1}' | sort -u | sed 's/^/A    /'
getent ahostsv6 api.telegram.org | awk '{print $1}' | sort -u | sed 's/^/AAAA /'

echo "== 2. хост: curl, 5 попыток по IPv4 и по IPv6 (таймаут соединения 10 с)"
for fam in 4 6; do
  for i in 1 2 3 4 5; do
    printf 'IPv%s #%s: ' "$fam" "$i"
    curl -"$fam" -sS -o /dev/null --connect-timeout 10 --max-time 20 \
      -w 'код=%{http_code} соединение=%{time_connect}с TLS=%{time_appconnect}с всего=%{time_total}с\n' \
      https://api.telegram.org/ 2>&1 | tr -d '\r'
  done
done

echo "== 3. worker: тем же httpx, что шлёт сигналы, 5 попыток (таймаут 15 с)"
docker compose exec -T worker python - </dev/null <<'PYEOF'
import socket, time, httpx
for fam, name in ((socket.AF_INET, "A"), (socket.AF_INET6, "AAAA")):
    try:
        addrs = sorted({a[4][0] for a in socket.getaddrinfo("api.telegram.org", 443, fam)})
    except Exception as e:
        addrs = [repr(e)]
    print(f"DNS в контейнере {name}: {addrs}")
for i in range(1, 6):
    t = time.monotonic()
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get("https://api.telegram.org/")
        print(f"#{i}: код={r.status_code} за {time.monotonic() - t:.2f}с")
    except Exception as e:
        print(f"#{i}: {type(e).__name__}: {e!r} за {time.monotonic() - t:.2f}с")
    time.sleep(2)
PYEOF

echo "== 4. отправки в Telegram за 2 суток (worker, api): успехи и сбои"
for s in worker api; do
  echo "-- $s"
  docker compose logs "$s" --since 48h --timestamps </dev/null 2>&1 \
    | grep -E "Telegram: доставлено|Telegram support notify failed|не доставлено" | tail -15
done

echo "== лог сохранён: /opt/astro/$LOG"
