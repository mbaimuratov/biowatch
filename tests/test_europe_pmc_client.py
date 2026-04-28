import asyncio

from httpx import AsyncClient, MockTransport, Request, Response

from app.clients.europe_pmc import EuropePMCClient, EuropePMCClientError


def test_europe_pmc_client_retries_retryable_status() -> None:
    requests: list[Request] = []

    async def run_search() -> dict:
        def handler(request: Request) -> Response:
            requests.append(request)
            if len(requests) == 1:
                return Response(500, json={"error": "temporary"}, request=request)
            return Response(200, json={"resultList": {"result": []}}, request=request)

        async with AsyncClient(transport=MockTransport(handler)) as http_client:
            client = EuropePMCClient(
                http_client=http_client,
                max_attempts=2,
                retry_backoff_seconds=0,
            )
            return await client.search("cancer", page_size=25)

    response = asyncio.run(run_search())

    assert response == {"resultList": {"result": []}}
    assert len(requests) == 2


def test_europe_pmc_client_does_not_retry_non_retryable_status() -> None:
    requests: list[Request] = []

    async def run_search() -> None:
        def handler(request: Request) -> Response:
            requests.append(request)
            return Response(400, json={"error": "bad query"}, request=request)

        async with AsyncClient(transport=MockTransport(handler)) as http_client:
            client = EuropePMCClient(
                http_client=http_client,
                max_attempts=3,
                retry_backoff_seconds=0,
            )
            await client.search("bad query", page_size=25)

    try:
        asyncio.run(run_search())
    except EuropePMCClientError as exc:
        assert "HTTP 400" in str(exc)
    else:
        raise AssertionError("Expected EuropePMCClientError")

    assert len(requests) == 1
