import asyncio
from datetime import UTC, date, datetime

import pytest
from prometheus_client import generate_latest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.jobs import delivery as delivery_job
from app.jobs.queues import get_delivery_queue
from app.models import (
    Paper,
    PaperSummary,
    TelegramDigestDelivery,
    TelegramDigestDeliveryItem,
    TelegramSubscriber,
    Topic,
    TopicPaper,
)
from app.services import summaries as summary_service
from app.services import telegram_deliveries as delivery_service

NOW = datetime(2026, 4, 29, 6, 30, tzinfo=UTC)


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[object, tuple]] = []

    def enqueue(self, func, *args):
        self.enqueued.append((func, args))
        return FakeJob(f"delivery-job-{len(self.enqueued)}")


class FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class FakeSender:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        if self.fail:
            raise RuntimeError("telegram unavailable")
        self.messages.append((chat_id, text))


class FakeEuropePMCClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, page_size: int = 25) -> dict:
        self.calls.append((query, page_size))
        record_id = query.replace(" ", "-")
        return {
            "resultList": {
                "result": [
                    {
                        "source": "MED",
                        "id": record_id,
                        "title": f"{query.title()} paper",
                        "abstractText": f"{query} tumor microenvironment",
                        "journalTitle": "BioWatch Journal",
                        "firstPublicationDate": "2026-04-28",
                        "doi": f"10.1000/{record_id}",
                    }
                ]
            }
        }


class FakeSearchClient:
    def __init__(self) -> None:
        self.indexed: list[list[Paper]] = []

    async def index_papers(self, papers: list[Paper]) -> None:
        self.indexed.append(papers)


class FakeSummaryQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[object, tuple]] = []

    def enqueue(self, func, *args):
        self.enqueued.append((func, args))
        return FakeJob(f"summary-job-{len(self.enqueued)}")


