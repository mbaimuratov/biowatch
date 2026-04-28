import asyncio

from app.db.session import SessionLocal
from app.services.ingestion import process_ingestion_run


def process_ingestion_run_job(run_id: int) -> int:
    return asyncio.run(_process_ingestion_run_job(run_id))


async def _process_ingestion_run_job(run_id: int) -> int:
    async with SessionLocal() as session:
        await process_ingestion_run(session, run_id)
    return run_id
