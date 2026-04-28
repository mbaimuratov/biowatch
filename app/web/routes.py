from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.jobs.ingestion import process_ingestion_run_job
from app.jobs.queues import get_ingestion_queue
from app.schemas.topics import TopicCreate
from app.search.client import PaperSearchClient, SearchError
from app.services import ingestion as ingestion_service
from app.services import papers as paper_service
from app.services import topics as topic_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IngestionQueueDep = Annotated[object, Depends(get_ingestion_queue)]


def get_paper_search_client() -> PaperSearchClient:
    return PaperSearchClient()


SearchClientDep = Annotated[PaperSearchClient, Depends(get_paper_search_client)]


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_home(
    request: Request,
    session: SessionDep,
    message: str | None = None,
) -> HTMLResponse:
    topics = await topic_service.list_topics(session)
    return templates.TemplateResponse(
        request,
        "topics.html",
        {"topics": topics, "message": message},
    )


@router.post("/ui/topics", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_create_topic(
    request: Request,
    session: SessionDep,
    name: Annotated[str, Form()],
    query: Annotated[str, Form()],
    enabled: Annotated[bool, Form()] = False,
) -> Response:
    try:
        topic_data = TopicCreate(name=name, query=query, enabled=enabled)
    except ValidationError as exc:
        topics = await topic_service.list_topics(session)
        return templates.TemplateResponse(
            request,
            "topics.html",
            {
                "topics": topics,
                "error": "Topic name and query are required.",
                "form": {"name": name, "query": query, "enabled": enabled},
                "details": exc.errors(),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    topic = await topic_service.create_topic(session, topic_data)
    return RedirectResponse(
        f"/ui/topics/{topic.id}?message=Topic%20created",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/ui/topics/{topic_id}", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_topic_detail(
    request: Request,
    topic_id: int,
    session: SessionDep,
    message: str | None = None,
) -> HTMLResponse:
    topic = await topic_service.get_topic(session, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    papers = await paper_service.list_papers_for_topic(session, topic_id)
    runs = await ingestion_service.list_ingestion_runs(session)
    topic_runs = [run for run in runs if run.topic_id == topic_id]
    return templates.TemplateResponse(
        request,
        "topic_detail.html",
        {
            "topic": topic,
            "papers": papers,
            "runs": topic_runs,
            "message": message,
        },
    )


@router.post("/ui/topics/{topic_id}/ingest", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_ingest_topic(
    request: Request,
    topic_id: int,
    session: SessionDep,
    ingestion_queue: IngestionQueueDep,
) -> Response:
    topic = await topic_service.get_topic(session, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    run = await ingestion_service.create_queued_run(session, topic)
    job = ingestion_queue.enqueue(process_ingestion_run_job, run.id)
    run = await ingestion_service.mark_run_enqueued(session, run, job.id)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request,
            "partials/ingestion_status.html",
            {"run": run},
            status_code=status.HTTP_202_ACCEPTED,
        )

    return RedirectResponse(
        f"/ui/topics/{topic_id}?message=Ingestion%20queued",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/ui/papers", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_papers(
    request: Request,
    session: SessionDep,
) -> HTMLResponse:
    papers = await paper_service.list_recent_papers(session)
    return templates.TemplateResponse(request, "papers.html", {"papers": papers})


@router.get("/ui/ingestion-runs", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_ingestion_runs(
    request: Request,
    session: SessionDep,
) -> HTMLResponse:
    runs = await ingestion_service.list_ingestion_runs(session)
    return templates.TemplateResponse(request, "ingestion_runs.html", {"runs": runs})


@router.get("/ui/search", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_search(
    request: Request,
    session: SessionDep,
    search_client: SearchClientDep,
    q: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    return await _render_search(request, session, search_client, q, "search.html")


@router.get("/ui/search/results", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_search_results(
    request: Request,
    session: SessionDep,
    search_client: SearchClientDep,
    q: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    return await _render_search(request, session, search_client, q, "partials/search_results.html")


async def _render_search(
    request: Request,
    session: AsyncSession,
    search_client: PaperSearchClient,
    query_text: str | None,
    template_name: str,
) -> HTMLResponse:
    query = (query_text or "").strip()
    papers = []
    error = None

    try:
        if query:
            papers = await paper_service.search_papers(session, query, search_client)
    except SearchError:
        error = "Paper search is temporarily unavailable."
    finally:
        await search_client.close()

    return templates.TemplateResponse(
        request,
        template_name,
        {"q": query_text or "", "query": query, "papers": papers, "error": error},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE if error else status.HTTP_200_OK,
    )
