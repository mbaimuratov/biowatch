import asyncio

import pytest
from prometheus_client import generate_latest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.jobs import summaries as summary_job
from app.llm.client import PaperSummaryResult
from app.models import Paper, PaperSummary
from app.services import summaries as summary_service


class FakeLLMClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def summarize_paper(self, title: str, abstract: str) -> PaperSummaryResult:
        self.calls.append((title, abstract))
        if self.fail:
            raise RuntimeError("llm unavailable")
        return PaperSummaryResult(
            summary_short="A concise takeaway.",
            key_points=["Point one", "Point two"],
            limitations="Abstract-only summary.",
            why_it_matters="It helps prioritize the paper.",
        )


def test_paper_summary_uniqueness_and_input_hash(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            paper = Paper(
                source="europe_pmc",
                source_id="MED:1",
                title="Spatial paper",
                abstract="Spatial transcriptomics abstract",
            )
            session.add(paper)
            await session.flush()
            paper_id = paper.id
            input_hash = summary_service.paper_summary_input_hash(paper)
            session.add(
                PaperSummary(
                    paper_id=paper.id,
                    model="gpt-5-mini",
                    prompt_version="v1",
                    input_hash=input_hash,
                    status="completed",
                )
            )
            await session.commit()

            duplicate = PaperSummary(
                paper_id=paper.id,
                model="gpt-5-mini",
                prompt_version="v1",
                input_hash=input_hash,
            )
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

            changed_hash = summary_service.paper_summary_input_hash(
                Paper(
                    id=paper_id,
                    source="europe_pmc",
                    source_id="MED:1",
                    title="Spatial paper",
                    abstract="Updated abstract",
                )
            )
            session.add(
                PaperSummary(
                    paper_id=paper_id,
                    model="gpt-5-mini",
                    prompt_version="v1",
                    input_hash=changed_hash,
                )
            )
            await session.commit()
            count = len(list(await session.scalars(select(PaperSummary))))
            return {"hash_changed": changed_hash != input_hash, "count": count}

    assert asyncio.run(scenario()) == {"hash_changed": True, "count": 2}


def test_generate_summary_stores_structured_fields(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            paper = Paper(
                source="europe_pmc",
                source_id="MED:1",
                title="Spatial paper",
                abstract="Spatial transcriptomics abstract",
            )
            session.add(paper)
            await session.flush()
            summary, _ = await summary_service.get_or_create_summary_placeholder(
                session,
                paper,
                model="gpt-5-mini",
                prompt_version="v1",
            )

            llm = FakeLLMClient()
            completed = await summary_service.generate_summary(session, summary.id, llm)
            return {
                "status": completed.status,
                "summary": completed.summary_short,
                "points": completed.key_points,
                "calls": llm.calls,
            }

    result = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert result["summary"] == "A concise takeaway."
    assert result["points"] == ["Point one", "Point two"]
    assert len(result["calls"]) == 1


def test_prepare_summaries_cache_hit_skips_queue(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            paper = Paper(
                source="europe_pmc",
                source_id="MED:1",
                title="Spatial paper",
                abstract="Spatial transcriptomics abstract",
            )
            session.add(paper)
            await session.flush()
            session.add(
                PaperSummary(
                    paper_id=paper.id,
                    model="gpt-5-mini",
                    prompt_version="v1",
                    input_hash=summary_service.paper_summary_input_hash(paper),
                    summary_short="Cached",
                    key_points=["Cached point"],
                    limitations="None",
                    why_it_matters="Cached reason",
                    status="completed",
                )
            )
            await session.commit()

            result = await summary_service.prepare_summaries_for_papers(
                session,
                [paper],
                model="gpt-5-mini",
                prompt_version="v1",
            )
            return {
                "hits": result.cache_hits,
                "misses": result.cache_misses,
                "summary": result.summaries_by_paper_id[paper.id].summary_short,
            }

    assert asyncio.run(scenario()) == {"hits": 1, "misses": 0, "summary": "Cached"}


def test_missing_abstract_records_failed_summary_without_llm_call(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            paper = Paper(source="europe_pmc", source_id="MED:1", title="No abstract")
            session.add(paper)
            await session.flush()
            summary, _ = await summary_service.get_or_create_summary_placeholder(
                session,
                paper,
                model="gpt-5-mini",
                prompt_version="v1",
            )

            llm = FakeLLMClient()
            failed = await summary_service.generate_summary(session, summary.id, llm)
            return {
                "status": failed.status,
                "error": failed.error_message,
                "calls": len(llm.calls),
            }

    assert asyncio.run(scenario()) == {
        "status": "failed",
        "error": "Paper abstract is missing",
        "calls": 0,
    }


def test_llm_error_records_failed_summary(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            paper = Paper(
                source="europe_pmc",
                source_id="MED:1",
                title="Spatial paper",
                abstract="Spatial transcriptomics abstract",
            )
            session.add(paper)
            await session.flush()
            summary, _ = await summary_service.get_or_create_summary_placeholder(
                session,
                paper,
                model="gpt-5-mini",
                prompt_version="v1",
            )

            failed = await summary_service.generate_summary(
                session,
                summary.id,
                FakeLLMClient(fail=True),
            )
            return {"status": failed.status, "error": failed.error_message}

    result = asyncio.run(scenario())
    assert result["status"] == "failed"
    assert "llm unavailable" in result["error"]


def test_summary_job_records_metrics(async_session_factory, monkeypatch) -> None:
    async def fake_generate(session, summary_id, llm_client):
        return PaperSummary(
            id=summary_id,
            paper_id=1,
            model="gpt-5-mini",
            prompt_version="v1",
            input_hash="abc",
            status="completed",
        )

    monkeypatch.setattr(summary_job, "SessionLocal", async_session_factory)
    monkeypatch.setattr(summary_job, "build_paper_summary_client", lambda settings: FakeLLMClient())
    monkeypatch.setattr(summary_job.summary_service, "generate_summary", fake_generate)

    asyncio.run(summary_job._process_paper_summary_job(123))
    metrics_text = generate_latest().decode()

    assert 'biowatch_paper_summary_jobs_total{status="completed"}' in metrics_text
    assert "biowatch_paper_summary_job_duration_seconds_bucket" in metrics_text
