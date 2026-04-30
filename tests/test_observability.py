import asyncio
import json
import logging

from fastapi.testclient import TestClient
from httpx import AsyncClient, MockTransport, Request, Response
from prometheus_client import generate_latest

from app.api.routes import get_paper_search_client
from app.clients.europe_pmc import EuropePMCClient
from app.jobs.ingestion import process_ingestion_run_job
from app.main import app
from app.models import Topic
from app.observability.logging import JsonFormatter
from app.search.client import SearchError
from app.services import ingestion as ingestion_service


class FailingSearchClient:
    async def search_papers(self, query: str) -> list[int]:
        raise SearchError("Elasticsearch unavailable")

    async def close(self) -> None:
        return None


class NoopPaperSearchClient:
    async def index_papers(self, papers) -> None:
        return None

    async def close(self) -> None:
        return None


def test_metrics_endpoint_exposes_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "python_info" in response.text


def test_api_request_metrics_are_recorded(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    metrics_response = client.get("/metrics")

    assert 'biowatch_api_requests_total{method="GET",path="/health",status="200"}' in (
        metrics_response.text
    )
    assert "biowatch_api_request_latency_seconds_bucket" in metrics_response.text


def test_api_error_metrics_are_recorded(client: TestClient) -> None:
    app.dependency_overrides[get_paper_search_client] = lambda: FailingSearchClient()

    response = client.get("/papers/search?q=biomarker")
    assert response.status_code == 503

    metrics_response = client.get("/metrics")

    assert 'biowatch_api_requests_total{method="GET",path="/papers/search",status="503"}' in (
        metrics_response.text
    )
    assert 'biowatch_api_request_errors_total{method="GET",path="/papers/search"}' in (
        metrics_response.text
    )


def test_json_formatter_redacts_telegram_bot_tokens() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: POST https://api.telegram.org/bot123456:ABC_def-ghi/getUpdates",
        args=(),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert "bot123456:ABC_def-ghi" not in payload["message"]
    assert "bot<redacted>" in payload["message"]


def test_ingestion_success_metrics_are_recorded(async_session_factory, monkeypatch) -> None:
    _mock_ingestion_dependencies(
        async_session_factory,
        monkeypatch,
        {
            "resultList": {
                "result": [
                    {
                        "source": "MED",
                        "id": "12345",
                        "title": "Alzheimer plasma biomarker validation",
                    }
                ]
            }
        },
    )
    run_id = asyncio.run(_create_queued_run(async_session_factory))

    assert process_ingestion_run_job(run_id) == run_id

    metrics_text = generate_latest().decode()
    assert 'biowatch_ingestion_jobs_total{status="completed"}' in metrics_text
    assert "biowatch_ingestion_job_duration_seconds_bucket" in metrics_text
    assert "biowatch_ingestion_records_fetched_total" in metrics_text


def test_ingestion_failure_metrics_are_recorded(async_session_factory, monkeypatch) -> None:
    _mock_ingestion_dependencies(async_session_factory, monkeypatch, status_code=500)
    run_id = asyncio.run(_create_queued_run(async_session_factory))

    assert process_ingestion_run_job(run_id) == run_id

    metrics_text = generate_latest().decode()
    assert 'biowatch_ingestion_jobs_total{status="failed"}' in metrics_text


async def _create_queued_run(async_session_factory) -> int:
    async with async_session_factory() as session:
        topic = Topic(name="Alzheimer biomarkers", query="alzheimer biomarker plasma")
        session.add(topic)
        await session.commit()
        await session.refresh(topic)
        run = await ingestion_service.create_queued_run(session, topic)
        return run.id


def _mock_ingestion_dependencies(
    async_session_factory,
    monkeypatch,
    payload: dict | None = None,
    status_code: int = 200,
) -> None:
    import app.jobs.ingestion as worker_module

    def handler(request: Request) -> Response:
        return Response(status_code, json=payload or {}, request=request)

    def client_factory() -> EuropePMCClient:
        http_client = AsyncClient(transport=MockTransport(handler))
        return EuropePMCClient(
            http_client=http_client,
            max_attempts=1,
            retry_backoff_seconds=0,
        )

    monkeypatch.setattr(worker_module, "SessionLocal", async_session_factory)
    monkeypatch.setattr(ingestion_service, "EuropePMCClient", client_factory)
    monkeypatch.setattr(ingestion_service, "PaperSearchClient", lambda: NoopPaperSearchClient())
