# ---------------------------------------------------------------------------
# Pakistan Inflation / Price Tracker — developer commands
# `make help` lists targets. CI mirrors: make lint, make type, make test.
# ---------------------------------------------------------------------------
ifeq ($(OS),Windows_NT)
PY      := .venv/Scripts/python
PIP     := $(PY) -m pip
SEP     := ;
else
PY      := .venv/bin/python
PIP     := $(PY) -m pip
SEP     := &&
endif

.DEFAULT_GOAL := help

.PHONY: help setup seed dev once test test-cov web-test lint format type qa docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[33m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv and install runtime + dev dependencies
	$(PIP) install -U pip $(SEP) $(PIP) install -r requirements.txt -r requirements-dev.txt

seed: ## Rebuild the approved baseline database
	$(PY) seed.py

dev: ## Run the web server locally (http://127.0.0.1:5010)
	$(PY) app.py

once: ## Run a single scheduled ingestion now
	$(PY) scheduler.py --once

test: ## Run the pytest suite
	$(PY) -m pytest

test-cov: ## Run pytest with coverage (fails under 80%)
	$(PY) -m pytest --cov --cov-fail-under=80

web-test: ## Boot the real server and check every route
	$(PY) test_web.py

pipeline-test: ## Dependency-free pipeline checks
	$(PY) test_pipeline.py

lint: ## Ruff lint
	$(PY) -m ruff check .

format: ## Format with black
	$(PY) -m black .

type: ## mypy type check
	$(PY) -m mypy

qa: ## Everything CI runs: lint, type, coverage, live web checks
	$(PY) -m ruff check . $(SEP) $(PY) -m mypy $(SEP) $(PY) -m pytest --cov --cov-fail-under=80 $(SEP) $(PY) test_web.py

docker-up: ## Start app + Postgres + Redis + Caddy (needs Docker)
	docker compose up --build -d

docker-down: ## Stop the compose stack
	docker compose down

clean: ## Remove caches and generated artifacts
	$(PY) -B -c "import shutil,sys; [shutil.rmtree(p, ignore_errors=True) for p in ['__pycache__','.pytest_cache','ingest/__pycache__','core/__pycache__','tests/__pycache__']]"