from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IngestionRun, TelegramSubscriber, Topic
from app.schemas.topics import TopicCreate

ACTIVE_INGESTION_STATUSES = ("queued", "running")


class TopicHasActiveIngestionError(Exception):
    pass


class TopicSubscriberNotFoundError(Exception):
    pass


async def create_topic(session: AsyncSession, data: TopicCreate) -> Topic:
    if data.subscriber_id is not None:
        subscriber = await session.get(TelegramSubscriber, data.subscriber_id)
        if subscriber is None:
            raise TopicSubscriberNotFoundError

    topic = Topic(
        subscriber_id=data.subscriber_id,
        name=data.name,
        query=data.query,
        enabled=data.enabled,
        ingestion_frequency=data.ingestion_frequency,
        priority=data.priority,
        max_papers_per_run=data.max_papers_per_run,
    )
    session.add(topic)
    await session.commit()
    await session.refresh(topic)
    return topic


async def list_topics(session: AsyncSession) -> list[Topic]:
    result = await session.scalars(select(Topic).order_by(Topic.id))
    return list(result)


async def list_topics_for_subscriber(session: AsyncSession, subscriber_id: int) -> list[Topic]:
    result = await session.scalars(
        select(Topic)
        .where(Topic.subscriber_id == subscriber_id)
        .order_by(Topic.priority.desc(), Topic.id)
    )
    return list(result)


async def get_topic(session: AsyncSession, topic_id: int) -> Topic | None:
    return await session.get(Topic, topic_id)


async def delete_topic(session: AsyncSession, topic_id: int) -> bool:
    topic = await get_topic(session, topic_id)
    if topic is None:
        return False

    active_run_id = await session.scalar(
        select(IngestionRun.id)
        .where(
            IngestionRun.topic_id == topic_id,
            IngestionRun.status.in_(ACTIVE_INGESTION_STATUSES),
        )
        .limit(1)
    )
    if active_run_id is not None:
        raise TopicHasActiveIngestionError

    await session.delete(topic)
    await session.commit()
    return True
