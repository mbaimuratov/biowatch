import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.sender import TelegramSender
from app.clients.europe_pmc import EuropePMCClient
from app.core.config import get_settings
from app.models import (
    Paper,
    PaperSummary,
    TelegramDigestDelivery,
    TelegramDigestDeliveryItem,
    TelegramDigestDeliveryMessage,
    TelegramSubscriber,
    Topic,
    TopicPaper,
)
from app.observability.metrics import PAPER_SUMMARY_CACHE_TOTAL
from app.search.client import PaperSearchClient
from app.services import digests as digest_service
from app.services import ingestion as ingestion_service
from app.services import subscriptions as subscription_service
from app.services import summaries as summary_service

DELIVERY_STATUS_QUEUED = "queued"
DELIVERY_STATUS_PREPARING = "preparing"
DELIVERY_STATUS_READY = "ready"
DELIVERY_STATUS_SEND_QUEUED = "send_queued"
DELIVERY_STATUS_SENDING = "sending"
DELIVERY_STATUS_SENT = "sent"
DELIVERY_STATUS_NOT_READY = "not_ready"
DELIVERY_STATUS_FAILED = "failed"
MAX_TELEGRAM_MESSAGE_CHARS = 3900
RECENT_MATCH_WINDOW = timedelta(hours=24)
logger = logging.getLogger(__name__)


class DeliveryNotFoundError(Exception):
    pass


class DeliveryRetryNotAllowedError(Exception):
    pass


@dataclass(frozen=True)
class DeliveryEnqueueResult:
    subscribers_checked: int
    deliveries_enqueued: int
    delivery_ids: list[int]


@dataclass(frozen=True)
class MorningBriefItem:
    paper: Paper
    topic: Topic
    reason: str
    is_new: bool
    keyword_overlap: int
    has_link: bool
    summary: PaperSummary | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


async def list_deliveries(session: AsyncSession) -> list[TelegramDigestDelivery]:
    result = await session.scalars(
        select(TelegramDigestDelivery)
        .options(
            selectinload(TelegramDigestDelivery.items),
            selectinload(TelegramDigestDelivery.messages),
        )
        .order_by(TelegramDigestDelivery.scheduled_for.desc(), TelegramDigestDelivery.id.desc())
    )
    return list(result)


async def enqueue_due_morning_deliveries(
    session: AsyncSession,
    delivery_queue: object,
    job_func: Callable[[int], int],
    now: datetime | None = None,
) -> DeliveryEnqueueResult:
    return await enqueue_due_morning_delivery_preparations(session, delivery_queue, job_func, now)


async def enqueue_due_morning_delivery_preparations(
    session: AsyncSession,
    delivery_queue: object,
    job_func: Callable[[int], int],
    now: datetime | None = None,
) -> DeliveryEnqueueResult:
    checked_at = _as_utc(now or utc_now())
    settings = get_settings()
    due_subscribers = await list_subscribers_due_for_preparation(
        session,
        checked_at,
        offset=timedelta(minutes=settings.delivery_prepare_offset_minutes),
    )
    deliveries: list[TelegramDigestDelivery] = []

    for subscriber, scheduled_for in due_subscribers:
        delivery = await create_queued_delivery(session, subscriber, scheduled_for)
        delivery_queue.enqueue(job_func, delivery.id)
        deliveries.append(delivery)

    return DeliveryEnqueueResult(
        subscribers_checked=await count_enabled_subscribers(session),
        deliveries_enqueued=len(deliveries),
        delivery_ids=[delivery.id for delivery in deliveries],
    )


async def enqueue_due_morning_delivery_sends(
    session: AsyncSession,
    delivery_queue: object,
    job_func: Callable[[int], int],
    now: datetime | None = None,
) -> DeliveryEnqueueResult:
    checked_at = _as_utc(now or utc_now())
    result = await session.scalars(
        select(TelegramDigestDelivery)
        .where(
            TelegramDigestDelivery.status == DELIVERY_STATUS_READY,
            TelegramDigestDelivery.scheduled_for <= checked_at,
        )
        .order_by(TelegramDigestDelivery.scheduled_for, TelegramDigestDelivery.id)
    )
    deliveries = list(result)
    for delivery in deliveries:
        delivery.status = DELIVERY_STATUS_SEND_QUEUED
        delivery.send_queued_at = checked_at
    await session.commit()
    for delivery in deliveries:
        delivery_queue.enqueue(job_func, delivery.id)

    await mark_unprepared_due_deliveries_not_ready(session, checked_at)
    return DeliveryEnqueueResult(
        subscribers_checked=await count_enabled_subscribers(session),
        deliveries_enqueued=len(deliveries),
        delivery_ids=[delivery.id for delivery in deliveries],
    )


