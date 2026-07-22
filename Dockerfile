FROM python:3.12-slim AS base

WORKDIR /app

# System deps for pyswisseph build (removed after pip install to shrink surface)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential \
    fonts-liberation fonts-dejavu-core fonts-noto fonts-noto-extra && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir "bcrypt>=3.2.0,<4.0.0" && \
    ( pip install --no-cache-dir -e "." 2>/dev/null || \
      pip install --no-cache-dir \
      fastapi "uvicorn[standard]" pyswisseph sqlalchemy alembic \
      psycopg2-binary httpx pydantic pydantic-settings slowapi \
      "python-jose[cryptography]" "passlib[bcrypt]" "bcrypt>=3.2.0,<4.0.0" \
      timezonefinder pytz geopy redis ) && \
    pip install --no-cache-dir "reportlab>=4.0.0" "python-multipart>=0.0.9" && \
    apt-get purge -y --auto-remove gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy application
ARG CACHE_BUST=1
COPY backend/ /app/backend/
COPY bot/ /app/bot/
COPY data/ephe/ /app/data/ephe/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Run as non-root
RUN useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["/app/start.sh"]
