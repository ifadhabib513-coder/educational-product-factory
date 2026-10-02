"""Research providers — base protocol + mock implementation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lpf.schemas.research import SearchProvider, SearchResult


@runtime_checkable
class SearchProviderProto(Protocol):
    """Protocol for all search providers."""

    provider_name: SearchProvider

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        """Search and return normalized results."""
        ...

    async def extract(self, url: str) -> str:
        """Extract text content from a URL."""
        ...


class MockSearchProvider:
    """Mock search provider for testing."""

    provider_name: SearchProvider = SearchProvider.MOCK

    def __init__(
        self,
        results: list[SearchResult] | None = None,
        extraction_text: str = "mock extracted content",
    ) -> None:
        self._results = results or []
        self._extraction = extraction_text
        self._search_calls: list[str] = []

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        self._search_calls.append(query)
        return self._results[:max_results]

    async def extract(self, url: str) -> str:
        return self._extraction

    @property
    def search_calls(self) -> list[str]:
        return self._search_calls
