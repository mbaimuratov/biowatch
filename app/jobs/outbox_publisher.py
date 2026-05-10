from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.kafka.producer import KafkaProducer
from app.observability.logging import configure_logging
from app.services.outbox import publish_pending_events

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 5


async def run_outbox_publisher() -> None:
    settings = get_settings()
    if not settings.kafka_enabled:
        logger.info("Kafka outbox publisher disabled")
        return
    if not settings.kafka_bootstrap_servers:
        raise RuntimeError("BIOWATCH_KAFKA_BOOTSTRAP_SERVERS is required when Kafka is enabled")

    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=settings.kafka_client_id,
    )
    await producer.start()
    logger.info(
        "Kafka outbox publisher started",
        extra={
            "bootstrap_servers": settings.kafka_bootstrap_servers,
            "client_id": settings.kafka_client_id,
        },
    )
    try:
        while True:
            async with SessionLocal() as session:
                result = await publish_pending_events(session, producer)
                if result.published or result.failed:
                    logger.info(
                        "Kafka outbox publisher processed events",
                        extra={"published": result.published, "failed": result.failed},
                    )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await producer.stop()


def main() -> None:
    configure_logging()
    asyncio.run(run_outbox_publisher())


if __name__ == "__main__":
    main()
