FROM python:3.12-slim AS base

WORKDIR /app

# System deps for pyswisseph build
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir "bcrypt>=3.2.0,<4.0.0" && \
    pip install --no-cache-dir -e ".[dev]" 2>/dev/null || \
    pip install --no-cache-dir \
    fastapi "uvicorn[standard]" pyswisseph sqlalchemy alembic \
    psycopg2-binary httpx pydantic pydantic-settings slowapi \
    "python-jose[cryptography]" "passlib[bcrypt]" "bcrypt>=3.2.0,<4.0.0" \
    timezonefinder pytz geopy \
    pytest pytest-asyncio

# Copy application
ARG CACHE_BUST=1
COPY backend/ /app/backend/
COPY data/ephe/ /app/data/ephe/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
