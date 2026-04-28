# AGENTS.md

## Project
BioWatch is a biomedical literature watcher. It lets users create tracked research topics, fetches papers from Europe PMC/PubMed, stores metadata, indexes papers for search, and exposes a small dashboard/API.

## Architecture
- Backend: FastAPI
- Database: PostgreSQL
- Queue/cache: Redis
- Worker: Python worker using RQ or Celery
- Search: OpenSearch or Elasticsearch, added after MVP
- Local dev: Docker Compose
- Deployment: Kubernetes + Helm
- Observability: Prometheus metrics + structured logs

## Rules
- Do not build everything at once.
- Make one focused change per task.
- Prefer simple code over clever abstractions.
- Add tests for API routes, workers, and parsing logic.
- Do not hardcode secrets.
- Do not add production dependencies without explaining why.
- Keep external API clients isolated under `app/clients/`.
- Keep business logic out of route handlers.
- Every task must update README or docs if commands change.

## Commands
- Use Python 3.12.
- Use `pytest` for tests.
- Use `ruff` for linting.
- Use Docker Compose for local dependencies.
- Before finishing a task, run tests or explain why they cannot run.

## Done criteria
A task is complete only when:
- code is implemented
- tests are added or updated
- commands are documented
- the app can still run locally