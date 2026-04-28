from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.jobs.ingestion import process_ingestion_run_job
from app.jobs.queues import get_ingestion_queue
from app.schemas.ingestion_runs import IngestionRunRead
from app.schemas.papers import PaperRead
from app.schemas.subscriptions import SubscriptionIngestDueRead
from app.schemas.topics import TopicCreate, TopicRead
from app.search.client import PaperSearchClient, SearchError
from app.services import ingestion as ingestion_service
from app.services import papers as paper_service
from app.services import subscriptions as subscription_service
from app.services import topics as topic_service

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_session)]
IngestionQueueDep = Annotated[object, Depends(get_ingestion_queue)]


def get_paper_search_client() -> PaperSearchClient:
    return PaperSearchClient()


SearchClientDep = Annotated[PaperSearchClient, Depends(get_paper_search_client)]


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.post(
    "/topics",
    response_model=TopicRead,
    status_code=status.HTTP_201_CREATED,
    tags=["topics"],
)
async def create_topic(
    data: TopicCreate,
    session: SessionDep,
) -> TopicRead:
    return await topic_service.create_topic(session, data)


@router.get("/topics", response_model=list[TopicRead], tags=["topics"])
async def list_topics(session: SessionDep) -> list[TopicRead]:
    return await topic_service.list_topics(session)


@router.get("/topics/{topic_id}", response_model=TopicRead, tags=["topics"])
async def get_topic(
    topic_id: int,
    session: SessionDep,
) -> TopicRead:
    topic = await topic_service.get_topic(session, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["topics"])
async def delete_topic(
    topic_id: int,
    session: SessionDep,
) -> Response:
    try:
        deleted = await topic_service.delete_topic(session, topic_id)
    except topic_service.TopicHasActiveIngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Topic has active ingestion runs",
        ) from exc

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/topics/{topic_id}/ingest",
    response_model=IngestionRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingestion"],
)
async def ingest_topic(
    topic_id: int,
    session: SessionDep,
    ingestion_queue: IngestionQueueDep,
) -> IngestionRunRead:
    topic = await topic_service.get_topic(session, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    return await ingestion_service.enqueue_topic_ingestion(
        session,
        topic,
        ingestion_queue,
        process_ingestion_run_job,
    )


@router.post(
    "/subscriptions/ingest-due",
    response_model=SubscriptionIngestDueRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["subscriptions"],
)
async def ingest_due_topics(
    session: SessionDep,
    ingestion_queue: IngestionQueueDep,
) -> SubscriptionIngestDueRead:
    result = await subscription_service.enqueue_due_topic_ingestions(
        session,
        ingestion_queue,
        process_ingestion_run_job,
    )
    return SubscriptionIngestDueRead(
        topics_checked=result.topics_checked,
        topics_enqueued=result.topics_enqueued,
        ingestion_run_ids=result.ingestion_run_ids,
        job_ids=result.job_ids,
    )


@router.get("/topics/{topic_id}/papers", response_model=list[PaperRead], tags=["papers"])
async def list_topic_papers(
    topic_id: int,
    session: SessionDep,
) -> list[PaperRead]:
    topic = await topic_service.get_topic(session, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return await paper_service.list_papers_for_topic(session, topic_id)


@router.get("/papers/search", response_model=list[PaperRead], tags=["papers"])
async def search_papers(
    q: Annotated[str, Query(min_length=1)],
    session: SessionDep,
    search_client: SearchClientDep,
) -> list[PaperRead]:
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="q is required",
        )

    try:
        return await paper_service.search_papers(session, query, search_client)
    except SearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paper search is temporarily unavailable",
        ) from exc
    finally:
        await search_client.close()


@router.get("/ingestion-runs", response_model=list[IngestionRunRead], tags=["ingestion"])
async def list_ingestion_runs(
    session: SessionDep,
) -> list[IngestionRunRead]:
    return await ingestion_service.list_ingestion_runs(session)