async def list_due_subscribers(
    session: AsyncSession,
    now: datetime | None = None,
) -> list[tuple[TelegramSubscriber, datetime]]:
    checked_at = _as_utc(now or utc_now())
    result = await session.scalars(
        select(TelegramSubscriber)
        .where(TelegramSubscriber.enabled.is_(True))
        .options(selectinload(TelegramSubscriber.topics))
        .order_by(TelegramSubscriber.id)
    )

    due: list[tuple[TelegramSubscriber, datetime]] = []
    for subscriber in result:
        if not any(topic.enabled for topic in subscriber.topics):
            continue
        scheduled_for = scheduled_for_subscriber(subscriber, checked_at)
        if scheduled_for is None:
            continue
        existing_delivery = await get_delivery_for_schedule(
            session,
            subscriber.id,
            scheduled_for,
        )
        if existing_delivery is None:
            due.append((subscriber, scheduled_for))
    return due


async def list_subscribers_due_for_preparation(
    session: AsyncSession,
    now: datetime | None = None,
    offset: timedelta = timedelta(minutes=30),
) -> list[tuple[TelegramSubscriber, datetime]]:
    checked_at = _as_utc(now or utc_now())
    result = await session.scalars(
        select(TelegramSubscriber)
        .where(TelegramSubscriber.enabled.is_(True))
        .options(selectinload(TelegramSubscriber.topics))
        .order_by(TelegramSubscriber.id)
    )

    due: list[tuple[TelegramSubscriber, datetime]] = []
    for subscriber in result:
        if not any(topic.enabled for topic in subscriber.topics):
            continue
        scheduled_for = next_scheduled_for_subscriber(subscriber, checked_at)
        prepare_at = scheduled_for - offset
        if not (prepare_at <= checked_at < scheduled_for):
            continue
        existing_delivery = await get_delivery_for_schedule(
            session,
            subscriber.id,
            scheduled_for,
        )
        if existing_delivery is None:
            due.append((subscriber, scheduled_for))
    return due


async def mark_unprepared_due_deliveries_not_ready(
    session: AsyncSession,
    now: datetime | None = None,
) -> list[TelegramDigestDelivery]:
    checked_at = _as_utc(now or utc_now())
    result = await session.scalars(
        select(TelegramSubscriber)
        .where(TelegramSubscriber.enabled.is_(True))
        .options(selectinload(TelegramSubscriber.topics))
        .order_by(TelegramSubscriber.id)
    )
    marked: list[TelegramDigestDelivery] = []
    for subscriber in result:
        if not any(topic.enabled for topic in subscriber.topics):
            continue
        scheduled_for = scheduled_for_subscriber(subscriber, checked_at)
        if scheduled_for is None:
            continue
        delivery = await get_delivery_for_schedule(session, subscriber.id, scheduled_for)
        if delivery is None:
            delivery = TelegramDigestDelivery(
                subscriber_id=subscriber.id,
                scheduled_for=scheduled_for,
                status=DELIVERY_STATUS_NOT_READY,
                error_message="Prepared morning brief was not ready at send time",
            )
            session.add(delivery)
            marked.append(delivery)
            continue
        if delivery.status in {
            DELIVERY_STATUS_QUEUED,
            DELIVERY_STATUS_PREPARING,
        }:
            delivery.status = DELIVERY_STATUS_NOT_READY
            delivery.error_message = "Prepared morning brief was not ready at send time"
            marked.append(delivery)
    if marked:
        await session.commit()
    return marked


