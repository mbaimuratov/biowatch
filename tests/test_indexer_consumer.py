import asyncio
from datetime import date

from app.events.papers import build_paper_ingested_payload
from app.kafka.consumer import KafkaMessage
from app.models import Paper
from app.search.client import PaperSearchClient
from app.services.indexer import process_paper_ingested_message


class RecordingCommitter:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class RecordingSearchClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.paper_ids: list[int] = []

    async def index_paper(self, paper: Paper) -> None:
        if self.should_fail:
            raise RuntimeError("Elasticsearch unavailable")
        self.paper_ids.append(paper.id)


class FakeIndices:
    def __init__(self) -> None:
        self.created = False
        self.refreshed: list[str] = []

    async def exists(self, index: str) -> bool:
        return self.created

    async def create(self, index: str, mappings: dict) -> None:
        self.created = True

    async def refresh(self, index: str) -> None:
        self.refreshed.append(index)


class FakeElasticsearch:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.index_calls: list[dict] = []

    async def index(self, index: str, id: str, document: dict) -> None:
        self.index_calls.append({"index": index, "id": id, "document": document})


def test_valid_event_loads_paper_indexes_and_commits(async_session_factory) -> None:
    asyncio.run(_run_valid_event(async_session_factory))


async def _run_valid_event(async_session_factory) -> None:
    async with async_session_factory() as session:
        paper = Paper(
            source="europe_pmc",
            source_id="MED:123",
            title="Spatial transcriptomics in cancer",
            publication_date=date(2026, 5, 1),
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)

        search_client = RecordingSearchClient()
        committer = RecordingCommitter()
        message = KafkaMessage(
            topic="biowatch.paper.ingested.v1",
            partition=0,
            offset=12,
            value=build_paper_ingested_payload(paper),
        )

        processed = await process_paper_ingested_message(
            session,
            search_client,
            committer,
            message,
        )

        assert processed is True
        assert search_client.paper_ids == [paper.id]
        assert committer.commits == 1


def test_invalid_event_is_logged_and_not_committed(async_session_factory) -> None:
    asyncio.run(_run_invalid_event(async_session_factory))


async def _run_invalid_event(async_session_factory) -> None:
    async with async_session_factory() as session:
        search_client = RecordingSearchClient()
        committer = RecordingCommitter()
        message = KafkaMessage(
            topic="biowatch.paper.ingested.v1",
            partition=0,
            offset=13,
            value={"event_type": "wrong"},
        )

        processed = await process_paper_ingested_message(
            session,
            search_client,
            committer,
            message,
        )

        assert processed is False
        assert search_client.paper_ids == []
        assert committer.commits == 0


def test_missing_paper_does_not_commit(async_session_factory) -> None:
    asyncio.run(_run_missing_paper(async_session_factory))


async def _run_missing_paper(async_session_factory) -> None:
    async with async_session_factory() as session:
        search_client = RecordingSearchClient()
        committer = RecordingCommitter()
        message = KafkaMessage(
            topic="biowatch.paper.ingested.v1",
            partition=0,
            offset=14,
            value={
                "event_id": "paper.ingested.v1:999",
                "event_type": "paper.ingested",
                "event_version": 1,
                "paper": {"id": 999},
            },
        )

        processed = await process_paper_ingested_message(
            session,
            search_client,
            committer,
            message,
        )

        assert processed is False
        assert search_client.paper_ids == []
        assert committer.commits == 0


def test_indexing_failure_does_not_commit_offset(async_session_factory) -> None:
    asyncio.run(_run_indexing_failure(async_session_factory))


async def _run_indexing_failure(async_session_factory) -> None:
    async with async_session_factory() as session:
        paper = Paper(
            source="europe_pmc",
            source_id="MED:123",
            title="Spatial transcriptomics in cancer",
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)

        search_client = RecordingSearchClient(should_fail=True)
        committer = RecordingCommitter()
        message = KafkaMessage(
            topic="biowatch.paper.ingested.v1",
            partition=0,
            offset=15,
            value=build_paper_ingested_payload(paper),
        )

        try:
            await process_paper_ingested_message(session, search_client, committer, message)
        except RuntimeError as exc:
            assert str(exc) == "Elasticsearch unavailable"
        else:
            raise AssertionError("Expected indexing failure")

        assert committer.commits == 0


def test_search_client_uses_paper_id_as_stable_document_id() -> None:
    asyncio.run(_run_search_client_stable_id())


async def _run_search_client_stable_id() -> None:
    elasticsearch = FakeElasticsearch()
    search_client = PaperSearchClient(
        elasticsearch_client=elasticsearch,
        index_name="biowatch-test-papers",
    )
    paper = Paper(
        id=42,
        source="europe_pmc",
        source_id="MED:123",
        title="Spatial transcriptomics in cancer",
    )

    await search_client.index_paper(paper)

    assert elasticsearch.index_calls == [
        {
            "index": "biowatch-test-papers",
            "id": "42",
            "document": {
                "id": 42,
                "source": "europe_pmc",
                "source_id": "MED:123",
                "title": "Spatial transcriptomics in cancer",
                "abstract": None,
                "journal": None,
                "publication_date": None,
                "doi": None,
                "url": None,
                "created_at": None,
            },
        }
    ]
    assert elasticsearch.indices.refreshed == ["biowatch-test-papers"]
