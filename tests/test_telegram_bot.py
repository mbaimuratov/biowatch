import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.bot import handlers
from app.bot import service as bot_service
from app.bot.parsing import (
    BotCommandError,
    parse_positive_int,
    parse_time,
    parse_timezone,
    parse_topic_command,
)
from app.models import Paper, Topic, TopicPaper
from app.schemas.telegram_subscribers import TelegramSubscriberCreate, TelegramSubscriberUpdate
from app.services import telegram_subscribers as subscriber_service


def test_parse_addtopic_command() -> None:
    command = parse_topic_command(
        "Spatial transcriptomics | spatial transcriptomics tumor microenvironment cancer"
    )

    assert command.name == "Spatial transcriptomics"
    assert command.query == "spatial transcriptomics tumor microenvironment cancer"


@pytest.mark.parametrize(
    "text",
    [
        "Spatial transcriptomics",
        "| spatial transcriptomics",
        "Spatial transcriptomics | ",
    ],
)
def test_parse_addtopic_rejects_invalid_input(text: str) -> None:
    with pytest.raises(BotCommandError):
        parse_topic_command(text)


def test_parse_numeric_time_and_timezone_values() -> None:
    assert parse_positive_int("5", "count") == 5
    assert parse_time("08:30").hour == 8
    assert parse_time("08:30").minute == 30
    assert parse_timezone("Europe/Rome") == "Europe/Rome"


@pytest.mark.parametrize(
    ("parser", "value"),
    [
        (lambda value: parse_positive_int(value, "count"), "0"),
        (lambda value: parse_positive_int(value, "count"), "abc"),
        (parse_time, "8:30"),
        (parse_time, "25:99"),
        (parse_timezone, "Not/AZone"),
    ],
)
def test_parse_rejects_invalid_values(parser, value: str) -> None:
    with pytest.raises(BotCommandError):
        parser(value)


def test_bot_service_manages_subscriber_settings_and_topics(async_session_factory) -> None:
    identity = bot_service.TelegramIdentity(
        chat_id=123,
        user_id=456,
        username="reader",
        first_name="Reader",
    )

    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            start_text = await bot_service.start(session, identity)
            count_text = await bot_service.set_count(session, identity, "5")
            time_text = await bot_service.set_time(session, identity, "08:30")
            timezone_text = await bot_service.set_timezone(session, identity, "Europe/Rome")
            pause_text = await bot_service.pause(session, identity)
            resume_text = await bot_service.resume(session, identity)
            add_text = await bot_service.add_topic(
                session,
                identity,
                "Spatial transcriptomics | spatial transcriptomics tumor microenvironment cancer",
            )
            topics_text = await bot_service.list_topics(session, identity)
            topic = await session.scalar(
                select(Topic).where(Topic.name == "Spatial transcriptomics")
            )
            remove_text = await bot_service.remove_topic(session, identity, str(topic.id))
            topics_after_remove = await bot_service.list_topics(session, identity)
            subscriber = await subscriber_service.get_subscriber_by_chat_id(session, 123)
            return {
                "start": start_text,
                "count": count_text,
                "time": time_text,
                "timezone": timezone_text,
                "pause": pause_text,
                "resume": resume_text,
                "add": add_text,
                "topics": topics_text,
                "remove": remove_text,
                "topics_after_remove": topics_after_remove,
                "article_count": subscriber.article_count,
                "morning_send_time": subscriber.morning_send_time.strftime("%H:%M"),
                "enabled": subscriber.enabled,
                "topic_enabled": topic.enabled,
                "topic_subscriber_id": topic.subscriber_id,
            }

    result = asyncio.run(scenario())

    assert "BioWatch is ready" in result["start"]
    assert result["count"] == "Morning article count set to 5."
    assert result["time"] == "Morning send time set to 08:30."
    assert result["timezone"] == "Timezone set to Europe/Rome."
    assert result["pause"] == "Morning briefs paused."
    assert result["resume"] == "Morning briefs resumed."
    assert result["add"].startswith("Added topic")
    assert "Spatial transcriptomics" in result["topics"]
    assert result["remove"].startswith("Disabled topic")
    assert "No enabled topics yet" in result["topics_after_remove"]
    assert result["article_count"] == 5
    assert result["morning_send_time"] == "08:30"
    assert result["enabled"] is True
    assert result["topic_enabled"] is False
    assert result["topic_subscriber_id"] is not None


