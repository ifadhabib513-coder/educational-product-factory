"""arXiv provider — academic preprint search.

Uses the public arXiv Atom API. No key required. Results are always classified
as ACADEMIC by construction: the provider only ever returns arxiv.org URLs.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from lpf.domain.identity import seeded_id
from lpf.research.authority import classify_authority
from lpf.research.transport import HttpTransport, RateLimiter, TransportError, build_client
from lpf.schemas.research import SearchProvider, SearchResult, SourceAuthority

logger = logging.getLogger(__name__)

_API_URL = "https://export.arxiv.org/api/query"

_ARXIV_DOMAIN = "arxiv.org"

# arXiv is strict about being called too often; be slower than rate limits require.
_ARXIV_INTERVAL_SECONDS = 3.0

_ATOM_NS = "{http://www.w3.org/2005/Atom}"


class ArxivProvider:
    """Search arXiv for academic preprints."""

    provider_name: SearchProvider = SearchProvider.ARXIV

    def __init__(
        self,
        transport: HttpTransport | None = None,
        *,
        max_query_chars: int = 400,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._max_query_chars = max_query_chars
        self._owns_transport = transport is None
        self._transport = transport or HttpTransport(
            client=build_client(
                headers={"Accept": "application/atom+xml"},
                timeout_seconds=timeout_seconds,
            ),
            rate_limiter=RateLimiter(min_interval_seconds=_ARXIV_INTERVAL_SECONDS),
        )

    async def aclose(self) -> None:
        """Close the HTTP client, but only if this provider created it."""
        if self._owns_transport:
            await self._transport.aclose()

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        """Query arXiv and normalise Atom entries into SearchResults."""
        text = await self._transport.get_text(
            _API_URL,
            params={
                "search_query": f"all:{query}"[: self._max_query_chars],
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
        )
        return self._parse(text, max_results)

    async def extract(self, url: str) -> str:
        """Fetch an arXiv abstract page and return its summary text."""
        try:
            return await self._transport.get_text(url)
        except TransportError as e:
            logger.warning("arXiv extract failed for %s: %s", url, e)
            return ""

    @staticmethod
    def _parse(xml_text: str, max_results: int) -> list[SearchResult]:
        """Parse an Atom feed into SearchResults.

        Malformed XML yields an empty list rather than raising: a research stage
        that cannot parse one feed should continue with what it already has.
        """
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("Could not parse arXiv Atom feed: %s", e)
            return []

        results: list[SearchResult] = []
        for entry in root.findall(f"{_ATOM_NS}entry")[:max_results]:
            results.append(_entry_to_result(entry))
        return results


def _entry_to_result(entry: ET.Element) -> SearchResult:
    url = _text(entry, "id")
    title = _text(entry, "title")
    summary = _text(entry, "summary")
    published = _text(entry, "published")

    return SearchResult(
        source_id=seeded_id(SearchProvider.ARXIV, url),
        title=_collapse(title) or url or "Untitled arXiv entry",
        url=url,
        snippet=_collapse(summary),
        domain=_ARXIV_DOMAIN,
        provider=SearchProvider.ARXIV,
        published_at=_parse_date(published),
        # Entries without a URL cannot be authority-classified from the URL, but
        # they came from arxiv, so ACADEMIC is a property of the provider.
        authority=classify_authority(url) if url else SourceAuthority.ACADEMIC,
    )


def _text(entry: ET.Element, tag: str) -> str:
    node = entry.find(f"{_ATOM_NS}{tag}")
    return (node.text or "").strip() if node is not None else ""


def _collapse(text: str) -> str:
    """Collapse runs of whitespace, which arXiv is full of."""
    return " ".join(text.split())


def _parse_date(value: str) -> datetime | None:
    """Parse an arXiv ISO-8601 timestamp, tolerating absence."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
