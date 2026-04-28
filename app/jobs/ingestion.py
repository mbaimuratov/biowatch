import asyncio
import logging
import time

from app.db.session import SessionLocal
from app.observability.metrics import (
    INGESTION_JOB_DURATION_SECONDS,
    INGESTION_JOBS_IN_PROGRESS,
    INGESTION_JOBS_TOTAL,
    INGESTION_RECORDS_FETCHED_TOTAL,
)
from app.services.ingestion import process_ingestion_run

logger = logging.getLogger(__name__)


def process_ingestion_run_job(run_id: int) -> int:
    return asyncio.run(_process_ingestion_run_job(run_id))


async def _process_ingestion_run_job(run_id: int) -> int:
    started_at = time.perf_counter()
    status = "failed"
    records_fetched = 0
    topic_id = None
    INGESTION_JOBS_IN_PROGRESS.inc()
    async with SessionLocal() as session:
        try:
            run = await process_ingestion_run(session, run_id)
            status = run.status
            records_fetched = run.records_fetched
            topic_id = run.topic_id
            if status == "completed":
                INGESTION_RECORDS_FETCHED_TOTAL.inc(records_fetched)
            return run_id
        except Exception:
            logger.exception("Ingestion job failed", extra={"ingestion_run_id": run_id})
            raise
        finally:
            duration = time.perf_counter() - started_at
            INGESTION_JOBS_TOTAL.labels(status=status).inc()
            INGESTION_JOB_DURATION_SECONDS.labels(status=status).observe(duration)
            INGESTION_JOBS_IN_PROGRESS.dec()
            logger.info(
                "Ingestion job finished",
                extra={
                    "ingestion_run_id": run_id,
                    "topic_id": topic_id,
                    "status": status,
                    "records_fetched": records_fetched,
                    "duration_seconds": round(duration, 6),
                },
            )
