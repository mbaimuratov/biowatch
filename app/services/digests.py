import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Digest, DigestItem, Paper, Topic, TopicPaper
from app.observability.metrics import (
    DIGEST_GENERATION_DURATION_SECONDS,
    DIGEST_GENERATIONS_TOTAL,
    DIGEST_ITEMS_GENERATED_TOTAL,
)

DIGEST_STATUS_GENERATED = "generated"
SUMMARY_STATUS_NOT_STARTED = "not_started"


def utc_now() -> datetime:
    return datetime.now(UTC)


async def generate_today_digest(session: AsyncSession, now: datetime | None = None) -> Digest:
    started_at = time.perf_counter()
    status = "failed"
    generated_at = now or utc_now()
    try:
        digest = await _generate_digest_for_date(session, generated_at.date(), generated_at)
        status = "generated"
        DIGEST_ITEMS_GENERATED_TOTAL.inc(digest.paper_count)
        return digest
    except Exception:
        status = "failed"
        raise
    finally:
        DIGEST_GENERATIONS_TOTAL.labels(status=status).inc()
        DIGEST_GENERATION_DURATION_SECONDS.labels(status=status).observe(
            time.perf_counter() - started_at
        )


async def get_today_digest(session: AsyncSession, now: datetime | None = None) -> Digest | None:
    today = (now or utc_now()).date()
    return await get_digest_by_date(session, today)


async def get_digest_by_date(session: AsyncSession, digest_date: date) -> Digest | None:
    return await session.scalar(
        select(Digest)
        .where(Digest.digest_date == digest_date)
        .options(
            selectinload(Digest.items).selectinload(DigestItem.paper),
            selectinload(Digest.items).selectinload(DigestItem.topic),
        )
    )


async def _generate_digest_for_date(
    session: AsyncSession,
    digest_date: date,
    generated_at: datetime,
) -> Digest:
    digest = await session.scalar(select(Digest).where(Digest.digest_date == digest_date))
    if digest is None:
        digest = Digest(digest_date=digest_date)
        session.add(digest)
        await session.flush()

    await session.execute(delete(DigestItem).where(DigestItem.digest_id == digest.id))

    matches = await _list_recent_matches(session, generated_at - timedelta(hours=24))
    for rank, match in enumerate(matches, start=1):
        topic = match.topic
        paper = match.paper
        session.add(
            DigestItem(
                digest_id=digest.id,
                paper_id=paper.id,
                topic_id=topic.id,
                rank=rank,
                reason=f"Matched topic: {topic.name}",
            )
        )

    digest.status = DIGEST_STATUS_GENERATED
    digest.summary_status = SUMMARY_STATUS_NOT_STARTED
    digest.paper_count = len(matches)
    digest.generated_at = generated_at
    await session.commit()

    generated_digest = await get_digest_by_date(session, digest_date)
    if generated_digest is None:
        raise RuntimeError(f"Digest {digest_date.isoformat()} was not persisted")
    return generated_digest


async def _list_recent_matches(session: AsyncSession, matched_since: datetime) -> list[TopicPaper]:
    result = await session.scalars(
        select(TopicPaper)
        .join(TopicPaper.paper)
        .join(TopicPaper.topic)
        .where(Topic.enabled.is_(True), TopicPaper.matched_at >= matched_since)
        .options(
            selectinload(TopicPaper.paper),
            selectinload(TopicPaper.topic),
        )
        .order_by(
            Paper.publication_date.desc().nulls_last(),
            Paper.created_at.desc(),
            Paper.id.desc(),
            Topic.id.asc(),
        )
    )
    return list(result)
