from typing import Any

import httpx

from app.core.config import get_settings


class PubMedClient:
    """Small async client for NCBI PubMed E-utilities."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._base_url = settings.pubmed_base_url
        self._http_client = http_client

    async def search_ids(self, term: str, retmax: int = 25) -> dict[str, Any]:
        client = self._http_client or httpx.AsyncClient()
        should_close = self._http_client is None

        try:
            response = await client.get(
                f"{self._base_url}/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": term,
                    "retmode": "json",
                    "retmax": retmax,
                },
            )
            response.raise_for_status()
            return response.json()
        finally:
            if should_close:
                await client.aclose()
