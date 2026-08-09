.PHONY: dev test lint migrate up down clean lock audit

# Start development server (without Docker)
dev:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Docker Compose up
up:
	docker compose up -d

# Docker Compose down
down:
	docker compose down

# Run tests
test:
	python -m pytest backend/tests/ -v

# Lint
lint:
	ruff check backend/
	mypy backend/ --ignore-missing-imports

# Пересобрать лок-файлы зависимостей. Цель — python 3.12/linux, как в
# контейнере, а не интерпретатор разработчика. Запускать после любой правки
# зависимостей в pyproject.toml и коммитить оба файла.
lock:
	uv pip compile pyproject.toml --python-version 3.12 --python-platform linux \
		--generate-hashes --no-header -o requirements.lock
	uv pip compile pyproject.toml --extra dev --python-version 3.12 --python-platform linux \
		--generate-hashes --no-header -o requirements-dev.lock

# Проверка зависимостей на известные уязвимости — то же, что гоняет CI.
audit:
	pip-audit -r requirements.lock --strict
	cd frontend && npm audit --audit-level=high

# Alembic migration
migrate:
	alembic upgrade head

# Create new migration
migration:
	alembic revision --autogenerate -m "$(msg)"

# Clean up
clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
