"""SearXNG provider — self-hosted metasearch.

SearXNG exposes a JSON API at ``/search``. Running it locally keeps search
history off third-party servers and removes an external dependency on the
critical path.
"""

from __future__ import annotations

import logging

from lpf.domain.identity import seeded_id
from lpf.research.authority import classify_authority, extract_domain
from lpf.research.transport import (
    HttpTransport,
    RateLimiter,
    TransportError,
    build_client,
)
from lpf.schemas.research import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class SearxngProvider:
    """Search via a self-hosted SearXNG instance."""

    provider_name: SearchProvider = SearchProvider.SEARXNG

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        transport: HttpTransport | None = None,
        *,
        categories: str = "general,science",
        language: str = "en",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._categories = categories
        self._language = language
        self._owns_transport = transport is None
        self._transport = transport or HttpTransport(
            client=build_client(headers={"Accept": "application/json"}),
            rate_limiter=RateLimiter(min_interval_seconds=0.2),
        )

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        """Query SearXNG and normalise its JSON results."""
        data = await self._transport.get_json(
            f"{self._base_url}/search",
            params={
                "q": query,
                "format": "json",
                "categories": self._categories,
                "language": self._language,
            },
        )

        if not isinstance(data, dict):
            raise TransportError(f"Unexpected SearXNG payload type: {type(data).__name__}")

        raw_results = data.get("results") or []
        results: list[SearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(self._to_result(item))
        return results

    async def extract(self, url: str) -> str:
        """SearXNG does not extract page text; return empty to signal fallback."""
        return ""

    def _to_result(self, item: dict) -> SearchResult:
        url = str(item.get("url") or "")
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()

        return SearchResult(
            source_id=seeded_id(self.provider_name, url),
            title=title or url or "Untitled",
            url=url,
            snippet=snippet,
            domain=extract_domain(url),
            provider=self.provider_name,
            authority=classify_authority(url),
        )
