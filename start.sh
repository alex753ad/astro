#!/bin/bash
set -e

# Если сервис помечен как бот — запускаем бота и выходим (БД не трогаем).
if [ "$SERVICE_ROLE" = "bot" ]; then
    echo "Starting Telegram pilot bot..."
    pip install --no-cache-dir "aiogram>=3.4" httpx -q
    exec python -m bot.pilot_bot
fi

# Иначе — обычный бэкенд.
echo "Ensuring reportlab is installed..."
pip install --no-cache-dir "reportlab>=4.0.0" -q
echo "Ensuring pywebpush is installed..."
pip install --no-cache-dir "pywebpush>=1.14.0" -q
echo "Starting server..."
exec uvicorn backend.main:app --host 0.0.0.0 --port $PORT
