import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import IngestionRun, Paper, TopicPaper


def test_create_get_and_list_topics(client: TestClient) -> None:
    create_response = client.post(
        "/topics",
        json={
            "name": "Checkpoint inhibitors",
            "query": "cancer immunotherapy checkpoint inhibitor",
        },
    )

    assert create_response.status_code == 201
    created_topic = create_response.json()
    assert created_topic["id"] == 1
    assert created_topic["subscriber_id"] is None
    assert created_topic["name"] == "Checkpoint inhibitors"
    assert created_topic["query"] == "cancer immunotherapy checkpoint inhibitor"
    assert created_topic["enabled"] is True
    assert created_topic["ingestion_frequency"] == "daily"
    assert created_topic["last_ingested_at"] is None
    assert created_topic["last_successful_ingestion_at"] is None
    assert created_topic["priority"] == 0
    assert created_topic["max_papers_per_run"] == 25
    assert created_topic["created_at"]

    get_response = client.get("/topics/1")

    assert get_response.status_code == 200
    assert get_response.json() == created_topic

    list_response = client.get("/topics")

    assert list_response.status_code == 200
    assert list_response.json() == [created_topic]


def test_create_topic_rejects_blank_text(client: TestClient) -> None:
    response = client.post(
        "/topics",
        json={
            "name": " ",
            "query": " ",
        },
    )

    assert response.status_code == 422


def test_create_topic_accepts_scheduling_settings(client: TestClient) -> None:
    response = client.post(
        "/topics",
        json={
            "name": "Checkpoint inhibitors",
            "query": "cancer immunotherapy checkpoint inhibitor",
            "ingestion_frequency": "weekly",
            "priority": 5,
            "max_papers_per_run": 10,
        },
    )

    assert response.status_code == 201
    topic = response.json()
    assert topic["ingestion_frequency"] == "weekly"
    assert topic["priority"] == 5
    assert topic["max_papers_per_run"] == 10


def test_create_topic_rejects_old_max_results_field(client: TestClient) -> None:
    response = client.post(
        "/topics",
        json={
            "name": "Checkpoint inhibitors",
            "query": "cancer immunotherapy checkpoint inhibitor",
            "max_results_per_run": 10,
        },
    )

    assert response.status_code == 422


def test_create_topic_rejects_unknown_ingestion_frequency(client: TestClient) -> None:
    response = client.post(
        "/topics",
        json={
            "name": "Checkpoint inhibitors",
            "query": "cancer immunotherapy checkpoint inhibitor",
            "ingestion_frequency": "hourly",
        },
    )

    assert response.status_code == 422


def test_delete_topic_removes_topic_links_and_runs(
    client: TestClient,
    async_session_factory,
) -> None:
    topic_id = _create_topic(client)
    paper_id = asyncio.run(_create_topic_paper_and_run(async_session_factory, topic_id))

    response = client.delete(f"/topics/{topic_id}")

    assert response.status_code == 204
    assert response.content == b""

    get_response = client.get(f"/topics/{topic_id}")
    assert get_response.status_code == 404

    list_response = client.get("/topics")
    assert list_response.status_code == 200
    assert list_response.json() == []

    remaining = asyncio.run(_get_remaining_topic_data(async_session_factory, paper_id))
    assert remaining == {
        "matches": 0,
        "runs": 0,
        "paper_exists": True,
    }


def test_delete_topic_returns_404_when_missing(client: TestClient) -> None:
    response = client.delete("/topics/404")

    assert response.status_code == 404
    assert response.json()["detail"] == "Topic not found"


def test_delete_topic_rejects_active_ingestion_run(
    client: TestClient,
    async_session_factory,
) -> None:
    topic_id = _create_topic(client)
    asyncio.run(_create_ingestion_run(async_session_factory, topic_id, "running"))

    response = client.delete(f"/topics/{topic_id}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Topic has active ingestion runs"
    assert client.get(f"/topics/{topic_id}").status_code == 200


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


async def _create_topic_paper_and_run(async_session_factory, topic_id: int) -> int:
    async with async_session_factory() as session:
        paper = Paper(
            source="europe_pmc",
            source_id="MED:456",
            title="Checkpoint blockade deletion test",
            abstract="Biomarker study",
            journal="BioWatch Journal",
            doi="10.1000/delete",
            url="https://example.test/delete",
        )
        session.add(paper)
        await session.flush()
        session.add(TopicPaper(topic_id=topic_id, paper_id=paper.id))
        session.add(
            IngestionRun(
                topic_id=topic_id,
                status="completed",
                job_id="completed-job-id",
                records_fetched=1,
            )
        )
        await session.commit()
        return paper.id


async def _create_ingestion_run(async_session_factory, topic_id: int, status: str) -> None:
    async with async_session_factory() as session:
        session.add(
            IngestionRun(
                topic_id=topic_id,
                status=status,
                job_id=f"{status}-job-id",
                records_fetched=0,
            )
        )
        await session.commit()


async def _get_remaining_topic_data(async_session_factory, paper_id: int) -> dict[str, object]:
    async with async_session_factory() as session:
        matches = await session.scalars(select(TopicPaper))
        runs = await session.scalars(select(IngestionRun))
        paper = await session.get(Paper, paper_id)
        return {
            "matches": len(list(matches)),
            "runs": len(list(runs)),
            "paper_exists": paper is not None,
        }
