"""Wikimedia provider — Wikipedia and Wikimedia Commons concept discovery.

Used for concept discovery rather than evidence: Wikipedia is a good index of
what a topic is called and how it relates to other topics, but it is not an
authority. Results are classified SECONDARY by the shared authority classifier.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote, unquote, urlparse

from lpf.domain.identity import seeded_id
from lpf.research.authority import classify_authority
from lpf.research.transport import HttpTransport, RateLimiter, TransportError, build_client
from lpf.schemas.research import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

_API_URL = "https://en.wikipedia.org/w/api.php"

# Wikimedia rejects requests whose User-Agent lacks a contactable URL or email,
# answering 403 "Please respect our robot policy". Verified live: a UA ending in
# "contact via repo" is refused, while one carrying a URL is accepted. Set
# LPF_RESEARCH_CONTACT to a real project URL or maintainer email before use.
_DEFAULT_CONTACT = "https://example.org/lpf-research"
_USER_AGENT = f"lpf-research/0.1 (educational product factory; {os.environ.get('LPF_RESEARCH_CONTACT', _DEFAULT_CONTACT)})"


class WikimediaProvider:
    """Search Wikipedia via the MediaWiki action API."""

    provider_name: SearchProvider = SearchProvider.WIKIMEDIA

    def __init__(
        self,
        transport: HttpTransport | None = None,
        *,
        language: str = "en",
        limit: int = 10,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._language = language
        self._limit = limit
        self._owns_transport = transport is None
        base = f"https://{language}.wikipedia.org/w/api.php"
        self._transport = transport or HttpTransport(
            client=build_client(user_agent=_USER_AGENT, timeout_seconds=timeout_seconds),
            rate_limiter=RateLimiter(min_interval_seconds=0.5),
        )
        self._search_url = base
        self._extract_base = f"https://{language}.wikipedia.org/api/rest_v1"

    async def aclose(self) -> None:
        """Close the HTTP client, but only if this provider created it."""
        if self._owns_transport:
            await self._transport.aclose()

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        """Full-text search Wikipedia, returning matching article summaries."""
        limit = min(max_results, self._limit)
        data = await self._transport.get_json(
            self._search_url,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
                "utf8": 1,
            },
        )

        if not isinstance(data, dict):
            raise TransportError(f"Unexpected Wikimedia payload: {type(data).__name__}")

        query_block = data.get("query") or {}
        hits = query_block.get("search") or []
        return [self._to_result(hit) for hit in hits[:limit] if isinstance(hit, dict)]

    async def extract(self, url: str) -> str:
        """Fetch the plain-text extract for a Wikipedia article URL."""
        title = self._title_from_url(url)
        if not title:
            return ""

        data = await self._transport.get_json(
            f"{self._extract_base}/page/summary/{quote(title, safe='')}"
        )
        if not isinstance(data, dict):
            return ""
        return str(data.get("extract") or "")

    def _to_result(self, hit: dict[str, Any]) -> SearchResult:
        title = str(hit.get("title") or "")
        page_url = (
            f"https://{self._language}.wikipedia.org/wiki/{title.replace(' ', '_')}"
            if title
            else ""
        )
        snippet = str(hit.get("snippet") or "")

        return SearchResult(
            source_id=seeded_id(self.provider_name, page_url),
            title=title or "Untitled",
            url=page_url,
            snippet=_strip_html(snippet),
            domain=f"{self._language}.wikipedia.org",
            provider=self.provider_name,
            authority=classify_authority(page_url),
        )

    @staticmethod
    def _title_from_url(url: str) -> str:
        """Extract an article title from a Wikipedia URL."""
        if not url or "wikipedia.org" not in url:
            return ""

        path = urlparse(url).path
        if "/wiki/" not in path:
            return ""

        slug = path.split("/wiki/", 1)[1]
        # Article sections live after '#', which is not part of the title.
        slug = slug.split("#", 1)[0]
        return unquote(slug).replace("_", " ")


def _strip_html(text: str) -> str:
    """Remove MediaWiki's search-result highlight markup.

    The API wraps matched terms in ``<span class="searchmatch">``; leaving the
    tags in would put raw HTML into evidence text.
    """
    return " ".join(text.replace('<span class="searchmatch">', "").replace("</span>", "").split())
