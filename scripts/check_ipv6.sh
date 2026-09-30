#!/usr/bin/env bash
# check_ipv6.sh — есть ли IPv6 до api.telegram.org у хоста и внутри
# контейнеров bot, api, worker, и каким семейством шли шаги 4–5
# check_support_bot.sh (urllib из api).
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/check_ipv6.sh
#
# Только чтение: сообщений не шлёт, токен не использует, ничего не меняет.
# Повод (30.09.2026): шаги 4–5 check_support_bot.sh из api прошли, а шаг 7 из
# bot упал по таймауту и по IPv6, и по IPv4 (~15,7 с). Версия — у хоста IPv6
# есть, у контейнеров нет; тогда то же касается сигналов из api и worker.
# В образе (python:3.12-slim) нет ни curl, ни ip — «curl -6» внутри контейнера
# сделан на python (TCP+TLS до каждого адреса), адреса и маршрут — из /proc.
# ⚠️ `</dev/null` у docker compose — иначе съедает stdin (см. diag_support.sh).

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/check_ipv6-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
echo "сейчас $(date -u +%FT%TZ)"

echo "== 1. хост: глобальные IPv6-адреса и маршрут по умолчанию"
ip -6 addr show scope global
ip -6 route show default
echo "forwarding: all=$(sysctl -n net.ipv6.conf.all.forwarding) default=$(sysctl -n net.ipv6.conf.default.forwarding)"

echo "== 2. хост: curl до api.telegram.org по IPv6 и IPv4"
for fam in 6 4; do
  printf 'IPv%s: ' "$fam"
  curl -"$fam" -sS -o /dev/null --connect-timeout 8 --max-time 15 \
    -w 'код=%{http_code} адрес=%{remote_ip} соединение=%{time_connect}с\n' \
    https://api.telegram.org/ 2>&1 | tr -d '\r'
done

echo "== 3. Docker: версия, daemon.json, сеть astro_net"
docker version --format 'сервер {{.Server.Version}}'
echo "-- /etc/docker/daemon.json:"; cat /etc/docker/daemon.json 2>&1
NET=$(docker network ls --format '{{.Name}}' | grep -E '(^|_)astro_net$' | head -1)
echo "-- сеть: $NET"
docker network inspect "$NET" --format 'EnableIPv6={{.EnableIPv6}} IPAM={{json .IPAM.Config}}'
docker network inspect "$NET" --format '{{range .Containers}}{{.Name}} v4={{.IPv4Address}} v6={{.IPv6Address}}{{"\n"}}{{end}}'
echo "-- NAT для IPv6 (ip6tables nat POSTROUTING):"
ip6tables -t nat -S POSTROUTING 2>&1
echo "-- NAT для IPv6 (nft, строки с fd00 / masquerade):"
nft list ruleset 2>/dev/null | grep -nE 'fd00|masquerade' | head -20

for s in bot api worker; do
  echo "== 4. контейнер $s"
  docker compose exec -T "$s" python - </dev/null <<'PYEOF'
import http.client, socket, ssl, time

def addrs6():
    out = []
    for line in open("/proc/net/if_inet6"):
        h, _, _, scope, _, dev = line.split()
        a = socket.inet_ntop(socket.AF_INET6, bytes.fromhex(h))
        out.append(f"{dev} {a} scope={scope}")
    return out

print("IPv6-адреса:", addrs6() or "нет")
default = [l.split() for l in open("/proc/net/ipv6_route") if l.startswith("0" * 32 + " 00 ")]
print("маршрут IPv6 по умолчанию:", [f"via {socket.inet_ntop(socket.AF_INET6, bytes.fromhex(r[4]))} dev {r[9]}" for r in default] or "нет")

ctx = ssl.create_default_context()
for fam, name in ((socket.AF_INET6, "IPv6"), (socket.AF_INET, "IPv4")):
    try:
        ips = sorted({a[4][0] for a in socket.getaddrinfo("api.telegram.org", 443, fam, socket.SOCK_STREAM)})
    except Exception as e:
        print(f"{name}: DNS {type(e).__name__}: {e}")
        continue
    for ip in ips:
        t = time.monotonic()
        try:
            with socket.create_connection((ip, 443), timeout=8) as raw:
                with ctx.wrap_socket(raw, server_hostname="api.telegram.org"):
                    pass
            print(f"{name} {ip}: TCP+TLS OK за {time.monotonic() - t:.2f}с")
        except Exception as e:
            print(f"{name} {ip}: {type(e).__name__}: {e} за {time.monotonic() - t:.2f}с")

# Как шаги 4–5: urllib/http.client без выбора семейства — какой адрес взял.
t = time.monotonic()
try:
    c = http.client.HTTPSConnection("api.telegram.org", timeout=30)
    c.connect()
    print(f"как шаги 4–5 (http.client): соединился с {c.sock.getpeername()[0]} за {time.monotonic() - t:.2f}с")
    c.close()
except Exception as e:
    print(f"как шаги 4–5 (http.client): {type(e).__name__}: {e} за {time.monotonic() - t:.2f}с")
PYEOF
done

echo "== конец. Лог: /opt/astro/$LOG"
