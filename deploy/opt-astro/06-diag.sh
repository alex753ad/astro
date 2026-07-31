#!/usr/bin/env bash
# Диагностический снимок состояния прод-стека в один текстовый отчёт.
# Запускать от deploy, из /opt/astro:  ./06-diag.sh
#
# Секреты не маскируются постфактум — они сюда просто не попадают:
# скрипт нигде не печатает значения переменных окружения (.env), только
# их имена, и не вызывает `docker compose config` (он резолвит ${...}
# в реальные значения).
#
# set -e намеренно НЕ используется для секций сбора данных — задача
# диагностики - собрать максимум, даже если один сервис не запущен или
# сертификата ещё нет. Ошибки внутри секций перехватываются run_or_na
# и попадают в отчёт как есть, вместо того чтобы прервать весь скрипт.
set -uo pipefail

BACKUP_DIR="backups"
mkdir -p "$BACKUP_DIR"
OUT_FILE="${BACKUP_DIR}/diag_$(date +%Y%m%d_%H%M%S).txt"

# Дублируем весь дальнейший вывод и на экран, и в файл.
exec > >(tee "$OUT_FILE") 2>&1

section() { echo; echo "=== $* ==="; }

run_or_na() {
  if ! "$@"; then
    echo "  [команда завершилась с ошибкой: $*]"
  fi
}

echo "Диагностика Astro — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Отчёт: $OUT_FILE"

if [[ ! -f docker-compose.yml ]]; then
  echo "ERROR: docker-compose.yml не найден в текущем каталоге. Запускайте из /opt/astro." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
section "Контейнеры (docker compose ps -a)"
run_or_na docker compose ps -a

# ---------------------------------------------------------------------------
services="$(docker compose config --services 2>/dev/null || echo "postgres redis api bot")"
for svc in $services; do
  section "Логи: $svc (последние 100 строк)"
  run_or_na docker compose logs --tail=100 --no-log-prefix "$svc"
done

# ---------------------------------------------------------------------------
section "Диск"
run_or_na df -h /

section "Память"
run_or_na free -h

section "Swap"
run_or_na swapon --show

# ---------------------------------------------------------------------------
section "nginx -t"
run_or_na sudo nginx -t

# ---------------------------------------------------------------------------
section "Срок действия TLS-сертификата"
CERT_DIR="/etc/letsencrypt/live"
if [[ -d "$CERT_DIR" ]] && compgen -G "${CERT_DIR}/*/fullchain.pem" > /dev/null 2>&1; then
  for f in "${CERT_DIR}"/*/fullchain.pem; do
    domain="$(basename "$(dirname "$f")")"
    echo "  $domain:"
    run_or_na bash -c "openssl x509 -enddate -noout -in '$f' | sed 's/^notAfter=/    Истекает: /'"
  done
else
  echo "  Сертификаты не найдены в $CERT_DIR — HTTPS ещё не настроен (ожидаемо до этапа certbot)."
fi

# ---------------------------------------------------------------------------
section "curl http://127.0.0.1:8000/health"
run_or_na curl -sS -m 5 -w '\nHTTP %{http_code}\n' http://127.0.0.1:8000/health

section "curl http://127.0.0.1:8000/health/db"
run_or_na curl -sS -m 5 -w '\nHTTP %{http_code}\n' http://127.0.0.1:8000/health/db

# ---------------------------------------------------------------------------
section "Переменные в .env (только имена, значения не выводятся)"
if [[ -f .env ]]; then
  grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env | cut -d= -f1 | sort
else
  echo "  .env не найден"
fi

echo
echo "Готово. Отчёт сохранён в $OUT_FILE"
