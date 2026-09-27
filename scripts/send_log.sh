#!/usr/bin/env bash
# send_log.sh [шаблон] — отправить последний лог диагностики файлом в канал
# поддержки, чтобы не копировать вывод из терминала.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/send_log.sh audit_since_0209
#
# Без аргумента — самый свежий лог в /opt/astro/diag. Файл уходит от
# серверного бота в @aristeatimesupport; оттуда владелец пересылает его
# @claudekrassbot, и Claude Code читает его сам (getUpdates того бота).
# Логи диагностики токенов не содержат — скрипты их не печатают.

set -uo pipefail
cd /opt/astro || exit 1
F=$(ls -t diag/"${1:-}"*.log 2>/dev/null | head -1)
[ -n "$F" ] || { echo "логов по шаблону «${1:-}» в /opt/astro/diag нет"; exit 1; }
docker compose cp "$F" api:/tmp/send_log.txt </dev/null >/dev/null || exit 1
docker compose exec -T -e LOG_NAME="$(basename "$F")" api python - <<'PYEOF'
import json, os, urllib.request, uuid
t = os.environ["TELEGRAM_BOT_TOKEN"]
chat = os.environ["TELEGRAM_SUPPORT_CHAT_ID"]
name = os.environ["LOG_NAME"]
data = open("/tmp/send_log.txt", "rb").read()
b = uuid.uuid4().hex
crlf = chr(13) + chr(10)
body = b""
for k, v in (("chat_id", chat), ("caption", "Лог диагностики: " + name)):
    body += ("--" + b + crlf + 'Content-Disposition: form-data; name="' + k + '"' + crlf + crlf + v + crlf).encode()
body += ("--" + b + crlf + 'Content-Disposition: form-data; name="document"; filename="' + name + '"' + crlf
         + "Content-Type: text/plain" + crlf + crlf).encode() + data + (crlf + "--" + b + "--" + crlf).encode()
req = urllib.request.Request("https://api.telegram.org/bot" + t + "/sendDocument", data=body, method="POST")
req.add_header("Content-Type", "multipart/form-data; boundary=" + b)
try:
    print("отправлено:", json.load(urllib.request.urlopen(req, timeout=60)).get("ok"), name)
except urllib.error.HTTPError as e:
    print("ОШИБКА:", json.load(e).get("description"))
os.remove("/tmp/send_log.txt")
PYEOF