def test_remove_topic_requires_topic_ownership(async_session_factory) -> None:
    owner = bot_service.TelegramIdentity(chat_id=1)
    stranger = bot_service.TelegramIdentity(chat_id=2)

    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            await bot_service.add_topic(session, owner, "Owner topic | owner query")
            topic = await session.scalar(select(Topic).where(Topic.name == "Owner topic"))
            response = await bot_service.remove_topic(session, stranger, str(topic.id))
            await session.refresh(topic)
            return {"response": response, "enabled": topic.enabled}

    assert asyncio.run(scenario()) == {
        "response": "Topic 1 was not found for this chat.",
        "enabled": True,
    }


def test_digest_is_subscriber_scoped_and_respects_article_count(async_session_factory) -> None:
    now = datetime.now(UTC)
    identity = bot_service.TelegramIdentity(chat_id=100)
    other_identity = bot_service.TelegramIdentity(chat_id=200)

    async def scenario() -> str:
        async with async_session_factory() as session:
            subscriber = await subscriber_service.upsert_telegram_subscriber(
                session,
                TelegramSubscriberCreate(telegram_chat_id=identity.chat_id),
            )
            await subscriber_service.update_subscriber_settings(
                session,
                subscriber,
                TelegramSubscriberUpdate(article_count=1),
            )
            other = await subscriber_service.upsert_telegram_subscriber(
                session,
                TelegramSubscriberCreate(telegram_chat_id=other_identity.chat_id),
            )

            topic = Topic(name="Checkpoint", query="checkpoint", subscriber_id=subscriber.id)
            second_topic = Topic(name="Second", query="second", subscriber_id=subscriber.id)
            other_topic = Topic(name="Other", query="other", subscriber_id=other.id)
            session.add_all([topic, second_topic, other_topic])
            await session.flush()

            included = Paper(
                source="europe_pmc",
                source_id="MED:included",
                title="Included paper",
                publication_date=date(2026, 1, 1),
                url="https://example.test/included",
            )
            excluded_by_count = Paper(
                source="europe_pmc",
                source_id="MED:second",
                title="Second paper",
                publication_date=date(2025, 1, 1),
            )
            excluded_by_subscriber = Paper(
                source="europe_pmc",
                source_id="MED:other",
                title="Other subscriber paper",
                publication_date=date(2027, 1, 1),
            )
            session.add_all([included, excluded_by_count, excluded_by_subscriber])
            await session.flush()
            session.add_all(
                [
                    TopicPaper(
                        topic_id=topic.id,
                        paper_id=included.id,
                        matched_at=now - timedelta(hours=1),
                    ),
                    TopicPaper(
                        topic_id=second_topic.id,
                        paper_id=excluded_by_count.id,
                        matched_at=now - timedelta(hours=1),
                    ),
                    TopicPaper(
                        topic_id=other_topic.id,
                        paper_id=excluded_by_subscriber.id,
                        matched_at=now - timedelta(hours=1),
                    ),
                ]
            )
            await session.commit()
            return await bot_service.digest(session, identity)

    digest_text = asyncio.run(scenario())

    assert "Today's BioWatch digest" in digest_text
    assert "Included paper" in digest_text
    assert "https://example.test/included" in digest_text
    assert "Reason: Matched topic: Checkpoint" in digest_text
    assert "Second paper" not in digest_text
    assert "Other subscriber paper" not in digest_text


def test_handler_replies_without_calling_telegram_api(async_session_factory, monkeypatch) -> None:
    monkeypatch.setattr(handlers, "SessionLocal", async_session_factory)
    update = FakeUpdate(command_text="/addtopic Biomarkers | plasma biomarkers")
    context = FakeContext(args=["Biomarkers", "|", "plasma", "biomarkers"])

    asyncio.run(handlers.addtopic(update, context))

    assert update.message.replies == [("Added topic 1: Biomarkers", True)]


class FakeChat:
    id = 321


class FakeUser:
    id = 654
    username = "tester"
    first_name = "Test"


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[tuple[str, bool]] = []

    async def reply_text(self, text: str, disable_web_page_preview: bool = False) -> None:
        self.replies.append((text, disable_web_page_preview))


class FakeUpdate:
    effective_chat = FakeChat()
    effective_user = FakeUser()

    def __init__(self, command_text: str) -> None:
        self.message = FakeMessage(command_text)


class FakeContext:
    def __init__(self, args: list[str]) -> None:
        self.args = args
