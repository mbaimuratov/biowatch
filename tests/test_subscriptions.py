import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import get_ingestion_queue
from app.main import app
from app.models import IngestionRun, Topic
from app.services import subscriptions as subscription_service


class FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[object, tuple]] = []

    def enqueue(self, func, *args):
        self.enqueued.append((func, args))
        return FakeJob(f"test-job-{len(self.enqueued)}")


def test_due_topic_selection_rules(async_session_factory) -> None:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    async def scenario() -> list[str]:
        async with async_session_factory() as session:
            topics = [
                Topic(name="Disabled", query="disabled", enabled=False),
                Topic(name="Never ingested", query="never", enabled=True),
                Topic(
                    name="Recent daily",
                    query="recent",
                    enabled=True,
                    ingestion_frequency="daily",
                    last_ingested_at=now - timedelta(hours=2),
                ),
                Topic(
                    name="Old daily",
                    query="old daily",
                    enabled=True,
                    ingestion_frequency="daily",
                    last_ingested_at=now - timedelta(hours=25),
                ),
                Topic(
                    name="Old weekly",
                    query="old weekly",
                    enabled=True,
                    ingestion_frequency="weekly",
                    last_ingested_at=now - timedelta(days=8),
                ),
            ]
            session.add_all(topics)
            await session.commit()

            due_topics = await subscription_service.list_due_topics(session, now=now)
            return [topic.name for topic in due_topics]

    assert asyncio.run(scenario()) == ["Never ingested", "Old daily", "Old weekly"]


def test_ingest_due_endpoint_enqueues_only_due_topics(
    client: TestClient,
    async_session_factory,
) -> None:
    fake_queue = FakeQueue()
    app.dependency_overrides[get_ingestion_queue] = lambda: fake_queue
    now = datetime.now(UTC)
    topic_ids = asyncio.run(_create_subscription_topics(async_session_factory, now))

    response = client.post("/subscriptions/ingest-due")

    assert response.status_code == 202
    payload = response.json()
    assert payload["topics_checked"] == 3
    assert payload["topics_enqueued"] == 2
    assert payload["job_ids"] == ["test-job-1", "test-job-2"]
    assert len(payload["ingestion_run_ids"]) == 2
    assert len(fake_queue.enqueued) == 2
    assert [args for _, args in fake_queue.enqueued] == [
        (payload["ingestion_run_ids"][0],),
        (payload["ingestion_run_ids"][1],),
    ]

    topics, runs = asyncio.run(_load_subscription_state(async_session_factory))
    due_topic_names = {"Never ingested", "Old weekly"}
    for topic in topics:
        if topic.name in due_topic_names:
            assert topic.last_ingested_at is not None
            assert topic.last_successful_ingestion_at is None
        if topic.id == topic_ids["recent_daily"]:
            assert topic.last_ingested_at is not None
            assert topic.last_successful_ingestion_at is None
        if topic.id == topic_ids["disabled"]:
            assert topic.last_ingested_at is None

    assert [(run.topic_id, run.status, run.job_id) for run in runs] == [
        (topic_ids["never_ingested"], "queued", "test-job-1"),
        (topic_ids["old_weekly"], "queued", "test-job-2"),
    ]


async def _create_subscription_topics(async_session_factory, now: datetime) -> dict[str, int]:
    async with async_session_factory() as session:
        topics = {
            "never_ingested": Topic(name="Never ingested", query="never", enabled=True),
            "recent_daily": Topic(
                name="Recent daily",
                query="recent",
                enabled=True,
                ingestion_frequency="daily",
                last_ingested_at=now - timedelta(hours=1),
            ),
            "disabled": Topic(name="Disabled", query="disabled", enabled=False),
            "old_weekly": Topic(
                name="Old weekly",
                query="weekly",
                enabled=True,
                ingestion_frequency="weekly",
                last_ingested_at=now - timedelta(days=8),
            ),
        }
        session.add_all(topics.values())
        await session.commit()
        return {name: topic.id for name, topic in topics.items()}


async def _load_subscription_state(async_session_factory) -> tuple[list[Topic], list[IngestionRun]]:
    async with async_session_factory() as session:
        topics = list(await session.scalars(select(Topic).order_by(Topic.id)))
        runs = list(await session.scalars(select(IngestionRun).order_by(IngestionRun.id)))
        return topics, runs
