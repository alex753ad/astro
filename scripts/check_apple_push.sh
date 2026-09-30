#!/usr/bin/env bash
# check_apple_push.sh — дойдёт ли web push до iPhone с нашего сервера
# (только чтение; ничего не меняет, пушей не шлёт, ключи не печатает).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_apple_push.sh
#
# Вывод дублируется в /opt/astro/diag/check_apple_push-<время>.log.
#
# Повод (30.09.2026): сайт на iPhone как приложение с экрана «Домой», пуши —
# web push (iOS 16.4+). Подписка Safari даёт адрес на web.push.apple.com, и
# слать туда будет pywebpush из контейнера api. У Telegram 30.09 IPv4 оказался
# закрыт при открытом IPv6 (check_telegram.sh) — поэтому оба семейства и
# отдельно изнутри контейнера: у хоста и у контейнера сеть может отличаться.
# Пустой POST без ключа — это не пуш: Apple отвечает 4xx (BadJwtToken и т. п.),
# и любой код, кроме 000, значит «сервер Apple достижим».
# Скрипты в контейнер идут через heredoc — stdin скрипта им не нужен.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_apple_push-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
echo "сейчас $(date -u +%FT%TZ)"

HOST=web.push.apple.com

echo "== 1. С хоста: адреса и пустой POST (код 4xx = достижим, 000 = нет связи)"
echo "IPv4: $(getent ahostsv4 $HOST | awk '{print $1}' | sort -u | tr '\n' ' ')"
echo "IPv6: $(getent ahostsv6 $HOST | grep -v '::ffff:' | awk '{print $1}' | sort -u | tr '\n' ' ')"
for fam in 4 6; do
  for try in 1 2 3; do
    out=$(curl -"$fam" -s -o /dev/null -X POST --connect-timeout 6 --max-time 12 \
      -w '%{http_code} %{time_connect}' "https://$HOST/" 2>/dev/null)
    set -- $out
    printf 'IPv%s попытка %s: код %s, соединение %sс\n' "$fam" "$try" "${1:-000}" "${2:--}"
  done
done

echo "== 2. Из контейнера api: TCP+TLS к $HOST по каждому семейству"
docker compose exec -T api python - <<'PY'
import socket, ssl, time
host = "web.push.apple.com"
for fam, name in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
    try:
        addrs = sorted({a[4][0] for a in socket.getaddrinfo(host, 443, fam, socket.SOCK_STREAM)})
    except Exception as e:
        print(f"{name}: нет адреса ({e.__class__.__name__})"); continue
    for ip in addrs[:2]:
        t = time.monotonic()
        try:
            with socket.create_connection((ip, 443), timeout=6) as s:
                with ssl.create_default_context().wrap_socket(s, server_hostname=host) as tls:
                    print(f"{name} {ip}: ок, TLS {tls.version()}, {time.monotonic() - t:.2f}с")
        except Exception as e:
            print(f"{name} {ip}: НЕТ СВЯЗИ ({e.__class__.__name__}: {e})")
PY

echo "== 3. Ключи VAPID в контейнере api (значения приватного ключа не печатаются)"
docker compose exec -T api python - <<'PY'
import os
pub, priv, sub = (os.getenv(k, "") for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"))
print("VAPID_PUBLIC_KEY :", f"задан ({len(pub)} симв.)" if pub else "НЕ ЗАДАН")
print("VAPID_PRIVATE_KEY:", f"задан ({len(priv)} симв.)" if priv else "НЕ ЗАДАН")
# Apple отвергает JWT, если sub не mailto: или https: (BadJwtToken).
print("VAPID_SUBJECT    :", sub or "(пусто — в коде дефолт mailto:admin@aristeatime.ru)",
      "" if (not sub or sub.startswith(("mailto:", "https:"))) else "⚠️ не mailto:/https: — Apple откажет")
try:
    from importlib.metadata import version
    print("pywebpush        :", version("pywebpush"))
except Exception as e:
    print("pywebpush        : не найден", e)
PY

echo "== 4. Веб-подписки в БД по сервису (адресов и людей не печатаем)"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -' <<'SQL'
select split_part(split_part(endpoint, '://', 2), '/', 1) as сервис,
       count(*) as подписок, count(distinct user_id) as людей
from push_subscriptions group by 1 order by 2 desc;
SQL

echo "== лог сохранён: /opt/astro/$LOG"
