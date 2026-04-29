# BioWatch

BioWatch is a biomedical literature watcher for tracking user-defined research topics,
ingesting new biomedical papers from Europe PMC and PubMed, indexing them, and showing
searchable alerts.

BioWatch is moving toward a Telegram-first biomedical reading bot. Every
morning the bot will send a configurable set of papers from subscribed topics;
the web dashboard remains useful for admin and debugging workflows.

The backend uses FastAPI, Jinja2, HTMX, PostgreSQL, Redis, RQ, Elasticsearch,
SQLAlchemy, Alembic, pytest, and ruff. Europe PMC is the primary literature
source; NCBI PubMed E-utilities is reserved as an optional secondary source.
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

Metrics and local observability are available at:

```text
API metrics:    http://127.0.0.1:8000/metrics
Worker metrics: http://127.0.0.1:9100/metrics
Prometheus:     http://127.0.0.1:9090
Grafana:        http://127.0.0.1:3000
```

## Development Commands

```sh
make test       # run pytest
make lint       # run ruff checks
make format     # format with ruff
make compose-up # start PostgreSQL, Redis, Elasticsearch, API, worker, scheduler, bot, Prometheus, and Grafana
make compose-down
make db-migrate # apply Alembic migrations
make worker     # run a local RQ worker with metrics against local Redis
make scheduler  # enqueue due Telegram morning deliveries
make bot        # run the Telegram bot with long polling
make k8s-dry-run
make helm-lint
make helm-template
```

Create a new Alembic migration:

```sh
make db-revision m="describe change"
```

## Telegram Bot MVP

BioWatch includes a Telegram bot service that uses long polling. The bot stores
Telegram subscribers and per-subscriber topic ownership so users can configure
reading preferences without web authentication. Existing global topics are still
supported with no subscriber attached, which keeps the API and dashboard useful
as admin/debug surfaces.

Set the bot token in your local environment. Do not commit real Telegram tokens;
rotate any token that was pasted into chat, logs, or source control.

```sh
BIOWATCH_TELEGRAM_BOT_TOKEN=your-telegram-token
```

Run the bot locally:

```sh
make bot
```

Or run it with Docker Compose:

```sh
docker compose up --build bot
```

Supported bot commands:

```text
/start
/help
/settings
/topics
/addtopic Spatial transcriptomics | spatial transcriptomics tumor microenvironment cancer
/removetopic 3
/pause
/resume
/count 5
/time 08:30
/timezone Europe/Rome
/digest
```

The bot can manage topics/settings and send an immediate subscriber-scoped
digest. `/start` explains the workflow, `/help` includes practical topic
examples, and the bot registers Telegram command suggestions plus a small reply
keyboard for common actions.

### Telegram Morning Delivery

BioWatch can also send a persistent morning brief for each enabled Telegram
subscriber. The scheduler checks subscriber timezone and `morning_send_time`,
queues one delivery per subscriber/scheduled morning, and the worker processes
the delivery. Delivery jobs ingest due subscriber topics, generate/reuse the
daily digest, select up to `article_count` papers, send Telegram messages, and
record delivery status/items.

Run the local morning-delivery stack:

```sh
export BIOWATCH_TELEGRAM_BOT_TOKEN=your-telegram-token
docker compose up --build postgres redis elasticsearch api worker scheduler bot
docker compose exec api alembic upgrade head
```

For non-Docker local development, run the API, worker, scheduler, and bot in
separate terminals:

```sh
make run
make worker
make scheduler
make bot
```

Inspect and retry deliveries through the admin/debug API:

```sh
curl http://127.0.0.1:8000/telegram/deliveries
curl -X POST http://127.0.0.1:8000/telegram/deliveries/1/retry
```

Automatic delivery is idempotent for a subscriber and scheduled morning. Failed
deliveries are not retried automatically; use the retry endpoint after
inspecting the failure. Webhooks, Kubernetes CronJobs, delivery AI summaries,
and advanced notification controls are intentionally not included yet.

## MVP API

