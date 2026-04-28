from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper, TopicPaper
from app.search.client import PaperSearchClient


async def list_papers_for_topic(session: AsyncSession, topic_id: int) -> list[Paper]:
    result = await session.scalars(
        select(Paper)
        .join(TopicPaper, TopicPaper.paper_id == Paper.id)
        .where(TopicPaper.topic_id == topic_id)
        .order_by(Paper.created_at.desc(), Paper.id)
    )
    return list(result)


async def list_recent_papers(session: AsyncSession, limit: int = 50) -> list[Paper]:
    result = await session.scalars(
        select(Paper).order_by(Paper.created_at.desc(), Paper.id).limit(limit)
    )
    return list(result)


async def search_papers(
    session: AsyncSession,
    query: str,
    search_client: PaperSearchClient,
) -> list[Paper]:
    paper_ids = await search_client.search_papers(query)
    if not paper_ids:
        return []

    result = await session.scalars(select(Paper).where(Paper.id.in_(paper_ids)))
    papers_by_id = {paper.id: paper for paper in result}
    return [papers_by_id[paper_id] for paper_id in paper_ids if paper_id in papers_by_id]
