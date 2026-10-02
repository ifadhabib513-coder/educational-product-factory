"""Research service — unified interface for all research operations."""

from __future__ import annotations

import logging

from lpf.research.router import ResearchRouter
from lpf.schemas.research import (
    ResearchPlan,
    ResearchQuestion,
    SearchResult,
    SourceAuthority,
    VerifiedSource,
)

logger = logging.getLogger(__name__)


class ResearchService:
    """Unified research interface.

    Agents see: search_web(), search_academic(), search_wiki(), extract_url()
    Not provider-specific complexity.
    """

    def __init__(self, router: ResearchRouter) -> None:
        self._router = router

    async def search_web(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Broad web search across available providers."""

        results = []
        for provider_name in self._router.available_providers:
            provider = self._router._providers.get(provider_name)
            if provider is None:
                continue
            try:
                found = await provider.search(query, max_results=max_results)
                results.extend(found)
            except Exception as e:
                logger.warning("Search failed for provider %s: %s", provider_name, e)

        return self._deduplicate(results)

    async def search_academic(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Academic-focused search (arXiv, etc.)."""
        from lpf.schemas.research import SearchProvider

        provider = self._router._providers.get(SearchProvider.ARXIV)
        if provider is None:
            logger.info("arXiv provider not available, falling back to web search")
            return await self.search_web(query, max_results)

        return await provider.search(query, max_results=max_results)

    async def search_wiki(self, query: str, max_results: int = 3) -> list[SearchResult]:
        """Wikipedia/concept search."""
        from lpf.schemas.research import SearchProvider

        provider = self._router._providers.get(SearchProvider.WIKIMEDIA)
        if provider is None:
            logger.info("Wikimedia provider not available, falling back to web search")
            return await self.search_web(query, max_results)

        return await provider.search(query, max_results=max_results)

    async def extract_url(self, url: str) -> str:
        """Extract text content from a URL."""
        from lpf.schemas.research import SearchProvider

        # Try Tavily first, then fall back to any provider
        for provider_name in [SearchProvider.TAVILY, *self._router.available_providers]:
            provider = self._router._providers.get(provider_name)
            if provider is not None:
                try:
                    return await provider.extract(url)
                except Exception as e:
                    logger.warning("Extract failed for %s: %s", url, e)

        return ""

    async def execute_plan(self, plan: ResearchPlan) -> dict[str, list[SearchResult]]:
        """Execute a complete research plan."""
        return await self._router.execute(plan.questions)

    async def execute_plan_questions(
        self, questions: list[ResearchQuestion]
    ) -> dict[str, list[SearchResult]]:
        """Execute searches for a bare list of questions.

        The pipeline works from questions rather than a full ResearchPlan, since
        plan construction is the caller’s decision.
        """
        return await self._router.execute(questions)

    def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Remove duplicate results by URL."""
        seen_urls: set[str] = set()
        deduplicated: list[SearchResult] = []
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                deduplicated.append(r)
        return deduplicated

    @staticmethod
    def rank_sources(
        results: list[SearchResult],
        authority_weight: float = 0.4,
        relevance_weight: float = 0.6,
    ) -> list[SearchResult]:
        """Rank search results by authority and relevance."""
        authority_order = {
            SourceAuthority.PRIMARY: 7,
            SourceAuthority.INSTITUTIONAL: 6,
            SourceAuthority.ACADEMIC: 5,
            SourceAuthority.EDUCATIONAL: 4,
            SourceAuthority.TEXTBOOK: 3,
            SourceAuthority.SECONDARY: 2,
            SourceAuthority.GENERAL: 1,
            SourceAuthority.UNKNOWN: 0,
        }

        def score(r: SearchResult) -> float:
            auth = authority_order.get(r.authority, 0) / 7.0
            return auth * authority_weight + r.relevance_score * relevance_weight

        return sorted(results, key=score, reverse=True)

    @staticmethod
    def verify_source(result: SearchResult) -> VerifiedSource:
        """Create a VerifiedSource from a SearchResult."""
        return VerifiedSource(
            source_id=result.source_id,
            url=result.url,
            title=result.title,
            domain=result.domain,
            authority=result.authority,
            exists=True,
            accessible=True,
            relevant=result.relevance_score > 0.5,
        )
