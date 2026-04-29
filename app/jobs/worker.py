import logging

from prometheus_client import start_http_server
from redis import Redis
from rq import Queue, SimpleWorker

from app.core.config import get_settings
from app.jobs.queues import DELIVERY_QUEUE_NAME, INGESTION_QUEUE_NAME
from app.observability.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    settings = get_settings()
    redis_connection = Redis.from_url(settings.redis_url)
    queues = [
        Queue(INGESTION_QUEUE_NAME, connection=redis_connection),
        Queue(DELIVERY_QUEUE_NAME, connection=redis_connection),
    ]

    start_http_server(settings.worker_metrics_port)
    logger.info(
        "Worker metrics server started",
        extra={"metrics_port": settings.worker_metrics_port},
    )

    worker = SimpleWorker(queues, connection=redis_connection)
    worker.work()


if __name__ == "__main__":
    main()
