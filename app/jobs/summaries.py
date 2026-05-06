import logging
import time

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.jobs.runtime import run_job_coroutine
from app.llm.client import build_paper_summary_client
from app.models import PaperSummary
from app.observability.metrics import (
    PAPER_SUMMARY_JOB_DURATION_SECONDS,
    PAPER_SUMMARY_JOBS_TOTAL,
)
from app.services import summaries as summary_service

logger = logging.getLogger(__name__)


def process_paper_summary_job(summary_id: int) -> int:
    return run_job_coroutine(_process_paper_summary_job(summary_id))


async def _process_paper_summary_job(summary_id: int) -> int:
    started_at = time.perf_counter()
    status = "failed"
    paper_id = None
    settings = get_settings()
    async with SessionLocal() as session:
        try:
            llm_client = build_paper_summary_client(settings)
            summary = await summary_service.generate_summary(session, summary_id, llm_client)
            status = summary.status
            paper_id = summary.paper_id
            return summary_id
        except Exception as exc:
            summary = await session.get(PaperSummary, summary_id)
            if summary is not None:
                summary.status = "failed"
                summary.error_message = str(exc)
                summary.generated_at = summary_service.utc_now()
                paper_id = summary.paper_id
                await session.commit()
            logger.exception("Paper summary job failed", extra={"summary_id": summary_id})
            return summary_id
        finally:
            duration = time.perf_counter() - started_at
            PAPER_SUMMARY_JOBS_TOTAL.labels(status=status).inc()
            PAPER_SUMMARY_JOB_DURATION_SECONDS.labels(status=status).observe(duration)
            logger.info(
                "Paper summary job finished",
                extra={
                    "summary_id": summary_id,
                    "paper_id": paper_id,
                    "status": status,
                    "model": settings.llm_model,
                    "prompt_version": settings.summary_prompt_version,
                    "duration_seconds": round(duration, 6),
                },
            )
