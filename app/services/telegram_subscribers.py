from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramSubscriber, Topic
from app.schemas.telegram_subscribers import TelegramSubscriberCreate, TelegramSubscriberUpdate
from app.schemas.topics import TopicCreate
from app.services import topics as topic_service


def utc_now() -> datetime:
    return datetime.now(UTC)


async def upsert_telegram_subscriber(
    session: AsyncSession,
    data: TelegramSubscriberCreate,
) -> TelegramSubscriber:
    subscriber = await get_subscriber_by_chat_id(session, data.telegram_chat_id)
    if subscriber is None:
        subscriber = TelegramSubscriber(
            telegram_chat_id=data.telegram_chat_id,
            telegram_user_id=data.telegram_user_id,
            username=data.username,
            first_name=data.first_name,
            timezone=data.timezone,
            morning_send_time=data.morning_send_time,
            article_count=data.article_count,
            enabled=data.enabled,
        )
        session.add(subscriber)
    else:
        subscriber.telegram_user_id = data.telegram_user_id
        subscriber.username = data.username
        subscriber.first_name = data.first_name
        subscriber.timezone = data.timezone
        subscriber.morning_send_time = data.morning_send_time
        subscriber.article_count = data.article_count
        subscriber.enabled = data.enabled
        subscriber.updated_at = utc_now()

    await session.commit()
    await session.refresh(subscriber)
    return subscriber


async def get_subscriber_by_chat_id(
    session: AsyncSession,
    telegram_chat_id: int,
) -> TelegramSubscriber | None:
    return await session.scalar(
        select(TelegramSubscriber).where(TelegramSubscriber.telegram_chat_id == telegram_chat_id)
    )


async def update_subscriber_settings(
    session: AsyncSession,
    subscriber: TelegramSubscriber,
    data: TelegramSubscriberUpdate,
) -> TelegramSubscriber:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscriber, field, value)
    subscriber.updated_at = utc_now()
    await session.commit()
    await session.refresh(subscriber)
    return subscriber


async def list_subscriber_topics(
    session: AsyncSession,
    subscriber: TelegramSubscriber,
) -> list[Topic]:
    return await topic_service.list_topics_for_subscriber(session, subscriber.id)


async def create_topic_for_subscriber(
    session: AsyncSession,
    subscriber: TelegramSubscriber,
    data: TopicCreate,
) -> Topic:
    topic_data = data.model_copy(update={"subscriber_id": subscriber.id})
    return await topic_service.create_topic(session, topic_data)
