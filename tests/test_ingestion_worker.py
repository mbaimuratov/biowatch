import asyncio
import logging

from httpx import AsyncClient, MockTransport, Request, Response
from sqlalchemy import func, select

from app.clients.europe_pmc import EuropePMCClient
from app.jobs.ingestion import process_ingestion_run_job
from app.models import IngestionRun, Paper, Topic
from app.services import ingestion as ingestion_service


class RecordingSearchClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.indexed_batches: list[list[int]] = []
        self.closed = False

    async def index_papers(self, papers) -> None:
        self.indexed_batches.append([paper.id for paper in papers])
        if self.should_fail:
            raise RuntimeError("Elasticsearch unavailable")

    async def close(self) -> None:
        self.closed = True


def test_worker_processes_ingestion_run_and_deduplicates_papers(
    async_session_factory,
    monkeypatch,
) -> None:
    requests: list[Request] = []
    search_client = RecordingSearchClient()
    _mock_worker_dependencies(
        async_session_factory,
        monkeypatch,
        requests,
        search_client,
        {
            "resultList": {
                "result": [
                    {
                        "source": "MED",
                        "id": "12345",
                        "title": "Alzheimer plasma biomarker validation",
                        "abstractText": "A useful abstract.",
                        "journalTitle": "Journal of Biomarkers",
                        "firstPublicationDate": "2024-03-05",
                        "doi": "10.1000/example.1",
                    },
                    {
                        "source": "PMC",
                        "id": "PMC98765",
                        "title": "Biomarker methods update",
                        "abstractText": "Another useful abstract.",
                        "journalTitle": "Methods in Medicine",
                        "pubYear": "2023",
                        "doi": "10.1000/example.2",
                    },
                ]
            }
        },
    )
    run_id = asyncio.run(_create_queued_run(async_session_factory))

    assert process_ingestion_run_job(run_id) == run_id
    assert process_ingestion_run_job(run_id) == run_id

    run, topic, papers, paper_count = asyncio.run(
        _load_run_and_papers(async_session_factory, run_id)
    )

    assert run.status == "completed"
    assert run.records_fetched == 2
    assert run.error_message is None
    assert run.finished_at is not None
    assert topic.last_successful_ingestion_at == run.finished_at
    assert len(requests) == 2
    assert {request.url.params["pageSize"] for request in requests} == {"7"}
    assert paper_count == 2
    assert {paper.source for paper in papers} == {"europe_pmc"}
    assert {paper.source_id for paper in papers} == {"MED:12345", "PMC:PMC98765"}
    assert len(search_client.indexed_batches) == 2
    assert search_client.indexed_batches[0] == search_client.indexed_batches[1]
    assert sorted(search_client.indexed_batches[0]) == [paper.id for paper in papers]
    assert search_client.closed is True


def test_worker_marks_run_failed_when_europe_pmc_fails(
    async_session_factory,
    monkeypatch,
) -> None:
    requests: list[Request] = []
    search_client = RecordingSearchClient()
    _mock_worker_dependencies(
        async_session_factory,
        monkeypatch,
        requests,
        search_client,
        status_code=500,
    )
    run_id = asyncio.run(_create_queued_run(async_session_factory))

    assert process_ingestion_run_job(run_id) == run_id

    run, topic, papers, paper_count = asyncio.run(
        _load_run_and_papers(async_session_factory, run_id)
    )

    assert run.status == "failed"
    assert run.records_fetched == 0
    assert run.finished_at is not None
    assert "Europe PMC" in run.error_message
    assert topic.last_successful_ingestion_at is None
    assert len(requests) == 1
    assert papers == []
    assert paper_count == 0
    assert search_client.indexed_batches == []


def test_worker_logs_indexing_failure_without_failing_run(
    async_session_factory,
    monkeypatch,
    caplog,
) -> None:
    requests: list[Request] = []
    search_client = RecordingSearchClient(should_fail=True)
    _mock_worker_dependencies(
        async_session_factory,
        monkeypatch,
        requests,
        search_client,
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

    with caplog.at_level(logging.ERROR):
        assert process_ingestion_run_job(run_id) == run_id

    run, topic, papers, paper_count = asyncio.run(
        _load_run_and_papers(async_session_factory, run_id)
    )

    assert run.status == "completed"
    assert run.records_fetched == 1
    assert run.error_message is None
    assert topic.last_successful_ingestion_at == run.finished_at
    assert paper_count == 1
    assert len(papers) == 1
    assert search_client.indexed_batches == [[papers[0].id]]
    assert "Failed to index papers for ingestion run" in caplog.text


async def _create_queued_run(async_session_factory) -> int:
    async with async_session_factory() as session:
        topic = Topic(
            name="Alzheimer biomarkers",
            query="alzheimer biomarker plasma",
            max_papers_per_run=7,
        )
        session.add(topic)
        await session.commit()
        await session.refresh(topic)
        run = await ingestion_service.create_queued_run(session, topic)
        return run.id


async def _load_run_and_papers(async_session_factory, run_id: int):
    async with async_session_factory() as session:
        run = await session.get(IngestionRun, run_id)
        topic = await session.get(Topic, run.topic_id)
        papers = list(await session.scalars(select(Paper).order_by(Paper.id)))
        paper_count = await session.scalar(select(func.count(Paper.id)))
        return run, topic, papers, paper_count


def _mock_worker_dependencies(
    async_session_factory,
    monkeypatch,
    requests: list[Request],
    search_client: RecordingSearchClient,
    payload: dict | None = None,
    status_code: int = 200,
) -> None:
    import app.jobs.ingestion as worker_module

    def handler(request: Request) -> Response:
        requests.append(request)
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
    monkeypatch.setattr(ingestion_service, "PaperSearchClient", lambda: search_client)
