#!/bin/bash
set -e

# Если сервис помечен как бот — запускаем бота и выходим (БД не трогаем).
if [ "$SERVICE_ROLE" = "bot" ]; then
    echo "Starting Telegram pilot bot..."
    exec python -m bot.pilot_bot
fi

# Иначе — обычный бэкенд.
echo "Starting server..."
exec uvicorn backend.main:app --host 0.0.0.0 --port $PORT
