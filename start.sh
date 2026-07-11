#!/bin/bash
set -e

echo "Ensuring reportlab is installed..."
pip install --no-cache-dir "reportlab>=4.0.0" -q

echo "Ensuring pywebpush is installed..."
pip install --no-cache-dir "pywebpush>=1.14.0" -q

echo "Checking alembic state..."

# Проверяем существует ли таблица alembic_version
ALEMBIC_EXISTS=$(python -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT to_regclass('alembic_version')\")
result = cur.fetchone()[0]
conn.close()
print('yes' if result else 'no')
")

if [ "$ALEMBIC_EXISTS" = "no" ]; then
    echo "No alembic_version found. Checking if tables exist..."

    TABLES_EXIST=$(python -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT to_regclass('users')\")
result = cur.fetchone()[0]
conn.close()
print('yes' if result else 'no')
")

    if [ "$TABLES_EXIST" = "yes" ]; then
        echo "Tables already exist, stamping head..."
        alembic stamp head
    else
        echo "Fresh database, running migrations..."
    fi
fi

echo "Running alembic upgrade head..."
alembic upgrade head

echo "Starting server..."
exec uvicorn backend.main:app --host 0.0.0.0 --port $PORT
