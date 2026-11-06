.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND  := backend
FRONTEND := frontend
VENV     := $(BACKEND)/.venv
PY       := $(VENV)/bin/python
CELERY   := cd $(BACKEND) && .venv/bin/celery -A app.workers.celery_app

.PHONY: help up down logs setup venv install env api worker beat web migrate migration \
        seed test test-db lint fmt typecheck check

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ---- Infrastructure -------------------------------------------------------
up: ## Start Postgres + Redis (docker compose) and wait until healthy
	docker compose up -d --wait

down: ## Stop containers (data volume is kept)
	docker compose down

logs: ## Tail container logs
	docker compose logs -f

# ---- Setup ----------------------------------------------------------------
setup: venv install env ## One-time setup: venv, backend + frontend deps, .env

venv:
	test -d $(VENV) || python3 -m venv $(VENV)

install: venv ## Install backend (editable, with dev extras) and frontend deps
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e "$(BACKEND)[dev]"
	cd $(FRONTEND) && npm install

env: ## Create backend/.env from .env.example if missing
	test -f $(BACKEND)/.env || cp .env.example $(BACKEND)/.env

# ---- Run (each in its own terminal) ----------------------------------------
api: ## Run FastAPI with auto-reload on :8000
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

worker: ## Run Celery worker
	$(CELERY) worker -l info

beat: ## Run Celery beat scheduler
	$(CELERY) beat -l info

web: ## Run Vite dev server on :5173
	cd $(FRONTEND) && npm run dev

# ---- Database ---------------------------------------------------------------
migrate: ## Apply migrations to the dev DB
	cd $(BACKEND) && .venv/bin/alembic upgrade head

migration: ## Autogenerate a migration: make migration m="message"
	cd $(BACKEND) && .venv/bin/alembic revision --autogenerate -m "$(m)"

seed: ## Seed demo data (make seed args=--reset to wipe first)
	cd $(BACKEND) && .venv/bin/python -m scripts.seed $(args)

# ---- Quality ----------------------------------------------------------------
test: ## Run backend tests
	cd $(BACKEND) && .venv/bin/pytest

lint: ## Lint backend (ruff) and frontend (oxlint)
	cd $(BACKEND) && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd $(FRONTEND) && npm run lint

fmt: ## Auto-format backend
	cd $(BACKEND) && .venv/bin/ruff check --fix . && .venv/bin/ruff format .

typecheck: ## mypy (backend) + tsc (frontend)
	cd $(BACKEND) && .venv/bin/mypy app scripts
	cd $(FRONTEND) && npm run typecheck

check: lint typecheck test ## Everything CI runs
	cd $(FRONTEND) && npm run build
