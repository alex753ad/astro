#!/bin/bash
set -e

# Один образ, роль выбирается переменной окружения SERVICE_ROLE — тот же
# паттерн, что уже был для бота, просто с двумя новыми значениями.
#
# worker/beat были нужны раньше: backend/tasks.py и backend/celery_app.py
# написаны и оттестированы полностью, но ни один процесс их не запускал.
# Каждый .delay()/.apply_async() клал задачу в Redis, и её никто никогда не
# забирал — рассылка клиентам из CRM отвечала {"queued": true} и не
# отправляла ничего, POST /transits/async всегда истекал по таймауту.
if [ "$SERVICE_ROLE" = "bot" ]; then
    echo "Starting Telegram pilot bot..."
    exec python -m bot.pilot_bot
fi

if [ "$SERVICE_ROLE" = "worker" ]; then
    echo "Starting Celery worker..."
    # -Ofair — задача не блокирует остальных на воркере, пока ждёт ответ AI
    # или Robokassa; при prefetch по умолчанию (=1, уже задан в celery_app.py)
    # это не критично, но защищает от голодания при будущих --concurrency>1.
    exec celery -A backend.celery_app worker --loglevel=info -O fair
fi

if [ "$SERVICE_ROLE" = "beat" ]; then
    echo "Starting Celery beat..."
    exec celery -A backend.celery_app beat --loglevel=info
fi

# Иначе — обычный бэкенд.
echo "Starting server..."
exec uvicorn backend.main:app --host 0.0.0.0 --port $PORT
