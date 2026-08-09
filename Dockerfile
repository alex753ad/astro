FROM python:3.12-slim AS base

WORKDIR /app

# System deps for pyswisseph build (removed after pip install to shrink surface)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential \
    fonts-liberation fonts-dejavu-core fonts-noto fonts-noto-extra && \
    rm -rf /var/lib/apt/lists/*

# Python deps.
#
# Ставим строго из requirements.lock — там точные версии со всей транзитивной
# цепочкой. Раньше здесь было `pip install -e "."` с диапазонами `>=` и, если
# он падал, молчаливый откат на `pip install fastapi uvicorn …` вообще без
# версий: каждая пересборка давала другой набор пакетов, упавший прод-образ
# невозможно было воспроизвести, а `|| ...` прятал причину сбоя.
#
# Лок обновляется командой `make lock` (см. Makefile) и коммитится в репозиторий.
# Сам пакет ставить не нужно: код лежит в /app, запуск идёт оттуда же
# (`uvicorn backend.main:app`), и `backend` импортируется как обычный каталог.
# Прежний `pip install -e "."` выполнялся, когда backend/ ещё не скопирован, —
# то есть работал ровно тот молчаливый fallback, который стоял следом.
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && \
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
