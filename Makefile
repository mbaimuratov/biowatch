PYTHON ?= python3.12
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install run worker summary-worker scheduler bot test lint format compose-up compose-down db-migrate db-revision k8s-dry-run helm-lint helm-template

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e ".[dev]"

run:
	$(BIN)/uvicorn app.main:app --reload

worker:
	$(BIN)/python -m app.jobs.worker

summary-worker:
	$(BIN)/python -m app.jobs.summary_worker

scheduler:
	$(BIN)/python -m app.jobs.scheduler

bot:
	$(BIN)/python -m app.bot.main

test:
	$(BIN)/pytest

lint:
	$(BIN)/ruff check .

format:
	$(BIN)/ruff format .

compose-up:
	docker compose up -d postgres redis elasticsearch api worker summary-worker scheduler bot prometheus grafana

compose-down:
	docker compose down

db-migrate:
	$(BIN)/alembic upgrade head

db-revision:
	$(BIN)/alembic revision --autogenerate -m "$(m)"

k8s-dry-run:
	kubectl apply --dry-run=client -f infra/k8s/

helm-lint:
	helm lint infra/helm/biowatch -f infra/helm/biowatch/values-dev.yaml

helm-template:
	helm template biowatch infra/helm/biowatch \
		--namespace biowatch \
		-f infra/helm/biowatch/values-dev.yaml
