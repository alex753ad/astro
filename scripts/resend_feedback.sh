#!/usr/bin/env bash
# resend_feedback.sh <id> — переотправить обращение из таблицы feedback в
# канал поддержки тем же кодом, что шлёт новые (_format_report + тариф и
# платежи для экрана payment). В БД ничего не меняет.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/resend_feedback.sh 13
#
# Повод (27.09.2026): обращение #13 из приложения записано в БД, но не дошло —
# в канале не было бота, от которого пишет сервер.

set -uo pipefail
ID="${1:?укажи номер обращения: bash scripts/resend_feedback.sh 13}"
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/resend_feedback-$ID-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

docker compose exec -T -e FEEDBACK_ID="$ID" api python - <<'PYEOF'
import asyncio, os
from backend.database import SessionLocal
from backend.models import Feedback, User
from backend.feedback.router import PAYMENT_SCREEN, _format_report, _payment_context
from backend.notifications.telegram import send_support_message

db = SessionLocal()
row = db.get(Feedback, int(os.environ["FEEDBACK_ID"]))
if row is None:
    raise SystemExit("обращения с таким номером нет")
user = db.get(User, row.user_id) if row.user_id else None
text = _format_report(row, user, row.context)
if row.screen == PAYMENT_SCREEN and user is not None:
    text += _payment_context(db, user)
text = "Повторная отправка #%s от %s UTC (первая не дошла)" % (row.id, f"{row.created_at:%d.%m.%Y %H:%M}") + chr(10) + chr(10) + text
print("обращение #%s, экран %s, аккаунт %s" % (row.id, row.screen, "есть" if user else "аноним"))
print("отправлено:", asyncio.run(send_support_message(text)))
PYEOF

echo "== конец. Лог: /opt/astro/$LOG"