async def count_enabled_subscribers(session: AsyncSession) -> int:
    return len(
        list(
            await session.scalars(
                select(TelegramSubscriber).where(TelegramSubscriber.enabled.is_(True))
            )
        )
    )


def scheduled_for_subscriber(
    subscriber: TelegramSubscriber,
    now: datetime | None = None,
) -> datetime | None:
    checked_at = _as_utc(now or utc_now())
    timezone = _subscriber_timezone(subscriber)
    local_now = checked_at.astimezone(timezone)
    local_scheduled = datetime.combine(
        local_now.date(),
        subscriber.morning_send_time,
        tzinfo=timezone,
    )
    if local_now < local_scheduled:
        return None
    return local_scheduled.astimezone(UTC)


def next_scheduled_for_subscriber(
    subscriber: TelegramSubscriber,
    now: datetime | None = None,
) -> datetime:
    checked_at = _as_utc(now or utc_now())
    timezone = _subscriber_timezone(subscriber)
    local_now = checked_at.astimezone(timezone)
    local_scheduled = datetime.combine(
        local_now.date(),
        subscriber.morning_send_time,
        tzinfo=timezone,
    )
    if local_now >= local_scheduled:
        local_scheduled = local_scheduled + timedelta(days=1)
    return local_scheduled.astimezone(UTC)


async def get_delivery_for_schedule(
    session: AsyncSession,
    subscriber_id: int,
    scheduled_for: datetime,
) -> TelegramDigestDelivery | None:
    return await session.scalar(
        select(TelegramDigestDelivery).where(
            TelegramDigestDelivery.subscriber_id == subscriber_id,
            TelegramDigestDelivery.scheduled_for == scheduled_for,
        )
    )


