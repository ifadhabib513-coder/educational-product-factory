"""Tests for the research provider injection seam.

The research stage must have one code path: offline providers and live providers
differ only in what the caller injects. These tests use fake providers so the
suite stays offline, and they fail if the stage ever hardcodes a provider again.
"""

from __future__ import annotations

from pathlib import Path

from lpf.orchestration.context import RunContext
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.orchestration.research_stage import build_research, default_providers
from lpf.research.audience import AudienceLevel
from lpf.schemas.discovery import DiscoveryInputs
from lpf.schemas.research import SearchProvider, SearchResult, SourceAuthority

_SNIPPET = (
    "This topic is defined here in plain language for the stated learner level, "
    "with one worked example and a note on the common mistake."
)


class FakeProvider:
    """A search provider that returns a fixed, recognisable result."""

    def __init__(self, name: SearchProvider, domain: str) -> None:
        self.provider_name = name
        self._domain = domain
        self.queries: list[str] = []

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        self.queries.append(query)
        return [
            SearchResult(
                source_id=f"{self.provider_name.value}-source-1",
                title=f"{query} (reference)",
                url=f"https://{self._domain}/reference",
                snippet=_SNIPPET,
                domain=self._domain,
                provider=self.provider_name,
                authority=SourceAuthority.SECONDARY,
                relevance_score=0.9,
            )
        ]

    async def extract(self, url: str) -> str:
        return f"Extracted content for {url}."


async def _research(ctx: RunContext, providers=None):
    return await build_research(
        ctx,
        product_spec_id="spec-1",
        research_questions=["What is linear algebra?", "Who wrote the BLAS notes?"],
        topic="linear algebra",
        audience=AudienceLevel.INTERMEDIATE,
        providers=providers,
    )


class TestDefaultProviders:
    def test_default_is_mock_only(self) -> None:
        providers = default_providers(RunContext(run_id="r"))
        assert list(providers) == [SearchProvider.MOCK]

    async def test_default_research_uses_the_offline_provider(self) -> None:
        bundle = await _research(RunContext(run_id="default-run"))
        assert bundle.results
        assert {result.provider for result in bundle.results} == {SearchProvider.MOCK}
        assert {result.domain for result in bundle.results} == {"reference.example"}


class TestInjection:
    async def test_injected_provider_replaces_the_offline_one(self) -> None:
        fake = FakeProvider(SearchProvider.WIKIMEDIA, "injected.example")
        bundle = await _research(
            RunContext(run_id="injected"), providers={SearchProvider.WIKIMEDIA: fake}
        )
        assert {result.domain for result in bundle.results} == {"injected.example"}
        assert {result.provider for result in bundle.results} == {SearchProvider.WIKIMEDIA}

    async def test_every_injected_provider_is_queried_per_question(self) -> None:
        arxiv = FakeProvider(SearchProvider.ARXIV, "arxiv.example")
        wiki = FakeProvider(SearchProvider.WIKIMEDIA, "wiki.example")
        bundle = await _research(
            RunContext(run_id="two"),
            providers={SearchProvider.ARXIV: arxiv, SearchProvider.WIKIMEDIA: wiki},
        )
        assert len(bundle.plan.questions) == 2
        for question in bundle.plan.questions:
            assert {query.provider for query in question.strategy.queries} == {
                SearchProvider.ARXIV,
                SearchProvider.WIKIMEDIA,
            }
        assert len(arxiv.queries) == 2
        assert len(wiki.queries) == 2

    async def test_evidence_still_reaches_the_report(self) -> None:
        fake = FakeProvider(SearchProvider.ARXIV, "arxiv.example")
        bundle = await _research(
            RunContext(run_id="evidence"), providers={SearchProvider.ARXIV: fake}
        )
        assert bundle.report.claims
        assert all("arxiv.example" in claim.notes for claim in bundle.report.claims)


class TestPipelineThreading:
    async def test_pipeline_passes_injected_providers_to_the_stage(self, tmp_path: Path) -> None:
        fake = FakeProvider(SearchProvider.ARXIV, "arxiv.example")
        pipeline = FactoryPipeline(
            output_dir=str(tmp_path),
            research_providers={SearchProvider.ARXIV: fake},
        )
        inputs = DiscoveryInputs(
            request="Teach me linear algebra.", subject="linear algebra", level="year 10"
        )
        result = await pipeline.run(inputs, run_id="live-sim")

        assert result.succeeded
        report = next(
            artifact for artifact in result.artifacts if artifact.artifact_type == "research_report"
        )
        assert report.verified_sources
        assert all(source.domain == "arxiv.example" for source in report.verified_sources)

    async def test_pipeline_without_providers_stays_offline(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        inputs = DiscoveryInputs(
            request="Teach me linear algebra.", subject="linear algebra", level="year 10"
        )
        result = await pipeline.run(inputs, run_id="offline")

        assert result.succeeded
        report = next(
            artifact for artifact in result.artifacts if artifact.artifact_type == "research_report"
        )
        assert {source.domain for source in report.verified_sources} == {"reference.example"}