```text
GET  /health
POST /topics
GET  /topics
GET  /topics/{topic_id}
DELETE /topics/{topic_id}
POST /topics/{topic_id}/ingest
POST /subscriptions/ingest-due
POST /digests/today/generate
GET  /digests/today
GET  /digests/{digest_date}
GET  /telegram/deliveries
POST /telegram/deliveries/{delivery_id}/retry
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

Delete a topic:

```sh
curl -X DELETE http://127.0.0.1:8000/topics/1
```

Enqueue subscription-style ingestion for all enabled topics that are due:

```sh
curl -X POST http://127.0.0.1:8000/subscriptions/ingest-due
```

Manual ingestion still exists for one-off topic refreshes. The subscription
endpoint checks enabled topics, enqueues only topics due by their configured
`ingestion_frequency`, updates `last_ingested_at` when a run is queued, and
leaves `last_successful_ingestion_at` for the worker to update after a
successful ingestion run. This is the app-level foundation for a future
Kubernetes CronJob; no scheduler dependency or CronJob is required yet.

Search indexed papers:

```sh
curl "http://127.0.0.1:8000/papers/search?q=checkpoint"
```

## Daily Digest

BioWatch can generate a persistent daily digest from recently matched papers.
The digest is stored in Postgres so later scheduled jobs, alerting, and AI
summaries can build on a durable application artifact.

Generate today's digest:

```sh
curl -X POST http://127.0.0.1:8000/digests/today/generate
```

Fetch today's digest:

```sh
curl http://127.0.0.1:8000/digests/today
```

Open the digest dashboard:

```text
http://127.0.0.1:8000/digest/today
```

Daily Digest v1 intentionally does not include AI summaries, advanced ranking,
or save/dismiss actions yet. Those come in later phases.

## Dashboard Flow

Open the dashboard after the API is running:

```text
http://127.0.0.1:8000/
```

From the dashboard you can:

- create a tracked topic
- open a topic detail page
- queue Europe PMC ingestion for that topic
- generate and view today's digest
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

## Observability

BioWatch exposes Prometheus metrics and JSON structured logs for the API and
worker. The API serves `/metrics`; the worker serves metrics on port `9100`.
Docker Compose also starts Prometheus and Grafana with a preloaded BioWatch
dashboard.

Start the local observability stack:

```sh
docker compose up --build
```

Inspect metrics directly:

```sh
curl http://127.0.0.1:8000/metrics
curl http://127.0.0.1:9100/metrics
```

Open Prometheus and Grafana:

```text
http://127.0.0.1:9090
http://127.0.0.1:3000
```

Grafana local credentials are `admin` / `admin`.

Useful Prometheus queries:

```promql
sum(rate(biowatch_api_requests_total[5m])) by (path)
sum(rate(biowatch_api_request_errors_total[5m]))
histogram_quantile(0.95, sum(rate(biowatch_api_request_latency_seconds_bucket[5m])) by (le, path))
increase(biowatch_ingestion_jobs_total[1h])
increase(biowatch_ingestion_records_fetched_total[1h])
increase(biowatch_telegram_delivery_attempts_total[1h])
increase(biowatch_telegram_delivery_items_sent_total[1h])
```

For Kubernetes, raw manifests add Prometheus scrape annotations to API and
worker Services and include a scrape config ConfigMap at
`infra/k8s/60-prometheus-scrape-config.yaml`. The Helm chart renders the same
scrape annotations by default and exposes the worker metrics Service.

Port-forward metrics in Kubernetes:

```sh
kubectl -n biowatch port-forward svc/biowatch-api 8000:8000
kubectl -n biowatch port-forward svc/biowatch-worker 9100:9100
```

Europe PMC client settings can be configured with:

```sh
BIOWATCH_ELASTICSEARCH_URL=http://localhost:59200
BIOWATCH_ELASTICSEARCH_INDEX=biowatch-papers
BIOWATCH_ELASTICSEARCH_TIMEOUT_SECONDS=10.0
BIOWATCH_EUROPE_PMC_TIMEOUT_SECONDS=10.0
BIOWATCH_EUROPE_PMC_MAX_ATTEMPTS=3
BIOWATCH_EUROPE_PMC_RETRY_BACKOFF_SECONDS=0.25
BIOWATCH_WORKER_METRICS_PORT=9100
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
under `infra/helm/biowatch`. From now on, Helm on kind is the default local
runtime path. The raw manifests remain useful for understanding and debugging
the objects.

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
docker build -t biowatch:local .
kind load docker-image biowatch:local --name biowatch
```

Create the runtime Secret from local shell values. Do not commit real Telegram
tokens to git; rotate any token pasted into chat, logs, or source control.

```sh
export BIOWATCH_TELEGRAM_BOT_TOKEN='set-token-locally'
kubectl create namespace biowatch --dry-run=client -o yaml | kubectl apply -f -
kubectl -n biowatch create secret generic biowatch-secret \
  --from-literal=POSTGRES_PASSWORD=biowatch \
  --from-literal=BIOWATCH_DATABASE_URL='postgresql+asyncpg://biowatch:biowatch@biowatch-postgres:5432/biowatch' \
  --from-literal=BIOWATCH_TELEGRAM_BOT_TOKEN="$BIOWATCH_TELEGRAM_BOT_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Install with Helm:

```sh
helm lint infra/helm/biowatch -f infra/helm/biowatch/values-dev.yaml
helm template biowatch infra/helm/biowatch \
  --namespace biowatch \
  -f infra/helm/biowatch/values-dev.yaml \
  --set image.repository=biowatch \
  --set image.tag=local \
  --set image.pullPolicy=Never
helm upgrade --install biowatch infra/helm/biowatch \
  --namespace biowatch \
  -f infra/helm/biowatch/values-dev.yaml \
  --set image.repository=biowatch \
  --set image.tag=local \
  --set image.pullPolicy=Never
kubectl -n biowatch rollout status deploy/biowatch-api
kubectl -n biowatch rollout status deploy/biowatch-worker
kubectl -n biowatch rollout status deploy/biowatch-bot
kubectl -n biowatch rollout status deploy/biowatch-scheduler
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

Check Telegram runtime pods and Secret injection:

```sh
kubectl -n biowatch logs deploy/biowatch-bot -f
kubectl -n biowatch logs deploy/biowatch-worker -f
kubectl -n biowatch logs deploy/biowatch-scheduler -f
kubectl -n biowatch exec deploy/biowatch-worker -- sh -lc 'test -n "$BIOWATCH_TELEGRAM_BOT_TOKEN" && echo token-present'
helm test biowatch --namespace biowatch
```

Validate and apply raw manifests only when you want the reference/debug path:

```sh
kubectl apply --dry-run=client -f infra/k8s/
kubectl apply -f infra/k8s/
kubectl -n biowatch wait --for=condition=complete job/biowatch-migrate --timeout=180s
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
