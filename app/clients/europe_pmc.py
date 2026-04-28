import asyncio
from typing import Any

import httpx

from app.core.config import get_settings


class EuropePMCClientError(RuntimeError):
    """Raised when Europe PMC search cannot be completed."""


class EuropePMCClient:
    """Small async client for the Europe PMC REST API."""

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = settings.europe_pmc_base_url
        self._http_client = http_client
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.europe_pmc_timeout_seconds
        )
        self._max_attempts = (
            max_attempts if max_attempts is not None else settings.europe_pmc_max_attempts
        )
        self._retry_backoff_seconds = (
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else settings.europe_pmc_retry_backoff_seconds
        )

    async def search(self, query: str, page_size: int = 25) -> dict[str, Any]:
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout_seconds)
        should_close = self._http_client is None

        try:
            return await self._search_with_retries(client, query, page_size)
        finally:
            if should_close:
                await client.aclose()

    async def _search_with_retries(
        self,
        client: httpx.AsyncClient,
        query: str,
        page_size: int,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await client.get(
                    f"{self._base_url}/search",
                    params={
                        "query": f"{query} sort_date:y",
                        "format": "json",
                        "resultType": "core",
                        "pageSize": page_size,
                    },
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                if not _is_retryable_status(exc.response.status_code):
                    raise EuropePMCClientError(
                        f"Europe PMC returned HTTP {exc.response.status_code}"
                    ) from exc
                last_error = exc
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = exc

            if attempt < self._max_attempts:
                await asyncio.sleep(self._retry_backoff_seconds * (2 ** (attempt - 1)))

        raise EuropePMCClientError(
            f"Europe PMC request failed after {self._max_attempts} attempts: {last_error}"
        ) from last_error


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500
