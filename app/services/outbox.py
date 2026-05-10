from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EventOutbox

PENDING = "pending"
PUBLISHED = "published"


class EventProducer(Protocol):
    async def publish(self, topic: str, payload: dict, key: str | None = None) -> None: ...


@dataclass(frozen=True)
class OutboxPublishResult:
    published: int
    failed: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def list_pending_events(session: AsyncSession, limit: int = 100) -> list[EventOutbox]:
    result = await session.scalars(
        select(EventOutbox)
        .where(EventOutbox.status == PENDING)
        .order_by(EventOutbox.id)
        .limit(limit)
    )
    return list(result)


async def publish_pending_events(
    session: AsyncSession,
    producer: EventProducer,
    limit: int = 100,
) -> OutboxPublishResult:
    published = 0
    failed = 0
    events = await list_pending_events(session, limit=limit)

    for event in events:
        try:
            await producer.publish(event.topic, event.payload, key=event.key)
        except Exception as exc:
            event.attempts += 1
            event.last_error = str(exc)
            failed += 1
        else:
            event.status = PUBLISHED
            event.published_at = _utc_now()
            event.last_error = None
            published += 1
        await session.commit()

    return OutboxPublishResult(published=published, failed=failed)
