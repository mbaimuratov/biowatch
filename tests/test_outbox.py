import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.events.papers import (
    PAPER_INGESTED_EVENT_TYPE,
    PAPER_INGESTED_EVENT_VERSION,
    PAPER_INGESTED_TOPIC,
    build_paper_ingested_payload,
)
from app.models import EventOutbox, Paper, Topic
from app.services.ingestion import create_queued_run, process_ingestion_run
from app.services.outbox import publish_pending_events


class StubEuropePMCClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def search(self, query: str, page_size: int = 25) -> dict:
        return self.payload


class NoopSearchClient:
    async def index_papers(self, papers) -> None:
        return None


class RecordingProducer:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.published: list[tuple[str, dict, str | None]] = []

    async def publish(self, topic: str, payload: dict, key: str | None = None) -> None:
        if self.should_fail:
            raise RuntimeError("Kafka unavailable")
        self.published.append((topic, payload, key))


def test_paper_ingested_event_schema() -> None:
    paper = Paper(
        id=42,
        source="europe_pmc",
        source_id="MED:123",
        title="Spatial transcriptomics in cancer",
        abstract="A useful abstract.",
        journal="Nature Medicine",
        publication_date=date(2026, 5, 1),
        doi="10.1000/example",
        url="https://europepmc.org/article/MED/123",
        created_at=datetime(2026, 5, 2, 8, 0, tzinfo=UTC),
    )

    payload = build_paper_ingested_payload(paper)

    assert payload == {
        "event_type": PAPER_INGESTED_EVENT_TYPE,
        "event_version": PAPER_INGESTED_EVENT_VERSION,
        "paper": {
            "id": 42,
            "source": "europe_pmc",
            "source_id": "MED:123",
            "title": "Spatial transcriptomics in cancer",
            "abstract": "A useful abstract.",
            "journal": "Nature Medicine",
            "publication_date": "2026-05-01",
            "doi": "10.1000/example",
            "url": "https://europepmc.org/article/MED/123",
            "created_at": "2026-05-02T08:00:00+00:00",
        },
    }


def test_ingestion_creates_outbox_events_for_new_papers_only(async_session_factory) -> None:
    asyncio.run(_run_ingestion_twice_and_assert_outbox(async_session_factory))


async def _run_ingestion_twice_and_assert_outbox(async_session_factory) -> None:
    async with async_session_factory() as session:
        topic = Topic(name="Spatial transcriptomics", query="spatial transcriptomics cancer")
        session.add(topic)
        await session.commit()
        await session.refresh(topic)
        run = await create_queued_run(session, topic)

        client = StubEuropePMCClient(
            {
                "resultList": {
                    "result": [
                        {
                            "source": "MED",
                            "id": "123",
                            "title": "Spatial transcriptomics in cancer",
                            "abstractText": "A useful abstract.",
                        },
                        {
                            "source": "PMC",
                            "id": "PMC456",
                            "title": "Tumor microenvironment atlas",
                        },
                    ]
                }
            }
        )
        await process_ingestion_run(
            session,
            run.id,
            europe_pmc_client=client,
            paper_search_client=NoopSearchClient(),
        )

        events = list(await session.scalars(select(EventOutbox).order_by(EventOutbox.id)))
        assert len(events) == 2
        assert {event.event_type for event in events} == {PAPER_INGESTED_EVENT_TYPE}
        assert {event.topic for event in events} == {PAPER_INGESTED_TOPIC}
        assert {event.status for event in events} == {"pending"}
        assert {event.attempts for event in events} == {0}

        second_run = await create_queued_run(session, topic)
        await process_ingestion_run(
            session,
            second_run.id,
            europe_pmc_client=client,
            paper_search_client=NoopSearchClient(),
        )

        events_after_duplicate_ingestion = list(
            await session.scalars(select(EventOutbox).order_by(EventOutbox.id))
        )
        assert len(events_after_duplicate_ingestion) == 2


def test_outbox_publisher_marks_events_published(async_session_factory) -> None:
    asyncio.run(_run_publisher_success(async_session_factory))


async def _run_publisher_success(async_session_factory) -> None:
    async with async_session_factory() as session:
        event = EventOutbox(
            event_type=PAPER_INGESTED_EVENT_TYPE,
            topic=PAPER_INGESTED_TOPIC,
            key="europe_pmc:MED:123",
            payload={"event_type": PAPER_INGESTED_EVENT_TYPE, "paper": {"id": 1}},
        )
        session.add(event)
        await session.commit()

        producer = RecordingProducer()
        result = await publish_pending_events(session, producer)

        await session.refresh(event)
        assert result.published == 1
        assert result.failed == 0
        assert producer.published == [
            (
                PAPER_INGESTED_TOPIC,
                {"event_type": PAPER_INGESTED_EVENT_TYPE, "paper": {"id": 1}},
                "europe_pmc:MED:123",
            )
        ]
        assert event.status == "published"
        assert event.published_at is not None
        assert event.last_error is None
        assert event.attempts == 0


def test_outbox_publisher_records_failure_for_retry(async_session_factory) -> None:
    asyncio.run(_run_publisher_failure(async_session_factory))


async def _run_publisher_failure(async_session_factory) -> None:
    async with async_session_factory() as session:
        event = EventOutbox(
            event_type=PAPER_INGESTED_EVENT_TYPE,
            topic=PAPER_INGESTED_TOPIC,
            key="europe_pmc:MED:123",
            payload={"event_type": PAPER_INGESTED_EVENT_TYPE, "paper": {"id": 1}},
        )
        session.add(event)
        await session.commit()

        producer = RecordingProducer(should_fail=True)
        result = await publish_pending_events(session, producer)

        await session.refresh(event)
        assert result.published == 0
        assert result.failed == 1
        assert producer.published == []
        assert event.status == "pending"
        assert event.published_at is None
        assert event.attempts == 1
        assert event.last_error == "Kafka unavailable"
