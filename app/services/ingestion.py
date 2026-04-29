import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.europe_pmc import EuropePMCClient
from app.models import IngestionRun, Paper, Topic, TopicPaper
from app.search.client import PaperSearchClient

EUROPE_PMC_SOURCE = "europe_pmc"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def list_ingestion_runs(session: AsyncSession) -> list[IngestionRun]:
    result = await session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()))
    return list(result)


async def create_queued_run(session: AsyncSession, topic: Topic) -> IngestionRun:
    run = IngestionRun(
        topic_id=topic.id,
        status=STATUS_QUEUED,
        started_at=_utc_now(),
        records_fetched=0,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def mark_run_enqueued(session: AsyncSession, run: IngestionRun, job_id: str) -> IngestionRun:
    run.job_id = job_id
    await session.commit()
    await session.refresh(run)
    return run


async def enqueue_topic_ingestion(
    session: AsyncSession,
    topic: Topic,
    ingestion_queue: object,
    job_func: Callable[[int], int],
    enqueued_at: datetime | None = None,
) -> IngestionRun:
    run = await create_queued_run(session, topic)
    job = ingestion_queue.enqueue(job_func, run.id)
    run.job_id = job.id
    topic.last_ingested_at = enqueued_at or _utc_now()
    await session.commit()
    await session.refresh(run)
    await session.refresh(topic)
    return run


async def process_ingestion_run(
    session: AsyncSession,
    run_id: int,
    europe_pmc_client: EuropePMCClient | None = None,
    paper_search_client: PaperSearchClient | None = None,
) -> IngestionRun:
    run = await session.get(IngestionRun, run_id)
    if run is None:
        raise ValueError(f"Ingestion run {run_id} not found")

    topic = await session.get(Topic, run.topic_id)
    if topic is None:
        run.status = STATUS_FAILED
        run.error_message = f"Topic {run.topic_id} not found"
        run.finished_at = _utc_now()
        await session.commit()
        await session.refresh(run)
        return run

    client = europe_pmc_client or EuropePMCClient()
    indexed_papers: list[Paper] = []
    run.status = STATUS_RUNNING
    run.error_message = None
    run.records_fetched = 0
    await session.commit()

    try:
        search_response = await client.search(topic.query, page_size=topic.max_results_per_run)
        payloads = _normalize_search_response(search_response)
        for payload in payloads:
            paper = await _upsert_paper(session, payload)
            await _match_topic_to_paper(session, topic, paper)
            indexed_papers.append(paper)

        run.status = STATUS_COMPLETED
        run.records_fetched = len(payloads)
        run.finished_at = _utc_now()
        topic.last_successful_ingestion_at = run.finished_at
    except Exception as exc:
        run.status = STATUS_FAILED
        run.error_message = str(exc)
        run.finished_at = _utc_now()

    await session.commit()
    await session.refresh(run)
    if run.status == STATUS_COMPLETED and indexed_papers:
        search_client = paper_search_client or PaperSearchClient()
        try:
            await search_client.index_papers(indexed_papers)
        except Exception:
            logger.exception("Failed to index papers for ingestion run %s", run.id)
        finally:
            if paper_search_client is None:
                await search_client.close()
    return run


def _normalize_search_response(search_response: dict[str, Any]) -> list[dict[str, Any]]:
    results = search_response.get("resultList", {}).get("result", [])
    if not isinstance(results, list):
        return []

    payloads: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        payload = _normalize_result(result)
        if payload is not None:
            payloads.append(payload)
    return payloads


def _normalize_result(result: dict[str, Any]) -> dict[str, Any] | None:
    raw_source = _clean_text(result.get("source"))
    raw_id = _clean_text(result.get("id"))
    if raw_source is None or raw_id is None:
        return None

    source_id = f"{raw_source}:{raw_id}"
    title = _clean_text(result.get("title")) or f"Untitled Europe PMC record {source_id}"

    return {
        "source": EUROPE_PMC_SOURCE,
        "source_id": source_id,
        "title": title,
        "abstract": _clean_text(result.get("abstractText")),
        "journal": _clean_text(result.get("journalTitle")),
        "publication_date": _parse_publication_date(result),
        "doi": _clean_text(result.get("doi")),
        "url": f"https://europepmc.org/article/{raw_source}/{raw_id}",
    }


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _parse_publication_date(result: dict[str, Any]) -> date | None:
    publication_date = _parse_date_text(_clean_text(result.get("firstPublicationDate")))
    if publication_date is not None:
        return publication_date

    publication_date = _parse_date_text(_clean_text(result.get("firstIndexDate")))
    if publication_date is not None:
        return publication_date

    pub_year = _clean_text(result.get("pubYear"))
    if pub_year is not None and pub_year.isdigit():
        return date(int(pub_year), 1, 1)

    return None


def _parse_date_text(value: str | None) -> date | None:
    if value is None:
        return None

    try:
        if len(value) == 4:
            return date(int(value), 1, 1)
        if len(value) == 7:
            year, month = value.split("-")
            return date(int(year), int(month), 1)
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


async def _upsert_paper(session: AsyncSession, payload: dict[str, Any]) -> Paper:
    paper = await session.scalar(
        select(Paper).where(
            Paper.source == payload["source"],
            Paper.source_id == payload["source_id"],
        )
    )
    if paper is None:
        paper = Paper(**payload)
        session.add(paper)
        await session.flush()
        return paper

    for field, value in payload.items():
        setattr(paper, field, value)
    await session.flush()
    return paper


async def _match_topic_to_paper(session: AsyncSession, topic: Topic, paper: Paper) -> None:
    existing_match = await session.get(
        TopicPaper,
        {"topic_id": topic.id, "paper_id": paper.id},
    )
    if existing_match is None:
        session.add(TopicPaper(topic_id=topic.id, paper_id=paper.id))