async def create_queued_delivery(
    session: AsyncSession,
    subscriber: TelegramSubscriber,
    scheduled_for: datetime,
) -> TelegramDigestDelivery:
    delivery = TelegramDigestDelivery(
        subscriber_id=subscriber.id,
        scheduled_for=scheduled_for,
        status=DELIVERY_STATUS_QUEUED,
    )
    session.add(delivery)
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def retry_failed_delivery(
    session: AsyncSession,
    delivery_id: int,
    delivery_queue: object,
    job_func: Callable[[int], int],
) -> TelegramDigestDelivery:
    delivery = await get_delivery(session, delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError
    if delivery.status != DELIVERY_STATUS_FAILED:
        raise DeliveryRetryNotAllowedError
    if not delivery.messages:
        raise DeliveryRetryNotAllowedError

    delivery.status = DELIVERY_STATUS_SEND_QUEUED
    delivery.error_message = None
    delivery.sent_at = None
    delivery.send_queued_at = utc_now()
    await session.commit()
    delivery_queue.enqueue(job_func, delivery.id)
    refreshed = await get_delivery(session, delivery.id)
    if refreshed is None:
        raise DeliveryNotFoundError
    return refreshed


async def retry_not_ready_delivery_preparation(
    session: AsyncSession,
    delivery_id: int,
    delivery_queue: object,
    job_func: Callable[[int], int],
) -> TelegramDigestDelivery:
    delivery = await get_delivery(session, delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError
    if delivery.status != DELIVERY_STATUS_NOT_READY:
        raise DeliveryRetryNotAllowedError

    delivery.status = DELIVERY_STATUS_QUEUED
    delivery.error_message = None
    delivery.preparation_started_at = None
    delivery.prepared_at = None
    delivery.send_queued_at = None
    delivery.sent_at = None
    await _clear_prepared_delivery(session, delivery.id)
    await session.commit()
    delivery_queue.enqueue(job_func, delivery.id)
    refreshed = await get_delivery(session, delivery.id)
    if refreshed is None:
        raise DeliveryNotFoundError
    return refreshed


async def get_delivery(
    session: AsyncSession,
    delivery_id: int,
) -> TelegramDigestDelivery | None:
    return await session.scalar(
        select(TelegramDigestDelivery)
        .where(TelegramDigestDelivery.id == delivery_id)
        .options(
            selectinload(TelegramDigestDelivery.items),
            selectinload(TelegramDigestDelivery.messages),
        )
    )


async def prepare_morning_delivery(
    session: AsyncSession,
    delivery_id: int,
    europe_pmc_client: EuropePMCClient | None = None,
    paper_search_client: PaperSearchClient | None = None,
    summary_queue: object | None = None,
    summary_job_func: Callable[[int], int] | None = None,
    summary_wait_timeout_seconds: float | None = None,
    now: datetime | None = None,
) -> TelegramDigestDelivery:
    processed_at = _as_utc(now or utc_now())
    delivery = await _load_delivery_for_processing(session, delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError(f"Telegram digest delivery {delivery_id} not found")
    if delivery.status in {
        DELIVERY_STATUS_READY,
        DELIVERY_STATUS_SEND_QUEUED,
        DELIVERY_STATUS_SENDING,
        DELIVERY_STATUS_SENT,
    }:
        return delivery
    if delivery.status == DELIVERY_STATUS_NOT_READY:
        return delivery

    delivery.status = DELIVERY_STATUS_PREPARING
    delivery.error_message = None
    delivery.preparation_started_at = processed_at
    delivery.prepared_at = None
    delivery.send_queued_at = None
    delivery.sent_at = None
    await _clear_prepared_delivery(session, delivery.id)
    await session.commit()

    try:
        subscriber = delivery.subscriber
        if not subscriber.enabled:
            raise RuntimeError("Subscriber is disabled")

        await _ingest_due_subscriber_topics(
            session,
            subscriber,
            processed_at,
            europe_pmc_client=europe_pmc_client,
            paper_search_client=paper_search_client,
        )
        digest = await digest_service.generate_today_digest(session, now=processed_at)
        selected_items = await select_morning_brief_items(session, subscriber, processed_at)
        selected_items = await attach_summaries_to_items(
            session,
            selected_items,
            summary_queue=summary_queue,
            summary_job_func=summary_job_func,
            wait_timeout_seconds=_summary_wait_timeout_for_delivery(
                delivery,
                processed_at,
                summary_wait_timeout_seconds,
            ),
        )
        missing_summaries = [item.paper.id for item in selected_items if item.summary is None]
        if missing_summaries:
            delivery = await session.get(TelegramDigestDelivery, delivery_id)
            if delivery is None:
                raise DeliveryNotFoundError(f"Telegram digest delivery {delivery_id} not found")
            delivery.status = DELIVERY_STATUS_NOT_READY
            delivery.error_message = (
                "AI summaries were not ready for selected papers: "
                + ", ".join(str(paper_id) for paper_id in missing_summaries)
            )
            await session.commit()
            await session.refresh(delivery)
            return delivery

        delivery = await _load_delivery_for_processing(session, delivery.id)
        if delivery is None:
            raise DeliveryNotFoundError(f"Telegram digest delivery {delivery_id} not found")
        delivery.digest_id = digest.id
        for position, item in enumerate(selected_items, start=1):
            session.add(
                TelegramDigestDeliveryItem(
                    delivery_id=delivery.id,
                    paper_id=item.paper.id,
                    topic_id=item.topic.id,
                    summary_id=item.summary.id if item.summary is not None else None,
                    position=position,
                )
            )
        messages = render_morning_brief(
            scheduled_for=delivery.scheduled_for,
            subscriber=subscriber,
            items=selected_items,
        )
        for position, message in enumerate(messages, start=1):
            session.add(
                TelegramDigestDeliveryMessage(
                    delivery_id=delivery.id,
                    position=position,
                    text=message,
                )
            )
        delivery.status = DELIVERY_STATUS_READY
        delivery.prepared_at = processed_at
        delivery.error_message = None
        await session.commit()
        refreshed = await _load_delivery_for_processing(session, delivery.id)
        if refreshed is None:
            raise DeliveryNotFoundError(f"Telegram digest delivery {delivery_id} not found")
        return refreshed
    except Exception as exc:
        delivery = await session.get(TelegramDigestDelivery, delivery_id)
        if delivery is None:
            raise
        delivery.status = DELIVERY_STATUS_FAILED
        delivery.error_message = str(exc)
        delivery.sent_at = None
        await session.commit()
        await session.refresh(delivery)
        logger.exception(
            "Telegram morning delivery preparation failed",
            extra={
                "delivery_id": delivery.id,
                "subscriber_id": delivery.subscriber_id,
                "scheduled_for": delivery.scheduled_for.isoformat(),
                "status": delivery.status,
            },
        )
        return delivery


async def send_prepared_morning_delivery(
    session: AsyncSession,
    delivery_id: int,
    sender: TelegramSender,
    now: datetime | None = None,
) -> TelegramDigestDelivery:
    sent_at = _as_utc(now or utc_now())
    delivery = await _load_delivery_for_processing(session, delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError(f"Telegram digest delivery {delivery_id} not found")
    if delivery.status == DELIVERY_STATUS_SENT:
        return delivery
    if delivery.status not in {DELIVERY_STATUS_READY, DELIVERY_STATUS_SEND_QUEUED}:
        delivery.status = DELIVERY_STATUS_NOT_READY
        delivery.error_message = "Prepared morning brief is not ready to send"
        await session.commit()
        await session.refresh(delivery)
        return delivery
    if not delivery.messages:
        delivery.status = DELIVERY_STATUS_NOT_READY
        delivery.error_message = "Prepared morning brief has no message chunks"
        await session.commit()
        await session.refresh(delivery)
        return delivery

    delivery.status = DELIVERY_STATUS_SENDING
    delivery.error_message = None
    await session.commit()

    try:
        subscriber = delivery.subscriber
        if not subscriber.enabled:
            raise RuntimeError("Subscriber is disabled")
        for message in delivery.messages:
            await sender.send_message(subscriber.telegram_chat_id, message.text)

        delivery = await _load_delivery_for_processing(session, delivery.id)
        if delivery is None:
            raise DeliveryNotFoundError(f"Telegram digest delivery {delivery_id} not found")
        delivery.status = DELIVERY_STATUS_SENT
        delivery.sent_at = sent_at
        delivery.error_message = None
        await session.commit()
        delivery = await _load_delivery_for_processing(session, delivery.id)
        if delivery is None:
            raise DeliveryNotFoundError(f"Telegram digest delivery {delivery_id} not found")
        logger.info(
            "Telegram morning delivery sent",
            extra={
                "delivery_id": delivery.id,
                "subscriber_id": delivery.subscriber_id,
                "scheduled_for": delivery.scheduled_for.isoformat(),
                "status": delivery.status,
                "item_count": len(delivery.items),
            },
        )
        return delivery
    except Exception as exc:
        delivery = await session.get(TelegramDigestDelivery, delivery_id)
        if delivery is None:
            raise
        delivery.status = DELIVERY_STATUS_FAILED
        delivery.error_message = str(exc)
        delivery.sent_at = None
        await session.commit()
        await session.refresh(delivery)
        logger.exception(
            "Telegram morning delivery failed",
            extra={
                "delivery_id": delivery.id,
                "subscriber_id": delivery.subscriber_id,
                "scheduled_for": delivery.scheduled_for.isoformat(),
                "status": delivery.status,
                "item_count": 0,
            },
        )
        return delivery


async def process_morning_delivery(
    session: AsyncSession,
    delivery_id: int,
    sender: TelegramSender,
    europe_pmc_client: EuropePMCClient | None = None,
    paper_search_client: PaperSearchClient | None = None,
    summary_queue: object | None = None,
    summary_job_func: Callable[[int], int] | None = None,
    summary_wait_timeout_seconds: float | None = None,
    now: datetime | None = None,
) -> TelegramDigestDelivery:
    prepared = await prepare_morning_delivery(
        session,
        delivery_id,
        europe_pmc_client=europe_pmc_client,
        paper_search_client=paper_search_client,
        summary_queue=summary_queue,
        summary_job_func=summary_job_func,
        summary_wait_timeout_seconds=summary_wait_timeout_seconds,
        now=now,
    )
    if prepared.status != DELIVERY_STATUS_READY:
        return prepared
    return await send_prepared_morning_delivery(session, delivery_id, sender, now=now)


async def select_morning_brief_items(
    session: AsyncSession,
    subscriber: TelegramSubscriber,
    now: datetime | None = None,
) -> list[MorningBriefItem]:
    selected_at = _as_utc(now or utc_now())
    seen_pairs = await _seen_paper_topic_pairs(session, subscriber.id)
    result = await session.scalars(
        select(TopicPaper)
        .join(TopicPaper.paper)
        .join(TopicPaper.topic)
        .where(
            Topic.subscriber_id == subscriber.id,
            Topic.enabled.is_(True),
            TopicPaper.matched_at >= selected_at - RECENT_MATCH_WINDOW,
        )
        .options(selectinload(TopicPaper.paper), selectinload(TopicPaper.topic))
    )

    items = [
        _brief_item(match, seen_pairs)
        for match in result
        if match.paper is not None and match.topic is not None
    ]
    items.sort(key=_brief_sort_key)
    return items[: subscriber.article_count]


async def attach_summaries_to_items(
    session: AsyncSession,
    items: list[MorningBriefItem],
    *,
    summary_queue: object | None = None,
    summary_job_func: Callable[[int], int] | None = None,
    wait_timeout_seconds: float | None = None,
) -> list[MorningBriefItem]:
    if not items:
        return items

    settings = get_settings()
    preparation = await summary_service.prepare_summaries_for_papers(
        session,
        [item.paper for item in items],
        model=settings.llm_model,
        prompt_version=settings.summary_prompt_version,
        summary_queue=summary_queue,
        job_func=summary_job_func,
        wait_timeout_seconds=(
            settings.summary_wait_timeout_seconds
            if wait_timeout_seconds is None
            else wait_timeout_seconds
        ),
    )
    PAPER_SUMMARY_CACHE_TOTAL.labels(result="hit").inc(preparation.cache_hits)
    PAPER_SUMMARY_CACHE_TOTAL.labels(result="miss").inc(preparation.cache_misses)
    return [
        replace(item, summary=preparation.summaries_by_paper_id.get(item.paper.id))
        for item in items
    ]


def render_morning_brief(
    scheduled_for: datetime,
    subscriber: TelegramSubscriber,
    items: list[MorningBriefItem],
) -> list[str]:
    local_date = _as_utc(scheduled_for).astimezone(_subscriber_timezone(subscriber)).date()
    header = f"BioWatch Morning Brief — {local_date.strftime('%d %b')}"
    if not items:
        return [f"{header}\n\nNo recent papers matched your enabled topics yet."]

    chunks: list[str] = []
    current = header
    for position, item in enumerate(items, start=1):
        block = _render_item(position, item)
        if len(current) + len(block) + 2 > MAX_TELEGRAM_MESSAGE_CHARS and current != header:
            chunks.append(current)
            current = f"{header} (continued)"
        current = f"{current}\n\n{block}"
    chunks.append(current)
    return chunks


async def _load_delivery_for_processing(
    session: AsyncSession,
    delivery_id: int,
) -> TelegramDigestDelivery | None:
    return await session.scalar(
        select(TelegramDigestDelivery)
        .where(TelegramDigestDelivery.id == delivery_id)
        .execution_options(populate_existing=True)
        .options(
            selectinload(TelegramDigestDelivery.subscriber).selectinload(TelegramSubscriber.topics),
            selectinload(TelegramDigestDelivery.items),
            selectinload(TelegramDigestDelivery.messages),
        )
    )


async def _clear_prepared_delivery(session: AsyncSession, delivery_id: int) -> None:
    await session.execute(
        delete(TelegramDigestDeliveryItem).where(
            TelegramDigestDeliveryItem.delivery_id == delivery_id
        )
    )
    await session.execute(
        delete(TelegramDigestDeliveryMessage).where(
            TelegramDigestDeliveryMessage.delivery_id == delivery_id
        )
    )


def _summary_wait_timeout_for_delivery(
    delivery: TelegramDigestDelivery,
    now: datetime,
    requested_timeout: float | None,
) -> float:
    settings = get_settings()
    configured_timeout = (
        settings.delivery_prepare_summary_timeout_seconds
        if requested_timeout is None
        else requested_timeout
    )
    seconds_until_send = max(0.0, (_as_utc(delivery.scheduled_for) - now).total_seconds() - 5)
    return min(configured_timeout, seconds_until_send)


async def _ingest_due_subscriber_topics(
    session: AsyncSession,
    subscriber: TelegramSubscriber,
    now: datetime,
    europe_pmc_client: EuropePMCClient | None = None,
    paper_search_client: PaperSearchClient | None = None,
) -> None:
    for topic in sorted(subscriber.topics, key=lambda subscriber_topic: subscriber_topic.id):
        if topic.subscriber_id != subscriber.id:
            continue
        if not subscription_service.is_topic_due(topic, now):
            continue
        run = await ingestion_service.create_queued_run(session, topic)
        topic.last_ingested_at = now
        await session.commit()
        await ingestion_service.process_ingestion_run(
            session,
            run.id,
            europe_pmc_client=europe_pmc_client,
            paper_search_client=paper_search_client,
        )


async def _seen_paper_topic_pairs(
    session: AsyncSession,
    subscriber_id: int,
) -> set[tuple[int, int]]:
    rows = await session.execute(
        select(TelegramDigestDeliveryItem.paper_id, TelegramDigestDeliveryItem.topic_id)
        .join(TelegramDigestDeliveryItem.delivery)
        .where(
            TelegramDigestDelivery.subscriber_id == subscriber_id,
            TelegramDigestDelivery.status == DELIVERY_STATUS_SENT,
        )
    )
    return {(paper_id, topic_id) for paper_id, topic_id in rows}


def _brief_item(
    match: TopicPaper,
    seen_pairs: set[tuple[int, int]],
) -> MorningBriefItem:
    paper = match.paper
    topic = match.topic
    overlap_terms = _overlap_terms(topic.query, f"{paper.title} {paper.abstract or ''}")
    return MorningBriefItem(
        paper=paper,
        topic=topic,
        reason=_reason(topic, overlap_terms),
        is_new=(paper.id, topic.id) not in seen_pairs,
        keyword_overlap=len(overlap_terms),
        has_link=bool(paper.url or paper.doi),
    )


def _brief_sort_key(item: MorningBriefItem) -> tuple:
    publication_date = item.paper.publication_date or date.min
    return (
        not item.is_new,
        -publication_date.toordinal(),
        -item.topic.priority,
        -item.keyword_overlap,
        not item.has_link,
        -item.paper.created_at.timestamp(),
        -item.paper.id,
    )


def _render_item(position: int, item: MorningBriefItem) -> str:
    paper = item.paper
    journal_date = _journal_date(paper)
    link = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else "Not available")
    lines = [
        f"{position}. {paper.title}",
        f"Topic: {item.topic.name}",
        f"Why shown: {item.reason}",
        f"Journal/date: {journal_date}",
        f"Link: {link}",
    ]
    if item.summary is not None and item.summary.status == summary_service.SUMMARY_STATUS_COMPLETED:
        lines.extend(
            [
                "",
                "AI summary:",
                item.summary.summary_short or "",
                "",
                "Key points:",
            ]
        )
        lines.extend(f"- {point}" for point in item.summary.normalized_key_points())
        lines.extend(["", "Why it matters:", item.summary.why_it_matters or ""])
    return "\n".join(lines)


def _journal_date(paper: Paper) -> str:
    journal = paper.journal or "Unknown journal"
    publication_date = (
        paper.publication_date.isoformat() if paper.publication_date else "Unknown date"
    )
    return f"{journal} / {publication_date}"


def _reason(topic: Topic, overlap_terms: list[str]) -> str:
    if overlap_terms:
        return f"matched {', '.join(overlap_terms[:3])} + recent publication"
    return f"matched topic: {topic.name} + recent publication"


def _overlap_terms(query: str, text: str) -> list[str]:
    query_terms = set(_terms(query))
    text_terms = set(_terms(text))
    return sorted(query_terms & text_terms)


def _terms(value: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 2]


def _subscriber_timezone(subscriber: TelegramSubscriber) -> ZoneInfo:
    try:
        return ZoneInfo(subscriber.timezone or "Europe/Rome")
    except ZoneInfoNotFoundError:
        logger.warning(
            "Invalid subscriber timezone; falling back to UTC",
            extra={"subscriber_id": subscriber.id, "timezone": subscriber.timezone},
        )
        return ZoneInfo("UTC")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
