from fastapi.testclient import TestClient

from app.api.routes import get_ingestion_queue
from app.main import app


class FakeJob:
    id = "test-job-id"


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[object, tuple]] = []

    def enqueue(self, func, *args):
        self.enqueued.append((func, args))
        return FakeJob()


def test_list_topic_papers_starts_empty(client: TestClient) -> None:
    topic_id = _create_topic(client)

    response = client.get(f"/topics/{topic_id}/papers")

    assert response.status_code == 200
    assert response.json() == []


def test_ingestion_endpoint_enqueues_run_without_fetching_papers(client: TestClient) -> None:
    fake_queue = FakeQueue()
    app.dependency_overrides[get_ingestion_queue] = lambda: fake_queue
    topic_id = _create_topic(client)

    ingest_response = client.post(f"/topics/{topic_id}/ingest")

    assert ingest_response.status_code == 202
    ingestion_run = ingest_response.json()
    assert ingestion_run["topic_id"] == topic_id
    assert ingestion_run["status"] == "queued"
    assert ingestion_run["job_id"] == "test-job-id"
    assert ingestion_run["records_fetched"] == 0
    assert ingestion_run["error_message"] is None
    assert ingestion_run["finished_at"] is None
    assert len(fake_queue.enqueued) == 1
    assert fake_queue.enqueued[0][1] == (ingestion_run["id"],)

    papers_response = client.get(f"/topics/{topic_id}/papers")

    assert papers_response.status_code == 200
    assert papers_response.json() == []

    runs_response = client.get("/ingestion-runs")

    assert runs_response.status_code == 200
    assert runs_response.json() == [ingestion_run]


def _create_topic(client: TestClient) -> int:
    response = client.post(
        "/topics",
        json={
            "name": "Alzheimer biomarkers",
            "query": "alzheimer biomarker plasma",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]
