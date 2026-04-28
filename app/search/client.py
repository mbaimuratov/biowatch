from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from elasticsearch import ApiError, AsyncElasticsearch, TransportError

from app.core.config import get_settings
from app.models import Paper


class SearchError(RuntimeError):
    """Raised when the paper search index cannot be used."""


class PaperSearchClient:
    def __init__(
        self,
        elasticsearch_client: AsyncElasticsearch | None = None,
        index_name: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self._index_name = index_name or settings.elasticsearch_index
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.elasticsearch_timeout_seconds
        )
        self._client = elasticsearch_client or AsyncElasticsearch(
            settings.elasticsearch_url,
            request_timeout=self._timeout_seconds,
        )
        self._owns_client = elasticsearch_client is None
        self._index_ensured = False

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def index_papers(self, papers: Sequence[Paper]) -> None:
        if not papers:
            return

        try:
            await self._ensure_index()
            for paper in papers:
                await self._client.index(
                    index=self._index_name,
                    id=str(paper.id),
                    document=_paper_document(paper),
                )
            await self._client.indices.refresh(index=self._index_name)
        except (ApiError, TransportError) as exc:
            raise SearchError("Failed to index papers in Elasticsearch") from exc

    async def search_papers(self, query: str, size: int = 25) -> list[int]:
        try:
            await self._ensure_index()
            response = await self._client.search(
                index=self._index_name,
                size=size,
                query={
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "title^3",
                            "abstract",
                            "journal^2",
                            "doi",
                            "source",
                            "source_id",
                        ],
                    }
                },
            )
        except (ApiError, TransportError) as exc:
            raise SearchError("Failed to search papers in Elasticsearch") from exc

        hits = response.get("hits", {}).get("hits", [])
        paper_ids: list[int] = []
        for hit in hits:
            try:
                paper_ids.append(int(hit["_id"]))
            except (KeyError, TypeError, ValueError):
                continue
        return paper_ids

    async def _ensure_index(self) -> None:
        if self._index_ensured:
            return

        exists = await self._client.indices.exists(index=self._index_name)
        if not exists:
            await self._client.indices.create(
                index=self._index_name,
                mappings={
                    "properties": {
                        "id": {"type": "integer"},
                        "source": {"type": "keyword"},
                        "source_id": {"type": "keyword"},
                        "title": {"type": "text"},
                        "abstract": {"type": "text"},
                        "journal": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                        "publication_date": {"type": "date"},
                        "doi": {"type": "keyword"},
                        "url": {"type": "keyword"},
                        "created_at": {"type": "date"},
                    }
                },
            )
        self._index_ensured = True


def _paper_document(paper: Paper) -> dict[str, Any]:
    return {
        "id": paper.id,
        "source": paper.source,
        "source_id": paper.source_id,
        "title": paper.title,
        "abstract": paper.abstract,
        "journal": paper.journal,
        "publication_date": _serialize_date(paper.publication_date),
        "doi": paper.doi,
        "url": paper.url,
        "created_at": _serialize_date(paper.created_at),
    }


def _serialize_date(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
