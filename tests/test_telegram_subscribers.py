import asyncio
from datetime import time

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models import TelegramSubscriber, Topic
from app.schemas.telegram_subscribers import TelegramSubscriberCreate, TelegramSubscriberUpdate
from app.schemas.topics import TopicCreate
from app.services import telegram_subscribers as subscriber_service
from app.services import topics as topic_service


def test_create_telegram_subscriber_uses_defaults(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            subscriber = await subscriber_service.upsert_telegram_subscriber(
                session,
                TelegramSubscriberCreate(telegram_chat_id=1234567890123),
            )
            return {
                "telegram_chat_id": subscriber.telegram_chat_id,
                "timezone": subscriber.timezone,
                "morning_send_time": subscriber.morning_send_time,
                "article_count": subscriber.article_count,
                "enabled": subscriber.enabled,
                "created_at": subscriber.created_at is not None,
                "updated_at": subscriber.updated_at is not None,
            }

    assert asyncio.run(scenario()) == {
        "telegram_chat_id": 1234567890123,
        "timezone": "Europe/Rome",
        "morning_send_time": time(8, 0),
        "article_count": 5,
        "enabled": True,
        "created_at": True,
        "updated_at": True,
    }


def test_upsert_telegram_subscriber_updates_existing_row(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            created = await subscriber_service.upsert_telegram_subscriber(
                session,
                TelegramSubscriberCreate(
                    telegram_chat_id=42,
                    telegram_user_id=100,
                    username="old",
                    first_name="Old",
                ),
            )
            updated = await subscriber_service.upsert_telegram_subscriber(
                session,
                TelegramSubscriberCreate(
                    telegram_chat_id=42,
                    telegram_user_id=200,
                    username="new",
                    first_name="New",
                    timezone="UTC",
                    morning_send_time=time(9, 30),
                    article_count=3,
                    enabled=False,
                ),
            )
            count = len(list(await session.scalars(select(TelegramSubscriber))))
            return {
                "same_id": created.id == updated.id,
                "count": count,
                "telegram_user_id": updated.telegram_user_id,
                "username": updated.username,
                "first_name": updated.first_name,
                "timezone": updated.timezone,
                "morning_send_time": updated.morning_send_time,
                "article_count": updated.article_count,
                "enabled": updated.enabled,
            }

    assert asyncio.run(scenario()) == {
        "same_id": True,
        "count": 1,
        "telegram_user_id": 200,
        "username": "new",
        "first_name": "New",
        "timezone": "UTC",
        "morning_send_time": time(9, 30),
        "article_count": 3,
        "enabled": False,
    }


def test_update_subscriber_settings_and_topic_helpers(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            subscriber = await subscriber_service.upsert_telegram_subscriber(
                session,
                TelegramSubscriberCreate(telegram_chat_id=99),
            )
            subscriber = await subscriber_service.update_subscriber_settings(
                session,
                subscriber,
                TelegramSubscriberUpdate(
                    timezone="Asia/Almaty",
                    morning_send_time=time(7, 15),
                    article_count=4,
                ),
            )
            owned = await subscriber_service.create_topic_for_subscriber(
                session,
                subscriber,
                TopicCreate(
                    name="Owned topic",
                    query="owned query",
                    priority=10,
                    max_papers_per_run=4,
                ),
            )
            global_topic = await topic_service.create_topic(
                session,
                TopicCreate(name="Global topic", query="global query"),
            )
            listed_topics = await subscriber_service.list_subscriber_topics(session, subscriber)
            return {
                "timezone": subscriber.timezone,
                "morning_send_time": subscriber.morning_send_time,
                "article_count": subscriber.article_count,
                "owned_subscriber_id": owned.subscriber_id,
                "owned_priority": owned.priority,
                "owned_max_papers": owned.max_papers_per_run,
                "global_subscriber_id": global_topic.subscriber_id,
                "listed_topic_ids": [topic.id for topic in listed_topics],
            }

    result = asyncio.run(scenario())

    assert result["timezone"] == "Asia/Almaty"
    assert result["morning_send_time"] == time(7, 15)
    assert result["article_count"] == 4
    assert result["owned_subscriber_id"] is not None
    assert result["owned_priority"] == 10
    assert result["owned_max_papers"] == 4
    assert result["global_subscriber_id"] is None
    assert len(result["listed_topic_ids"]) == 1


def test_deleting_subscriber_preserves_topic_with_null_subscriber(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            subscriber = await subscriber_service.upsert_telegram_subscriber(
                session,
                TelegramSubscriberCreate(telegram_chat_id=77),
            )
            topic = await subscriber_service.create_topic_for_subscriber(
                session,
                subscriber,
                TopicCreate(name="Owned topic", query="owned query"),
            )
            topic_id = topic.id
            await session.delete(subscriber)
            await session.commit()

            preserved_topic = await session.get(Topic, topic_id)
            subscribers = list(await session.scalars(select(TelegramSubscriber)))
            return {
                "subscriber_count": len(subscribers),
                "topic_exists": preserved_topic is not None,
                "topic_subscriber_id": preserved_topic.subscriber_id,
            }

    assert asyncio.run(scenario()) == {
        "subscriber_count": 0,
        "topic_exists": True,
        "topic_subscriber_id": None,
    }


def test_subscriber_and_topic_validation_rejects_invalid_counts() -> None:
    with pytest.raises(ValidationError):
        TelegramSubscriberCreate(telegram_chat_id=1, article_count=0)

    with pytest.raises(ValidationError):
        TopicCreate(name="Invalid", query="invalid", max_papers_per_run=0)
