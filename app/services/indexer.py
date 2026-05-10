from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.papers import InvalidPaperIngestedEvent, parse_paper_ingested_event
from app.kafka.consumer import KafkaMessage
from app.models import Paper
from app.search.client import PaperSearchClient

logger = logging.getLogger(__name__)


class OffsetCommitter(Protocol):
    async def commit(self) -> None: ...


async def process_paper_ingested_message(
    session: AsyncSession,
    search_client: PaperSearchClient,
    committer: OffsetCommitter,
    message: KafkaMessage,
) -> bool:
    try:
        event = parse_paper_ingested_event(message.value)
    except InvalidPaperIngestedEvent as exc:
        logger.warning(
            "Invalid paper.ingested event",
            extra={
                "event_id": None,
                "paper_id": None,
                "topic": message.topic,
                "partition": message.partition,
                "offset": message.offset,
                "indexing_result": "invalid_event",
                "error": str(exc),
            },
        )
        return False

    paper = await session.get(Paper, event.paper_id)
    if paper is None:
        logger.warning(
            "Paper from paper.ingested event was not found",
            extra={
                "event_id": event.event_id,
                "paper_id": event.paper_id,
                "topic": message.topic,
                "partition": message.partition,
                "offset": message.offset,
                "indexing_result": "paper_not_found",
            },
        )
        return False

    try:
        await search_client.index_paper(paper)
    except Exception:
        logger.exception(
            "Failed to index paper from Kafka event",
            extra={
                "event_id": event.event_id,
                "paper_id": event.paper_id,
                "topic": message.topic,
                "partition": message.partition,
                "offset": message.offset,
                "indexing_result": "failed",
            },
        )
        raise

    await committer.commit()
    logger.info(
        "Indexed paper from Kafka event",
        extra={
            "event_id": event.event_id,
            "paper_id": event.paper_id,
            "topic": message.topic,
            "partition": message.partition,
            "offset": message.offset,
            "indexing_result": "indexed",
        },
    )
    return True
