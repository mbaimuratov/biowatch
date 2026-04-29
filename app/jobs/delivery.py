import asyncio
import logging
import time

from app.bot.sender import TelegramBotSender
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import TelegramDigestDelivery
from app.observability.metrics import (
    TELEGRAM_DELIVERIES_IN_PROGRESS,
    TELEGRAM_DELIVERY_ATTEMPTS_TOTAL,
    TELEGRAM_DELIVERY_DURATION_SECONDS,
    TELEGRAM_DELIVERY_ITEMS_SENT_TOTAL,
)
from app.services.telegram_deliveries import process_morning_delivery

logger = logging.getLogger(__name__)


def process_morning_delivery_job(delivery_id: int) -> int:
    return asyncio.run(_process_morning_delivery_job(delivery_id))


async def _process_morning_delivery_job(delivery_id: int) -> int:
    started_at = time.perf_counter()
    status = "failed"
    item_count = 0
    subscriber_id = None
    TELEGRAM_DELIVERIES_IN_PROGRESS.inc()
    async with SessionLocal() as session:
        try:
            sender = TelegramBotSender(get_settings().telegram_bot_token)
            delivery = await process_morning_delivery(session, delivery_id, sender)
            status = delivery.status
            item_count = len(delivery.items) if "items" in delivery.__dict__ else 0
            subscriber_id = delivery.subscriber_id
            if status == "sent":
                TELEGRAM_DELIVERY_ITEMS_SENT_TOTAL.inc(item_count)
            return delivery_id
        except Exception as exc:
            delivery = await session.get(TelegramDigestDelivery, delivery_id)
            if delivery is not None:
                delivery.status = "failed"
                delivery.error_message = str(exc)
                subscriber_id = delivery.subscriber_id
                await session.commit()
            logger.exception("Telegram delivery job failed", extra={"delivery_id": delivery_id})
            return delivery_id
        finally:
            duration = time.perf_counter() - started_at
            TELEGRAM_DELIVERY_ATTEMPTS_TOTAL.labels(status=status).inc()
            TELEGRAM_DELIVERY_DURATION_SECONDS.labels(status=status).observe(duration)
            TELEGRAM_DELIVERIES_IN_PROGRESS.dec()
            logger.info(
                "Telegram delivery job finished",
                extra={
                    "delivery_id": delivery_id,
                    "subscriber_id": subscriber_id,
                    "status": status,
                    "item_count": item_count,
                    "duration_seconds": round(duration, 6),
                },
            )
