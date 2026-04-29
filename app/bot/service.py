from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.parsing import parse_positive_int, parse_time, parse_timezone, parse_topic_command
from app.models import Paper, TelegramSubscriber, Topic, TopicPaper
from app.schemas.telegram_subscribers import TelegramSubscriberCreate, TelegramSubscriberUpdate
from app.schemas.topics import TopicCreate
from app.services import telegram_subscribers as subscriber_service
from app.services.digests import utc_now


@dataclass(frozen=True)
class TelegramIdentity:
    chat_id: int
    user_id: int | None = None
    username: str | None = None
    first_name: str | None = None


HELP_TEXT = """BioWatch commands:
/start - register this chat
/settings - show your settings
/topics - list your enabled topics
/addtopic Name | Europe PMC query
/removetopic 3 - disable a topic
/count 5 - set morning article count
/time 08:30 - set morning send time
/timezone Europe/Rome - set timezone
/pause - pause morning briefs
/resume - resume morning briefs
/digest - send a digest now"""


async def start(session: AsyncSession, identity: TelegramIdentity) -> str:
    subscriber = await ensure_subscriber(session, identity)
    name = subscriber.first_name or subscriber.username or "there"
    return (
        f"Hi {name}. BioWatch is ready.\n\n"
        "Add your first topic with:\n"
        "/addtopic Spatial transcriptomics | spatial transcriptomics tumor microenvironment cancer"
    )


async def ensure_subscriber(
    session: AsyncSession,
    identity: TelegramIdentity,
) -> TelegramSubscriber:
    subscriber = await subscriber_service.get_subscriber_by_chat_id(session, identity.chat_id)
    if subscriber is None:
        return await subscriber_service.upsert_telegram_subscriber(
            session,
            TelegramSubscriberCreate(
                telegram_chat_id=identity.chat_id,
                telegram_user_id=identity.user_id,
                username=identity.username,
                first_name=identity.first_name,
            ),
        )

    subscriber.telegram_user_id = identity.user_id
    subscriber.username = identity.username
    subscriber.first_name = identity.first_name
    subscriber.updated_at = utc_now()
    await session.commit()
    await session.refresh(subscriber)
    return subscriber


async def settings(session: AsyncSession, identity: TelegramIdentity) -> str:
    subscriber = await ensure_subscriber(session, identity)
    enabled = "enabled" if subscriber.enabled else "paused"
    return (
        "Settings\n"
        f"Status: {enabled}\n"
        f"Timezone: {subscriber.timezone}\n"
        f"Morning time: {subscriber.morning_send_time.strftime('%H:%M')}\n"
        f"Article count: {subscriber.article_count}"
    )


async def list_topics(session: AsyncSession, identity: TelegramIdentity) -> str:
    subscriber = await ensure_subscriber(session, identity)
    topics = [
        topic
        for topic in await subscriber_service.list_subscriber_topics(session, subscriber)
        if topic.enabled
    ]
    if not topics:
        return "No enabled topics yet. Add one with /addtopic Name | query"

    lines = ["Enabled topics:"]
    lines.extend(f"{topic.id}. {topic.name}" for topic in topics)
    return "\n".join(lines)


async def add_topic(session: AsyncSession, identity: TelegramIdentity, text: str) -> str:
    subscriber = await ensure_subscriber(session, identity)
    command = parse_topic_command(text)
    topic = await subscriber_service.create_topic_for_subscriber(
        session,
        subscriber,
        TopicCreate(name=command.name, query=command.query),
    )
    return f"Added topic {topic.id}: {topic.name}"


async def remove_topic(session: AsyncSession, identity: TelegramIdentity, text: str) -> str:
    subscriber = await ensure_subscriber(session, identity)
    topic_id = parse_positive_int(text, "removetopic")
    topic = await session.get(Topic, topic_id)
    if topic is None or topic.subscriber_id != subscriber.id:
        return f"Topic {topic_id} was not found for this chat."

    topic.enabled = False
    await session.commit()
    return f"Disabled topic {topic.id}: {topic.name}"


async def set_count(session: AsyncSession, identity: TelegramIdentity, text: str) -> str:
    subscriber = await ensure_subscriber(session, identity)
    count = parse_positive_int(text, "count")
    await subscriber_service.update_subscriber_settings(
        session,
        subscriber,
        TelegramSubscriberUpdate(article_count=count),
    )
    return f"Morning article count set to {count}."


async def set_time(session: AsyncSession, identity: TelegramIdentity, text: str) -> str:
    subscriber = await ensure_subscriber(session, identity)
    send_time = parse_time(text)
    await subscriber_service.update_subscriber_settings(
        session,
        subscriber,
        TelegramSubscriberUpdate(morning_send_time=send_time),
    )
    return f"Morning send time set to {send_time.strftime('%H:%M')}."


async def set_timezone(session: AsyncSession, identity: TelegramIdentity, text: str) -> str:
    subscriber = await ensure_subscriber(session, identity)
    timezone = parse_timezone(text)
    await subscriber_service.update_subscriber_settings(
        session,
        subscriber,
        TelegramSubscriberUpdate(timezone=timezone),
    )
    return f"Timezone set to {timezone}."


async def pause(session: AsyncSession, identity: TelegramIdentity) -> str:
    subscriber = await ensure_subscriber(session, identity)
    await subscriber_service.update_subscriber_settings(
        session,
        subscriber,
        TelegramSubscriberUpdate(enabled=False),
    )
    return "Morning briefs paused."


async def resume(session: AsyncSession, identity: TelegramIdentity) -> str:
    subscriber = await ensure_subscriber(session, identity)
    await subscriber_service.update_subscriber_settings(
        session,
        subscriber,
        TelegramSubscriberUpdate(enabled=True),
    )
    return "Morning briefs resumed."


async def digest(session: AsyncSession, identity: TelegramIdentity) -> str:
    subscriber = await ensure_subscriber(session, identity)
    matches = await _list_subscriber_digest_matches(session, subscriber)
    if not matches:
        return "No recent papers matched your enabled topics yet."

    lines = ["Today's BioWatch digest:"]
    for index, match in enumerate(matches, start=1):
        paper = match.paper
        topic = match.topic
        lines.append("")
        lines.append(f"{index}. {paper.title}")
        if paper.url:
            lines.append(paper.url)
        lines.append(f"Reason: Matched topic: {topic.name}")
    return "\n".join(lines)


async def _list_subscriber_digest_matches(
    session: AsyncSession,
    subscriber: TelegramSubscriber,
) -> list[TopicPaper]:
    matched_since = utc_now() - timedelta(hours=24)
    result = await session.scalars(
        select(TopicPaper)
        .join(TopicPaper.paper)
        .join(TopicPaper.topic)
        .where(
            Topic.subscriber_id == subscriber.id,
            Topic.enabled.is_(True),
            TopicPaper.matched_at >= matched_since,
        )
        .options(
            selectinload(TopicPaper.paper),
            selectinload(TopicPaper.topic),
        )
        .order_by(
            Paper.publication_date.desc().nulls_last(),
            Paper.created_at.desc(),
            Paper.id.desc(),
            Topic.id.asc(),
        )
        .limit(subscriber.article_count)
    )
    return list(result)
