#!/bin/bash
set -e
echo "Ensuring reportlab is installed..."
pip install --no-cache-dir "reportlab>=4.0.0" -q
echo "Ensuring pywebpush is installed..."
pip install --no-cache-dir "pywebpush>=1.14.0" -q
echo "Starting server..."
exec uvicorn backend.main:app --host 0.0.0.0 --port $PORT
