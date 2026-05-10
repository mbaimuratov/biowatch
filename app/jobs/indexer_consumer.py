from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.kafka.consumer import KafkaConsumer
from app.observability.logging import configure_logging
from app.search.client import PaperSearchClient
from app.services.indexer import process_paper_ingested_message

logger = logging.getLogger(__name__)


async def run_indexer_consumer() -> None:
    settings = get_settings()
    if not settings.kafka_enabled:
        logger.info("Kafka indexer consumer disabled")
        return
    if not settings.kafka_bootstrap_servers:
        raise RuntimeError("BIOWATCH_KAFKA_BOOTSTRAP_SERVERS is required when Kafka is enabled")

    consumer = KafkaConsumer(
        topics=[settings.kafka_indexer_topic],
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_indexer_group_id,
        client_id=f"{settings.kafka_client_id}-indexer",
    )
    search_client = PaperSearchClient()
    await consumer.start()
    logger.info(
        "Kafka indexer consumer started",
        extra={
            "topic": settings.kafka_indexer_topic,
            "consumer_group": settings.kafka_indexer_group_id,
            "bootstrap_servers": settings.kafka_bootstrap_servers,
        },
    )
    try:
        async for message in consumer.messages():
            async with SessionLocal() as session:
                await process_paper_ingested_message(session, search_client, consumer, message)
    finally:
        await search_client.close()
        await consumer.stop()


def main() -> None:
    configure_logging()
    asyncio.run(run_indexer_consumer())


if __name__ == "__main__":
    main()
