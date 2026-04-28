# BioWatch

BioWatch is a biomedical literature watcher for tracking user-defined research topics,
ingesting new biomedical papers from Europe PMC and PubMed, indexing them, and showing
searchable alerts.

This repository contains the first backend MVP. It uses FastAPI, Jinja2, HTMX,
PostgreSQL, Redis, RQ, Elasticsearch, SQLAlchemy, Alembic, pytest, and ruff.
Europe PMC is the primary literature source; NCBI PubMed E-utilities is reserved
as an optional secondary source.
Manual topic ingestion enqueues an RQ job that fetches one page of the newest
matching Europe PMC records.

## Requirements

- Python 3.12
- Docker and Docker Compose for local PostgreSQL, Redis, and Elasticsearch

## Local Setup

Create a virtual environment and install the app with development dependencies:

```sh
make install
```

Copy the example environment file:

```sh
cp .env.example .env
```

Start the full local stack:

```sh
docker compose up --build
```

PostgreSQL is published on local port `55432`, Redis on local port `56379`,
and Elasticsearch on local port `59200` to avoid collisions with services
already running on your machine.

Run database migrations:

```sh
docker compose exec api alembic upgrade head
```

For non-Docker development, start dependencies and processes separately:

```sh
make compose-up
make db-migrate
make run
make worker
```

The health endpoint is available at:

```text
http://127.0.0.1:8000/health
```

The server-rendered dashboard is available at:

```text
http://127.0.0.1:8000/
```

## Development Commands

```sh
make test       # run pytest
make lint       # run ruff checks
make format     # format with ruff
make compose-up # start PostgreSQL, Redis, Elasticsearch, API, and worker
make compose-down
make db-migrate # apply Alembic migrations
make worker     # run a local RQ worker against local Redis
make k8s-dry-run
make helm-lint
make helm-template
```

Create a new Alembic migration:

```sh
make db-revision m="describe change"
```

## MVP API

```text
GET  /health
POST /topics
GET  /topics
GET  /topics/{topic_id}
POST /topics/{topic_id}/ingest
GET  /topics/{topic_id}/papers
GET  /papers/search?q=...
GET  /ingestion-runs
```

Create a topic:

```sh
curl -X POST http://127.0.0.1:8000/topics \
  -H "Content-Type: application/json" \
  -d '{"name":"Checkpoint inhibitors","query":"cancer immunotherapy checkpoint inhibitor"}'
```

Run Europe PMC ingestion for a topic:

```sh
curl -X POST http://127.0.0.1:8000/topics/1/ingest
```

The response should be `202 Accepted` with an ingestion run in `queued` status
and a `job_id`. Watch the worker process the job:

```sh
docker compose logs -f worker
```

Confirm the worker updated the run and stored papers:

```sh
curl http://127.0.0.1:8000/ingestion-runs
curl http://127.0.0.1:8000/topics/1/papers
```

Search indexed papers:

```sh
curl "http://127.0.0.1:8000/papers/search?q=checkpoint"
```

## Dashboard Flow

Open the dashboard after the API is running:

```text
http://127.0.0.1:8000/
```

From the dashboard you can:

- create a tracked topic
- open a topic detail page
- queue Europe PMC ingestion for that topic
- view recent papers
- view ingestion run status
- search indexed papers

For a full local demo, start the stack, apply migrations, open the dashboard,
create a topic, trigger ingestion, watch the worker, then refresh the papers,
ingestion runs, and search pages:

```sh
docker compose up --build
docker compose exec api alembic upgrade head
docker compose logs -f worker
```

Europe PMC client settings can be configured with:

```sh
BIOWATCH_ELASTICSEARCH_URL=http://localhost:59200
BIOWATCH_ELASTICSEARCH_INDEX=biowatch-papers
BIOWATCH_ELASTICSEARCH_TIMEOUT_SECONDS=10.0
BIOWATCH_EUROPE_PMC_TIMEOUT_SECONDS=10.0
BIOWATCH_EUROPE_PMC_MAX_ATTEMPTS=3
BIOWATCH_EUROPE_PMC_RETRY_BACKOFF_SECONDS=0.25
```

Run tests:

```sh
make test
```

## Continuous Integration

GitHub Actions CI runs on pull requests and pushes to `main`.

CI validates:

- `ruff check .`
- `pytest`
- Docker builds for `biowatch-api:ci` and `biowatch-worker:ci`
- `helm lint`
- `helm template` with development and production-like values

The current workflow does not deploy to Kubernetes or cloud infrastructure, and
it does not push Docker images. No repository secrets are required right now.
Future image publishing can use `GITHUB_TOKEN` package permissions or registry
credentials such as `REGISTRY_USERNAME` and `REGISTRY_PASSWORD`.

## Kubernetes and Helm

BioWatch includes raw Kubernetes manifests under `infra/k8s` and a Helm chart
under `infra/helm/biowatch`. The raw manifests are useful for understanding and
debugging the objects. Helm is the repeatable install and upgrade path.

Create a local kind cluster with HTTP ingress mapped to `localhost:8080`:

```sh
kind create cluster --name biowatch --config infra/kind/biowatch.yaml
```

Install the NGINX ingress controller for kind:

```sh
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=180s
```

Build and load the local BioWatch image:

```sh
docker build -t biowatch:dev .
kind load docker-image biowatch:dev --name biowatch
```

Validate and apply the raw manifests:

```sh
kubectl apply --dry-run=client -f infra/k8s/
kubectl apply -f infra/k8s/
kubectl -n biowatch wait --for=condition=complete job/biowatch-migrate --timeout=180s
kubectl -n biowatch rollout status deploy/biowatch-api
kubectl -n biowatch rollout status deploy/biowatch-worker
```

Reach the API through port-forward:

```sh
kubectl -n biowatch port-forward svc/biowatch-api 8000:8000
curl http://127.0.0.1:8000/health
```

Or use the Ingress:

```sh
curl -H "Host: biowatch.local" http://127.0.0.1:8080/health
```

Check worker ingestion:

```sh
curl -X POST http://127.0.0.1:8000/topics \
  -H "Content-Type: application/json" \
  -d '{"name":"Checkpoint inhibitors","query":"cancer immunotherapy checkpoint inhibitor"}'
curl -X POST http://127.0.0.1:8000/topics/1/ingest
kubectl -n biowatch logs deploy/biowatch-worker -f
curl http://127.0.0.1:8000/ingestion-runs
```

Install with Helm instead of raw manifests:

```sh
helm lint infra/helm/biowatch -f infra/helm/biowatch/values-dev.yaml
helm template biowatch infra/helm/biowatch \
  --namespace biowatch \
  -f infra/helm/biowatch/values-dev.yaml
helm install biowatch infra/helm/biowatch \
  --namespace biowatch \
  --create-namespace \
  -f infra/helm/biowatch/values-dev.yaml
kubectl -n biowatch rollout status deploy/biowatch-api
helm test biowatch --namespace biowatch
```

Upgrade image tags or config:

```sh
docker build -t biowatch:next .
kind load docker-image biowatch:next --name biowatch
helm upgrade biowatch infra/helm/biowatch \
  --namespace biowatch \
  -f infra/helm/biowatch/values-dev.yaml \
  --set image.tag=next
```

Rollback or uninstall:

```sh
helm rollback biowatch --namespace biowatch
helm uninstall biowatch --namespace biowatch
kubectl delete namespace biowatch
kind delete cluster --name biowatch
```
