import asyncio
import logging

from rq import Queue

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.jobs.delivery import (
    process_morning_delivery_preparation_job,
    process_morning_delivery_send_job,
)
from app.jobs.queues import DELIVERY_QUEUE_NAME, get_redis_connection
from app.observability.logging import configure_logging
from app.services.telegram_deliveries import (
    enqueue_due_morning_delivery_preparations,
    enqueue_due_morning_delivery_sends,
)

logger = logging.getLogger(__name__)


async def run_scheduler_loop() -> None:
    settings = get_settings()
    redis_connection = get_redis_connection()
    delivery_queue = Queue(DELIVERY_QUEUE_NAME, connection=redis_connection)
    logger.info(
        "Telegram delivery scheduler started",
        extra={"interval_seconds": settings.scheduler_interval_seconds},
    )

    while True:
        async with SessionLocal() as session:
            result = await enqueue_due_morning_delivery_preparations(
                session,
                delivery_queue,
                process_morning_delivery_preparation_job,
            )
            if result.deliveries_enqueued:
                logger.info(
                    "Queued Telegram morning delivery preparations",
                    extra={
                        "subscribers_checked": result.subscribers_checked,
                        "deliveries_enqueued": result.deliveries_enqueued,
                        "delivery_ids": result.delivery_ids,
                    },
                )
            send_result = await enqueue_due_morning_delivery_sends(
                session,
                delivery_queue,
                process_morning_delivery_send_job,
            )
            if send_result.deliveries_enqueued:
                logger.info(
                    "Queued ready Telegram morning deliveries for send",
                    extra={
                        "subscribers_checked": send_result.subscribers_checked,
                        "deliveries_enqueued": send_result.deliveries_enqueued,
                        "delivery_ids": send_result.delivery_ids,
                    },
                )
        await asyncio.sleep(settings.scheduler_interval_seconds)


def main() -> None:
    configure_logging()
    asyncio.run(run_scheduler_loop())


if __name__ == "__main__":
    main()
