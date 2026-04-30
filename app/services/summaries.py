from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import PaperSummaryLLMClient
from app.models import Paper, PaperSummary

SUMMARY_STATUS_QUEUED = "queued"
SUMMARY_STATUS_COMPLETED = "completed"
SUMMARY_STATUS_FAILED = "failed"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummaryPreparationResult:
    summaries_by_paper_id: dict[int, PaperSummary]
    enqueued_summary_ids: list[int]
    cache_hits: int
    cache_misses: int


def utc_now() -> datetime:
    return datetime.now(UTC)


def paper_summary_input(paper: Paper) -> str:
    title = " ".join(paper.title.split())
    abstract = " ".join((paper.abstract or "").split())
    return f"Title: {title}\n\nAbstract: {abstract}"


def paper_summary_input_hash(paper: Paper) -> str:
    return hashlib.sha256(paper_summary_input(paper).encode("utf-8")).hexdigest()


async def get_completed_summary_for_paper(
    session: AsyncSession,
    paper: Paper,
    prompt_version: str,
) -> PaperSummary | None:
    return await session.scalar(
        select(PaperSummary).where(
            PaperSummary.paper_id == paper.id,
            PaperSummary.input_hash == paper_summary_input_hash(paper),
            PaperSummary.prompt_version == prompt_version,
            PaperSummary.status == SUMMARY_STATUS_COMPLETED,
        )
    )


async def prepare_summaries_for_papers(
    session: AsyncSession,
    papers: list[Paper],
    *,
    model: str,
    prompt_version: str,
    summary_queue: object | None = None,
    job_func: Callable[[int], int] | None = None,
    wait_timeout_seconds: float = 0.0,
) -> SummaryPreparationResult:
    summaries_by_paper_id: dict[int, PaperSummary] = {}
    enqueued_summary_ids: list[int] = []
    cache_hits = 0
    cache_misses = 0

    unique_papers = {paper.id: paper for paper in papers if paper.id is not None}
    for paper in unique_papers.values():
        completed = await get_completed_summary_for_paper(session, paper, prompt_version)
        if completed is not None:
            summaries_by_paper_id[paper.id] = completed
            cache_hits += 1
            continue

        cache_misses += 1
        if summary_queue is None or job_func is None:
            continue

        summary, should_enqueue = await get_or_create_summary_placeholder(
            session,
            paper,
            model=model,
            prompt_version=prompt_version,
        )
        if should_enqueue:
            summary_queue.enqueue(job_func, summary.id)
            enqueued_summary_ids.append(summary.id)

    if enqueued_summary_ids and wait_timeout_seconds > 0:
        waited = await wait_for_summaries(session, enqueued_summary_ids, wait_timeout_seconds)
        for summary in waited:
            if summary.status == SUMMARY_STATUS_COMPLETED:
                summaries_by_paper_id[summary.paper_id] = summary

    logger.info(
        "Prepared paper summaries for Telegram brief",
        extra={
            "paper_count": len(unique_papers),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "enqueued_count": len(enqueued_summary_ids),
        },
    )
    return SummaryPreparationResult(
        summaries_by_paper_id=summaries_by_paper_id,
        enqueued_summary_ids=enqueued_summary_ids,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
    )


async def get_or_create_summary_placeholder(
    session: AsyncSession,
    paper: Paper,
    *,
    model: str,
    prompt_version: str,
) -> tuple[PaperSummary, bool]:
    input_hash = paper_summary_input_hash(paper)
    summary = await session.scalar(
        select(PaperSummary).where(
            PaperSummary.paper_id == paper.id,
            PaperSummary.input_hash == input_hash,
            PaperSummary.prompt_version == prompt_version,
        )
    )
    should_enqueue = False
    if summary is None:
        summary = PaperSummary(
            paper_id=paper.id,
            model=model,
            prompt_version=prompt_version,
            input_hash=input_hash,
            status=SUMMARY_STATUS_QUEUED,
        )
        session.add(summary)
        should_enqueue = True
    elif summary.status == SUMMARY_STATUS_FAILED:
        summary.model = model
        summary.status = SUMMARY_STATUS_QUEUED
        summary.error_message = None
        summary.summary_short = None
        summary.key_points = None
        summary.limitations = None
        summary.why_it_matters = None
        summary.generated_at = None
        should_enqueue = True
    await session.commit()
    await session.refresh(summary)
    return summary, should_enqueue


async def wait_for_summaries(
    session: AsyncSession,
    summary_ids: list[int],
    timeout_seconds: float,
) -> list[PaperSummary]:
    deadline = time.monotonic() + timeout_seconds
    summaries: list[PaperSummary] = []
    while True:
        result = await session.scalars(
            select(PaperSummary)
            .where(PaperSummary.id.in_(summary_ids))
            .execution_options(populate_existing=True)
        )
        summaries = list(result)
        if all(summary.status != SUMMARY_STATUS_QUEUED for summary in summaries):
            return summaries
        if time.monotonic() >= deadline:
            return summaries
        await asyncio.sleep(0.2)


async def generate_summary(
    session: AsyncSession,
    summary_id: int,
    llm_client: PaperSummaryLLMClient,
) -> PaperSummary:
    summary = await session.get(PaperSummary, summary_id)
    if summary is None:
        raise ValueError(f"Paper summary {summary_id} not found")

    paper = await session.get(Paper, summary.paper_id)
    if paper is None:
        summary.status = SUMMARY_STATUS_FAILED
        summary.error_message = "Paper not found"
        await session.commit()
        await session.refresh(summary)
        return summary

    expected_hash = paper_summary_input_hash(paper)
    if summary.input_hash != expected_hash:
        summary.status = SUMMARY_STATUS_FAILED
        summary.error_message = "Paper content changed before summary generation"
        await session.commit()
        await session.refresh(summary)
        return summary

    if not paper.abstract or not paper.abstract.strip():
        summary.status = SUMMARY_STATUS_FAILED
        summary.error_message = "Paper abstract is missing"
        summary.generated_at = utc_now()
        await session.commit()
        await session.refresh(summary)
        return summary

    try:
        result = await llm_client.summarize_paper(paper.title, paper.abstract)
        summary.summary_short = result.summary_short
        summary.key_points = result.key_points
        summary.limitations = result.limitations
        summary.why_it_matters = result.why_it_matters
        summary.status = SUMMARY_STATUS_COMPLETED
        summary.error_message = None
        summary.generated_at = utc_now()
    except Exception as exc:
        summary.status = SUMMARY_STATUS_FAILED
        summary.error_message = str(exc)
        summary.generated_at = utc_now()
        logger.exception(
            "Paper summary generation failed",
            extra={
                "summary_id": summary.id,
                "paper_id": summary.paper_id,
                "model": summary.model,
                "prompt_version": summary.prompt_version,
            },
        )

    await session.commit()
    await session.refresh(summary)
    return summary
