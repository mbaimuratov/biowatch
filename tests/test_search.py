import asyncio
from datetime import date

from fastapi.testclient import TestClient

from app.api.routes import get_paper_search_client
from app.main import app
from app.models import Paper
from app.search.client import SearchError


class FakeSearchClient:
    def __init__(
        self,
        paper_ids: list[int] | None = None,
        should_fail: bool = False,
    ) -> None:
        self.paper_ids = paper_ids or []
        self.should_fail = should_fail
        self.queries: list[str] = []
        self.closed = False

    async def search_papers(self, query: str) -> list[int]:
        self.queries.append(query)
        if self.should_fail:
            raise SearchError("Elasticsearch unavailable")
        return self.paper_ids

    async def close(self) -> None:
        self.closed = True


def test_search_endpoint_returns_matching_postgres_papers(
    client: TestClient,
    async_session_factory,
) -> None:
    paper_ids = asyncio.run(_create_papers(async_session_factory))
    search_client = FakeSearchClient(paper_ids=[paper_ids[1], paper_ids[0]])
    app.dependency_overrides[get_paper_search_client] = lambda: search_client

    response = client.get("/papers/search?q=biomarker")

    assert response.status_code == 200
    papers = response.json()
    assert [paper["id"] for paper in papers] == [paper_ids[1], paper_ids[0]]
    assert [paper["title"] for paper in papers] == [
        "Second biomarker paper",
        "First biomarker paper",
    ]
    assert search_client.queries == ["biomarker"]
    assert search_client.closed is True


def test_search_endpoint_rejects_missing_or_blank_query(client: TestClient) -> None:
    missing_response = client.get("/papers/search")
    blank_response = client.get("/papers/search?q=%20%20")

    assert missing_response.status_code == 422
    assert blank_response.status_code == 422


def test_search_endpoint_returns_503_when_search_fails(client: TestClient) -> None:
    search_client = FakeSearchClient(should_fail=True)
    app.dependency_overrides[get_paper_search_client] = lambda: search_client

    response = client.get("/papers/search?q=biomarker")

    assert response.status_code == 503
    assert response.json() == {"detail": "Paper search is temporarily unavailable"}
    assert search_client.closed is True


async def _create_papers(async_session_factory) -> list[int]:
    async with async_session_factory() as session:
        papers = [
            Paper(
                source="europe_pmc",
                source_id="MED:1",
                title="First biomarker paper",
                abstract="Alpha",
                journal="BioWatch Journal",
                publication_date=date(2024, 1, 1),
                doi="10.1000/one",
                url="https://example.test/one",
            ),
            Paper(
                source="europe_pmc",
                source_id="MED:2",
                title="Second biomarker paper",
                abstract="Beta",
                journal="BioWatch Journal",
                publication_date=date(2024, 1, 2),
                doi="10.1000/two",
                url="https://example.test/two",
            ),
        ]
        session.add_all(papers)
        await session.commit()
        return [paper.id for paper in papers]