def test_delivery_tables_persist_items_and_enforce_idempotency(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            subscriber = TelegramSubscriber(telegram_chat_id=1)
            topic = Topic(name="Spatial", query="spatial", subscriber=subscriber)
            paper = Paper(source="europe_pmc", source_id="MED:1", title="Paper")
            session.add_all([subscriber, topic, paper])
            await session.flush()
            delivery = TelegramDigestDelivery(
                subscriber_id=subscriber.id,
                scheduled_for=NOW,
            )
            session.add(delivery)
            await session.flush()
            session.add(
                TelegramDigestDeliveryItem(
                    delivery_id=delivery.id,
                    paper_id=paper.id,
                    topic_id=topic.id,
                    position=1,
                )
            )
            await session.commit()

            duplicate = TelegramDigestDelivery(subscriber_id=subscriber.id, scheduled_for=NOW)
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

            persisted = await session.scalar(
                select(TelegramDigestDelivery).options(selectinload(TelegramDigestDelivery.items))
            )
            return {
                "status": persisted.status,
                "items": len(persisted.items),
            }

    assert asyncio.run(scenario()) == {"status": "queued", "items": 1}


def test_due_selection_skips_disabled_no_topic_and_existing_delivery(
    async_session_factory,
) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            due = TelegramSubscriber(telegram_chat_id=1)
            due_topic = Topic(name="Due", query="due", subscriber=due)
            disabled = TelegramSubscriber(telegram_chat_id=2, enabled=False)
            Topic(name="Disabled", query="disabled", subscriber=disabled)
            no_topic = TelegramSubscriber(telegram_chat_id=3)
            existing = TelegramSubscriber(telegram_chat_id=4)
            Topic(name="Existing", query="existing", subscriber=existing)
            session.add_all([due, due_topic, disabled, no_topic, existing])
            await session.flush()
            scheduled_for = delivery_service.scheduled_for_subscriber(existing, NOW)
            session.add(
                TelegramDigestDelivery(
                    subscriber_id=existing.id,
                    scheduled_for=scheduled_for,
                    status="failed",
                )
            )
            await session.commit()

            due_subscribers = await delivery_service.list_due_subscribers(session, NOW)
            return {
                "chat_ids": [subscriber.telegram_chat_id for subscriber, _ in due_subscribers],
                "scheduled_for": due_subscribers[0][1],
            }

    result = asyncio.run(scenario())
    assert result["chat_ids"] == [1]
    assert result["scheduled_for"] == datetime(2026, 4, 29, 6, 0, tzinfo=UTC)


def test_enqueue_due_deliveries_is_idempotent(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        fake_queue = FakeQueue()
        async with async_session_factory() as session:
            subscriber = TelegramSubscriber(telegram_chat_id=1)
            topic = Topic(name="Due", query="due", subscriber=subscriber)
            session.add_all([subscriber, topic])
            await session.commit()

            first = await delivery_service.enqueue_due_morning_deliveries(
                session,
                fake_queue,
                lambda delivery_id: delivery_id,
                now=NOW,
            )
            second = await delivery_service.enqueue_due_morning_deliveries(
                session,
                fake_queue,
                lambda delivery_id: delivery_id,
                now=NOW,
            )
            deliveries = list(await session.scalars(select(TelegramDigestDelivery)))
            return {
                "first": first.deliveries_enqueued,
                "second": second.deliveries_enqueued,
                "delivery_count": len(deliveries),
                "queue_count": len(fake_queue.enqueued),
            }

    assert asyncio.run(scenario()) == {
        "first": 1,
        "second": 0,
        "delivery_count": 1,
        "queue_count": 1,
    }


def test_process_delivery_ingests_sends_and_respects_article_count(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        sender = FakeSender()
        europe_pmc = FakeEuropePMCClient()
        search_client = FakeSearchClient()
        async with async_session_factory() as session:
            subscriber = TelegramSubscriber(telegram_chat_id=42, article_count=1)
            high = Topic(
                name="Spatial",
                query="spatial transcriptomics",
                subscriber=subscriber,
                priority=10,
                max_papers_per_run=7,
            )
            low = Topic(name="Checkpoint", query="checkpoint inhibitor", subscriber=subscriber)
            session.add_all([subscriber, high, low])
            await session.flush()
            delivery = await delivery_service.create_queued_delivery(
                session,
                subscriber,
                delivery_service.scheduled_for_subscriber(subscriber, NOW),
            )

            processed = await delivery_service.process_morning_delivery(
                session,
                delivery.id,
                sender,
                europe_pmc_client=europe_pmc,
                paper_search_client=search_client,
                now=NOW,
            )
            return {
                "status": processed.status,
                "item_count": len(processed.items),
                "sent_at": processed.sent_at,
                "messages": sender.messages,
                "europe_calls": europe_pmc.calls,
                "indexed_batches": len(search_client.indexed),
            }

    result = asyncio.run(scenario())
    assert result["status"] == "sent"
    assert result["item_count"] == 1
    assert result["sent_at"] == NOW.replace(tzinfo=None)
    assert result["messages"][0][0] == 42
    assert "BioWatch Morning Brief — 29 Apr" in result["messages"][0][1]
    assert "Topic: Spatial" in result["messages"][0][1]
    assert "Why shown: matched" in result["messages"][0][1]
    assert result["europe_calls"][0] == ("spatial transcriptomics", 7)
    assert result["indexed_batches"] == 2


def test_failed_telegram_send_marks_delivery_failed(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            subscriber = TelegramSubscriber(telegram_chat_id=42)
            topic = Topic(
                name="Spatial",
                query="spatial",
                subscriber=subscriber,
                last_ingested_at=NOW,
            )
            paper = Paper(source="europe_pmc", source_id="MED:1", title="Spatial paper")
            session.add_all([subscriber, topic, paper])
            await session.flush()
            session.add(TopicPaper(topic_id=topic.id, paper_id=paper.id, matched_at=NOW))
            delivery = await delivery_service.create_queued_delivery(
                session,
                subscriber,
                delivery_service.scheduled_for_subscriber(subscriber, NOW),
            )

            processed = await delivery_service.process_morning_delivery(
                session,
                delivery.id,
                FakeSender(fail=True),
                now=NOW,
            )
            return {"status": processed.status, "error": processed.error_message}

    result = asyncio.run(scenario())
    assert result["status"] == "failed"
    assert "telegram unavailable" in result["error"]


def test_delivery_enqueues_summaries_only_for_selected_items_and_falls_back(
    async_session_factory,
) -> None:
    async def scenario() -> dict[str, object]:
        sender = FakeSender()
        summary_queue = FakeSummaryQueue()
        async with async_session_factory() as session:
            subscriber = TelegramSubscriber(telegram_chat_id=42, article_count=1)
            high = Topic(
                name="Spatial",
                query="spatial",
                subscriber=subscriber,
                priority=10,
                last_ingested_at=NOW,
            )
            low = Topic(
                name="Checkpoint",
                query="checkpoint",
                subscriber=subscriber,
                priority=0,
                last_ingested_at=NOW,
            )
            paper_high = Paper(
                source="europe_pmc",
                source_id="MED:1",
                title="Spatial paper",
                abstract="Spatial abstract",
                publication_date=date(2026, 4, 29),
            )
            paper_low = Paper(
                source="europe_pmc",
                source_id="MED:2",
                title="Checkpoint paper",
                abstract="Checkpoint abstract",
                publication_date=date(2026, 4, 28),
            )
            session.add_all([subscriber, high, low, paper_high, paper_low])
            await session.flush()
            session.add_all(
                [
                    TopicPaper(topic_id=high.id, paper_id=paper_high.id, matched_at=NOW),
                    TopicPaper(topic_id=low.id, paper_id=paper_low.id, matched_at=NOW),
                ]
            )
            delivery = await delivery_service.create_queued_delivery(
                session,
                subscriber,
                delivery_service.scheduled_for_subscriber(subscriber, NOW),
            )

            processed = await delivery_service.process_morning_delivery(
                session,
                delivery.id,
                sender,
                summary_queue=summary_queue,
                summary_job_func=lambda summary_id: summary_id,
                summary_wait_timeout_seconds=0,
                now=NOW,
            )
            summaries = list(await session.scalars(select(PaperSummary)))
            return {
                "status": processed.status,
                "delivery_items": len(processed.items),
                "summary_jobs": len(summary_queue.enqueued),
                "summary_paper_ids": [summary.paper_id for summary in summaries],
                "message": sender.messages[0][1],
            }

    result = asyncio.run(scenario())
    assert result["status"] == "sent"
    assert result["delivery_items"] == 1
    assert result["summary_jobs"] == 1
    assert result["summary_paper_ids"] == [1]
    assert "AI summary:" not in result["message"]
    assert "Topic: Spatial" in result["message"]


def test_delivery_renders_cached_ai_summary(async_session_factory) -> None:
    async def scenario() -> str:
        sender = FakeSender()
        async with async_session_factory() as session:
            subscriber = TelegramSubscriber(telegram_chat_id=42, article_count=1)
            topic = Topic(
                name="Spatial",
                query="spatial",
                subscriber=subscriber,
                last_ingested_at=NOW,
            )
            paper = Paper(
                source="europe_pmc",
                source_id="MED:1",
                title="Spatial paper",
                abstract="Spatial transcriptomics abstract",
                publication_date=date(2026, 4, 29),
            )
            session.add_all([subscriber, topic, paper])
            await session.flush()
            session.add(TopicPaper(topic_id=topic.id, paper_id=paper.id, matched_at=NOW))
            session.add(
                PaperSummary(
                    paper_id=paper.id,
                    model="gpt-5-mini",
                    prompt_version="v1",
                    input_hash=summary_service.paper_summary_input_hash(paper),
                    summary_short="This paper maps spatial signals in tumors.",
                    key_points=["Profiles tumor regions", "Links context to biology"],
                    limitations="Abstract-only summary.",
                    why_it_matters="It helps prioritize spatial oncology reading.",
                    status="completed",
                )
            )
            delivery = await delivery_service.create_queued_delivery(
                session,
                subscriber,
                delivery_service.scheduled_for_subscriber(subscriber, NOW),
            )

            await delivery_service.process_morning_delivery(
                session,
                delivery.id,
                sender,
                now=NOW,
            )
            return sender.messages[0][1]

    message = asyncio.run(scenario())
    assert "AI summary:" in message
    assert "This paper maps spatial signals in tumors." in message
    assert "- Profiles tumor regions" in message
    assert "Why it matters:" in message


def test_render_morning_brief_splits_long_messages() -> None:
    subscriber = TelegramSubscriber(telegram_chat_id=1)
    topic = Topic(id=1, name="Long Topic", query="long")
    items = [
        delivery_service.MorningBriefItem(
            paper=Paper(
                id=index,
                source="europe_pmc",
                source_id=f"MED:{index}",
                title=f"{index} " + ("A" * 1800),
                journal="Long Journal",
                publication_date=date(2026, 4, 29),
            ),
            topic=topic,
            reason="matched long + recent publication",
            is_new=True,
            keyword_overlap=1,
            has_link=False,
        )
        for index in range(1, 4)
    ]

    messages = delivery_service.render_morning_brief(NOW, subscriber, items)

    assert len(messages) > 1
    assert all(len(message) <= delivery_service.MAX_TELEGRAM_MESSAGE_CHARS for message in messages)
    assert messages[1].startswith("BioWatch Morning Brief — 29 Apr (continued)")


def test_retry_failed_delivery_api_requeues_existing_delivery(
    client, async_session_factory
) -> None:
    fake_queue = FakeQueue()
    client.app.dependency_overrides[get_delivery_queue] = lambda: fake_queue

    async def setup() -> int:
        async with async_session_factory() as session:
            subscriber = TelegramSubscriber(telegram_chat_id=1)
            session.add(subscriber)
            await session.flush()
            delivery = TelegramDigestDelivery(
                subscriber_id=subscriber.id,
                scheduled_for=NOW,
                status="failed",
                error_message="telegram unavailable",
            )
            session.add(delivery)
            await session.commit()
            return delivery.id

    delivery_id = asyncio.run(setup())

    retry_response = client.post(f"/telegram/deliveries/{delivery_id}/retry")
    list_response = client.get("/telegram/deliveries")

    assert retry_response.status_code == 202
    assert retry_response.json()["status"] == "queued"
    assert retry_response.json()["error_message"] is None
    assert len(fake_queue.enqueued) == 1
    assert fake_queue.enqueued[0][1] == (delivery_id,)
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == delivery_id


def test_delivery_job_records_success_metrics(async_session_factory, monkeypatch) -> None:
    async def fake_process(session, delivery_id, sender, **kwargs):
        delivery = TelegramDigestDelivery(
            id=delivery_id,
            subscriber_id=123,
            scheduled_for=NOW,
            status="sent",
        )
        delivery.items = [
            TelegramDigestDeliveryItem(
                delivery_id=delivery_id,
                paper_id=1,
                topic_id=1,
                position=1,
            )
        ]
        return delivery

    monkeypatch.setattr(delivery_job, "SessionLocal", async_session_factory)
    monkeypatch.setattr(delivery_job, "TelegramBotSender", lambda token: FakeSender())
    monkeypatch.setattr(delivery_job, "process_morning_delivery", fake_process)

    asyncio.run(delivery_job._process_morning_delivery_job(99))
    metrics_text = generate_latest().decode()

    assert 'biowatch_telegram_delivery_attempts_total{status="sent"}' in metrics_text
    assert "biowatch_telegram_delivery_duration_seconds_bucket" in metrics_text
    assert "biowatch_telegram_delivery_items_sent_total" in metrics_text
