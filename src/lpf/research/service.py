"""Research service — unified interface for all research operations."""

from __future__ import annotations

from lpf.research.router import ResearchRouter
from lpf.schemas.research import ResearchQuestion, SearchResult


class ResearchService:
    """Unified research interface over a :class:`ResearchRouter`.

    The pipeline works from a bare list of research questions; plan construction
    and ranking are the caller's decision, so this seam stays a thin pass-through
    to the router instead of re-exposing provider-specific operations.
    """

    def __init__(self, router: ResearchRouter) -> None:
        self._router = router

    async def execute_plan_questions(
        self, questions: list[ResearchQuestion]
    ) -> dict[str, list[SearchResult]]:
        """Execute searches for a bare list of questions.

        The pipeline works from questions rather than a full ResearchPlan, since
        plan construction is the caller's decision.
        """
        return await self._router.execute(questions)
