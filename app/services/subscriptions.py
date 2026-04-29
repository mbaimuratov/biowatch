from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IngestionRun, Topic
from app.services import ingestion as ingestion_service

DAILY = "daily"
WEEKLY = "weekly"


@dataclass(frozen=True)
class SubscriptionIngestDueResult:
    topics_checked: int
    topics_enqueued: int
    ingestion_run_ids: list[int]
    job_ids: list[str]


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_topic_due(topic: Topic, now: datetime | None = None) -> bool:
    if not topic.enabled:
        return False
    if topic.last_ingested_at is None:
        return True

    now_utc = _as_utc(now or utc_now())
    last_ingested_at = _as_utc(topic.last_ingested_at)

    if topic.ingestion_frequency == DAILY:
        return last_ingested_at <= now_utc - timedelta(hours=24)
    if topic.ingestion_frequency == WEEKLY:
        return last_ingested_at <= now_utc - timedelta(days=7)
    return False


async def list_enabled_topics(session: AsyncSession) -> list[Topic]:
    result = await session.scalars(select(Topic).where(Topic.enabled.is_(True)).order_by(Topic.id))
    return list(result)


async def list_due_topics(session: AsyncSession, now: datetime | None = None) -> list[Topic]:
    enabled_topics = await list_enabled_topics(session)
    return [topic for topic in enabled_topics if is_topic_due(topic, now)]


async def enqueue_due_topic_ingestions(
    session: AsyncSession,
    ingestion_queue: object,
    job_func: Callable[[int], int],
    now: datetime | None = None,
) -> SubscriptionIngestDueResult:
    enqueued_at = now or utc_now()
    enabled_topics = await list_enabled_topics(session)
    due_topics = [topic for topic in enabled_topics if is_topic_due(topic, enqueued_at)]
    runs: list[IngestionRun] = []

    for topic in due_topics:
        run = await ingestion_service.enqueue_topic_ingestion(
            session,
            topic,
            ingestion_queue,
            job_func,
            enqueued_at=enqueued_at,
        )
        runs.append(run)

    return SubscriptionIngestDueResult(
        topics_checked=len(enabled_topics),
        topics_enqueued=len(runs),
        ingestion_run_ids=[run.id for run in runs],
        job_ids=[run.job_id for run in runs if run.job_id is not None],
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
