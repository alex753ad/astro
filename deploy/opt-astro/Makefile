-include .env
export

POSTGRES_USER ?= astro
POSTGRES_DB ?= astro_db

.PHONY: logs migrate shell-db restart-api backup

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

shell-db:
	docker compose exec postgres psql -U $(POSTGRES_USER) $(POSTGRES_DB)

restart-api:
	docker compose restart api

backup:
	mkdir -p backups
	docker compose exec -T postgres pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) > backups/astro_$$(date +%Y%m%d_%H%M%S).sql
