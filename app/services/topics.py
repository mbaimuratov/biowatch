from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic
from app.schemas.topics import TopicCreate


async def create_topic(session: AsyncSession, data: TopicCreate) -> Topic:
    topic = Topic(
        name=data.name,
        query=data.query,
        enabled=data.enabled,
    )
    session.add(topic)
    await session.commit()
    await session.refresh(topic)
    return topic


async def list_topics(session: AsyncSession) -> list[Topic]:
    result = await session.scalars(select(Topic).order_by(Topic.id))
    return list(result)


async def get_topic(session: AsyncSession, topic_id: int) -> Topic | None:
    return await session.get(Topic, topic_id)
