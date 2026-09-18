# VisiOnRoute developer entrypoints.
# `make bootstrap && make dev` must be enough for a new developer.

PG_DATA    := .localdata/pg
PG_PORT    ?= 5433
PG_BIN     := $(shell ls -d /opt/homebrew/opt/postgresql@17/bin 2>/dev/null || echo "")
DB_URL     ?= postgresql+asyncpg://visionroute:visionroute@localhost:$(PG_PORT)/visionroute

.PHONY: bootstrap dev api web worker scheduler db-up db-down db-init migrate \
        fmt fmt-check lint type test test-unit test-integration security check \
        seed-demo clean e2e

bootstrap:  ## Install all dependencies + git hooks
	poetry install
	cd apps/web && pnpm install
	poetry run pre-commit install || true
	@test -f .env || cp .env.example .env
	@echo "Bootstrap tamam. 'make dev' ile başlatın."

## ---- Local services -------------------------------------------------------
# Prefer docker compose when available; otherwise fall back to local Homebrew
# PostgreSQL 17 (+PostGIS) so development works without Docker.
db-up:
	@if command -v docker >/dev/null 2>&1; then \
		docker compose up -d postgres redis minio mailpit; \
	else \
		$(MAKE) db-init; \
		LC_ALL=C LANG=C $(PG_BIN)/pg_ctl -D $(PG_DATA) -o "-p $(PG_PORT)" -l .localdata/pg.log start || true; \
		sleep 1; \
		$(PG_BIN)/psql -p $(PG_PORT) -d postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='visionroute'" | grep -q 1 || \
			$(PG_BIN)/psql -p $(PG_PORT) -d postgres -c "CREATE ROLE visionroute LOGIN PASSWORD 'visionroute' CREATEDB"; \
		$(PG_BIN)/psql -p $(PG_PORT) -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='visionroute'" | grep -q 1 || \
			$(PG_BIN)/createdb -p $(PG_PORT) -O visionroute visionroute; \
		$(PG_BIN)/psql -p $(PG_PORT) -d visionroute -c "CREATE EXTENSION IF NOT EXISTS postgis" || \
			echo "UYARI: PostGIS uzantısı kurulamadı (brew install postgis)"; \
	fi

db-init:
	@test -d $(PG_DATA) || (mkdir -p .localdata && $(PG_BIN)/initdb -D $(PG_DATA) -E UTF8 --locale=C >/dev/null)

db-down:
	@if command -v docker >/dev/null 2>&1; then docker compose down; \
	else $(PG_BIN)/pg_ctl -D $(PG_DATA) stop || true; fi

migrate:
	poetry run alembic upgrade head

## ---- Run ------------------------------------------------------------------
dev: db-up migrate  ## Start the full local stack (api + web + worker)
	@echo "API:  http://localhost:8000  —  Web: http://localhost:3000"
	@$(MAKE) -j3 api web worker

api:
	poetry run uvicorn visionroute.api.main:create_app --factory --reload --port 8000

web:
	cd apps/web && pnpm dev

worker:
	poetry run visionroute worker run

scheduler:
	poetry run visionroute scheduler run

seed-demo:  ## Sentetik demo telemetrisi (data_origin=synthetic). Gerekli: API_KEY, SOURCE_KEY; isteğe bağlı: VEHICLE, BASE_URL
	@test -n "$(API_KEY)" -a -n "$(SOURCE_KEY)" || { \
		echo "Kullanım: make seed-demo API_KEY=vrk_... SOURCE_KEY=telematik-1 [VEHICLE=34ABC123] [BASE_URL=http://localhost:8000]"; \
		echo "API anahtarı ve veri kaynağı panelde Entegrasyonlar sayfasından oluşturulur."; exit 1; }
	poetry run visionroute simulate telemetry \
		--base-url "$(or $(BASE_URL),http://localhost:8000)" \
		--api-key "$(API_KEY)" --source-key "$(SOURCE_KEY)" \
		--vehicle-external-id "$(or $(VEHICLE),34ABC123)"

## ---- Quality gate ----------------------------------------------------------
fmt:
	poetry run ruff format src tests

fmt-check:
	poetry run ruff format --check src tests

lint:
	poetry run ruff check src tests
	poetry run lint-imports

type:
	poetry run mypy

test-unit:
	poetry run pytest tests/unit -q

test-integration:
	poetry run pytest tests/integration tests/security -q -m "integration or security"

test:
	poetry run pytest -q

e2e:  ## Uçtan uca testler (Playwright; PostgreSQL :5433 ve `pnpm exec playwright install chromium` gerekir)
	cd apps/web && pnpm e2e

security:
	poetry run bandit -c pyproject.toml -r src -q
	poetry run pip-audit --skip-editable || true

check: fmt-check lint type test security  ## Full quality gate
	@echo "Tüm kontroller geçti."

clean:
	rm -rf .localdata .ruff_cache .mypy_cache .pytest_cache htmlcov
