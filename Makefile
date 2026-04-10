.PHONY: dev test lint migrate up down clean

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
