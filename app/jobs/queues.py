from redis import Redis
from rq import Queue

from app.core.config import get_settings

INGESTION_QUEUE_NAME = "biowatch-ingestion"


def get_redis_connection() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_ingestion_queue() -> Queue:
    return Queue(INGESTION_QUEUE_NAME, connection=get_redis_connection())
