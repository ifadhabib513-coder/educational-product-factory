"""Tavily provider — AI search with page extraction.

Tavily returns cleaned page content alongside results, so it is the preferred
provider for ``extract_url``. Requires an API key.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from lpf.domain.identity import seeded_id
from lpf.research.authority import classify_authority, extract_domain
from lpf.research.transport import HttpTransport, RateLimiter, TransportError, build_client
from lpf.schemas.research import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

_API_URL = "https://api.tavily.com/search"


class TavilyProvider:
    """Search and extract via the Tavily API."""

    provider_name: SearchProvider = SearchProvider.TAVILY

    def __init__(
        self,
        api_key: str,
        transport: HttpTransport | None = None,
        *,
        search_depth: str = "advanced",
        include_answer: bool = False,
        max_extracted_chars: int = 20_000,
    ) -> None:
        if not api_key:
            raise ValueError("TavilyProvider requires an API key")

        self._api_key = api_key
        self._search_depth = search_depth
        self._include_answer = include_answer
        self._max_extracted_chars = max_extracted_chars
        self._transport = transport or HttpTransport(
            client=build_client(),
            rate_limiter=RateLimiter(min_interval_seconds=1.0),
        )

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        """Run a Tavily search and normalise the results."""
        data = await self._transport.post_json(
            _API_URL,
            {
                "api_key": self._api_key,
                "query": query,
                "search_depth": self._search_depth,
                "max_results": max_results,
                "include_answer": self._include_answer,
            },
        )

        if not isinstance(data, dict):
            raise TransportError(f"Unexpected Tavily payload type: {type(data).__name__}")

        raw_results = data.get("results") or []
        results: list[SearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(self._to_result(item))
        return results

    async def extract(self, url: str) -> str:
        """Extract clean text from a URL."""
        data = await self._transport.post_json(
            "https://api.tavily.com/extract",
            {"api_key": self._api_key, "urls": [url]},
        )

        if not isinstance(data, dict):
            raise TransportError(f"Unexpected Tavily extract payload: {type(data).__name__}")

        results = data.get("results") or []
        if not results:
            return ""

        first = results[0]
        raw = (
            str(first.get("raw_content") or first.get("content") or "")
            if isinstance(first, dict)
            else ""
        )
        return raw[: self._max_extracted_chars]

    def _to_result(self, item: dict[str, Any]) -> SearchResult:
        url = str(item.get("url") or "")
        title = str(item.get("title") or "").strip()

        return SearchResult(
            source_id=seeded_id(self.provider_name, url),
            title=title or url or "Untitled",
            url=url,
            snippet=str(item.get("content") or "").strip(),
            domain=extract_domain(url),
            provider=self.provider_name,
            published_at=_parse_date(item.get("published_date")),
            authority=classify_authority(url),
            relevance_score=self._score(item.get("score")),
        )

    @staticmethod
    def _score(value: Any) -> float:
        """Coerce Tavily's relevance score into 0..1.

        Missing or malformed scores yield 0.0 rather than a default mid-range
        value, so an unscored result cannot outrank a scored one.
        """
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, score))


def _parse_date(value: Any) -> datetime | None:
    """Parse a Tavily ``published_date``, tolerating absence or bad format.

    Tavily is inconsistent about the format it returns (ISO with or without a
    timezone, occasionally a bare date), so a bad value yields None rather than
    failing the whole search.
    """
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
