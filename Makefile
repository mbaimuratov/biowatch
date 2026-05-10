PYTHON ?= python3.12
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install run worker summary-worker outbox-publisher indexer-consumer scheduler bot test lint format compose-up compose-down db-migrate db-revision k8s-dry-run helm-lint helm-template prod-bootstrap prod-seal-secret prod-argocd-login-help prod-status

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

outbox-publisher:
	$(BIN)/python -m app.jobs.outbox_publisher

indexer-consumer:
	$(BIN)/python -m app.jobs.indexer_consumer

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

prod-bootstrap:
	./scripts/bootstrap-prod.sh

prod-seal-secret:
	./scripts/seal-prod-secret.sh

prod-argocd-login-help:
	@echo 'export KUBECONFIG="$${KUBECONFIG:-$$HOME/.kube/biowatch-utm-k3s.yaml}"'
	@echo 'export ARGOCD_PASSWORD="$$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)"'
	@echo 'argocd login argocd.local --username admin --password "$$ARGOCD_PASSWORD" --insecure --grpc-web'

prod-status:
	@echo 'kubectl get pods -A'
	@echo 'kubectl get pods -n biowatch-prod'
	@echo 'kubectl get applications.argoproj.io -n argocd'
	@echo 'kubectl get appprojects.argoproj.io -n argocd'
	@echo 'argocd app list --grpc-web'
	@echo 'argocd app get biowatch-prod --grpc-web'
