import asyncio
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import IngestionRun, Paper, TopicPaper
from app.search.client import SearchError
from app.web.routes import get_ingestion_queue, get_paper_search_client


class FakeJob:
    id = "dashboard-job-id"


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[object, tuple]] = []

    def enqueue(self, func, *args):
        self.enqueued.append((func, args))
        return FakeJob()


class FakeSearchClient:
    def __init__(self, paper_ids: list[int] | None = None, should_fail: bool = False) -> None:
        self.paper_ids = paper_ids or []
        self.should_fail = should_fail
        self.closed = False

    async def search_papers(self, query: str) -> list[int]:
        if self.should_fail:
            raise SearchError("Elasticsearch unavailable")
        return self.paper_ids

    async def close(self) -> None:
        self.closed = True


def test_dashboard_topics_page_renders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Tracked Topics" in response.text
    assert "Create Topic" in response.text


def test_dashboard_create_topic_form_creates_topic(client: TestClient) -> None:
    response = client.post(
        "/ui/topics",
        data={
            "name": "Checkpoint inhibitors",
            "query": "cancer immunotherapy checkpoint inhibitor",
            "enabled": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/topics/1?message=Topic%20created"

    detail_response = client.get(response.headers["location"])

    assert detail_response.status_code == 200
    assert "Checkpoint inhibitors" in detail_response.text
    assert "cancer immunotherapy checkpoint inhibitor" in detail_response.text


def test_dashboard_topic_detail_lists_papers(
    client: TestClient,
    async_session_factory,
) -> None:
    topic_id = _create_topic(client)
    asyncio.run(_create_topic_paper(async_session_factory, topic_id))

    response = client.get(f"/ui/topics/{topic_id}")

    assert response.status_code == 200
    assert "Matched Papers" in response.text
    assert "Checkpoint blockade biomarkers" in response.text
    assert "BioWatch Journal" in response.text


def test_dashboard_ingest_form_enqueues_run(client: TestClient) -> None:
    fake_queue = FakeQueue()
    app.dependency_overrides[get_ingestion_queue] = lambda: fake_queue
    topic_id = _create_topic(client)

    response = client.post(
        f"/ui/topics/{topic_id}/ingest",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 202
    assert "queued with job dashboard-job-id" in response.text
    assert len(fake_queue.enqueued) == 1

    runs_response = client.get("/ingestion-runs")

    assert runs_response.status_code == 200
    assert runs_response.json()[0]["status"] == "queued"
    assert runs_response.json()[0]["job_id"] == "dashboard-job-id"


def test_dashboard_ingestion_runs_page_renders(
    client: TestClient,
    async_session_factory,
) -> None:
    topic_id = _create_topic(client)
    asyncio.run(_create_ingestion_run(async_session_factory, topic_id))

    response = client.get("/ui/ingestion-runs")

    assert response.status_code == 200
    assert "Ingestion Runs" in response.text
    assert "completed" in response.text
    assert "run-job-id" in response.text


def test_dashboard_search_page_returns_postgres_papers(
    client: TestClient,
    async_session_factory,
) -> None:
    topic_id = _create_topic(client)
    paper_id = asyncio.run(_create_topic_paper(async_session_factory, topic_id))
    search_client = FakeSearchClient(paper_ids=[paper_id])
    app.dependency_overrides[get_paper_search_client] = lambda: search_client

    response = client.get("/ui/search?q=biomarker")

    assert response.status_code == 200
    assert "Results for" in response.text
    assert "Checkpoint blockade biomarkers" in response.text
    assert search_client.closed is True


def test_dashboard_search_failure_renders_unavailable_message(client: TestClient) -> None:
    search_client = FakeSearchClient(should_fail=True)
    app.dependency_overrides[get_paper_search_client] = lambda: search_client

    response = client.get("/ui/search?q=biomarker")

    assert response.status_code == 503
    assert "Paper search is temporarily unavailable." in response.text
    assert search_client.closed is True


def _create_topic(client: TestClient) -> int:
    response = client.post(
        "/topics",
        json={
            "name": "Checkpoint inhibitors",
            "query": "cancer immunotherapy checkpoint inhibitor",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_topic_paper(async_session_factory, topic_id: int) -> int:
    async with async_session_factory() as session:
        paper = Paper(
            source="europe_pmc",
            source_id="MED:123",
            title="Checkpoint blockade biomarkers",
            abstract="Biomarker study",
            journal="BioWatch Journal",
            publication_date=date(2024, 1, 1),
            doi="10.1000/dashboard",
            url="https://example.test/dashboard",
        )
        session.add(paper)
        await session.flush()
        session.add(TopicPaper(topic_id=topic_id, paper_id=paper.id))
        await session.commit()
        return paper.id


async def _create_ingestion_run(async_session_factory, topic_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            IngestionRun(
                topic_id=topic_id,
                status="completed",
                job_id="run-job-id",
                records_fetched=2,
            )
        )
        await session.commit()
