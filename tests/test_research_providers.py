"""Tests for the four real research provider adapters."""

from __future__ import annotations

import httpx
import pytest

from lpf.research.providers.arxiv import ArxivProvider
from lpf.research.providers.searxng import SearxngProvider
from lpf.research.providers.tavily import TavilyProvider
from lpf.research.providers.wikimedia import WikimediaProvider
from lpf.research.transport import HttpTransport, RateLimiter, RetryPolicy, TransportError
from lpf.schemas.research import SearchProvider, SourceAuthority


def _transport(handler, *, status: int = 200, text: str | None = None) -> HttpTransport:
    """Transport over a mock handler returning JSON or raw text."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpTransport(
        client=client,
        retry=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
        rate_limiter=RateLimiter(min_interval_seconds=0.0),
    )


def _json(payload: object) -> callable:
    return lambda request: httpx.Response(200, json=payload)


def _raw(text: str) -> callable:
    return lambda request: httpx.Response(200, text=text)


# ---------------------------------------------------------------------------
# SearXNG
# ---------------------------------------------------------------------------


SEARXNG_PAYLOAD = {
    "results": [
        {
            "url": "https://en.wikipedia.org/wiki/Algebra",
            "title": "Algebra",
            "content": "Algebra is the study of symbols and their operations.",
        },
        {
            "url": "https://arxiv.org/abs/2401.00001",
            "title": "On Algebraic Reasoning",
            "content": "We study algebraic reasoning in learners.",
        },
    ]
}


class TestSearxngProvider:
    @pytest.mark.asyncio
    async def test_search_returns_normalized_results(self) -> None:
        provider = SearxngProvider(transport=_transport(_json(SEARXNG_PAYLOAD)))
        results = await provider.search("algebra")
        assert len(results) == 2
        assert results[0].url == "https://en.wikipedia.org/wiki/Algebra"

    @pytest.mark.asyncio
    async def test_authority_is_classified(self) -> None:
        provider = SearxngProvider(transport=_transport(_json(SEARXNG_PAYLOAD)))
        results = await provider.search("algebra")
        by_url = {r.url: r.authority for r in results}
        assert by_url["https://en.wikipedia.org/wiki/Algebra"] is SourceAuthority.SECONDARY
        assert by_url["https://arxiv.org/abs/2401.00001"] is SourceAuthority.ACADEMIC

    @pytest.mark.asyncio
    async def test_domain_is_extracted(self) -> None:
        provider = SearxngProvider(transport=_transport(_json(SEARXNG_PAYLOAD)))
        results = await provider.search("algebra")
        assert results[0].domain == "en.wikipedia.org"

    @pytest.mark.asyncio
    async def test_respects_max_results(self) -> None:
        provider = SearxngProvider(transport=_transport(_json(SEARXNG_PAYLOAD)))
        assert len(await provider.search("algebra", max_results=1)) == 1

    @pytest.mark.asyncio
    async def test_sends_json_format_param(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json=SEARXNG_PAYLOAD)

        provider = SearxngProvider(transport=_transport(handler))
        await provider.search("algebra")
        assert seen["params"]["format"] == "json"
        assert seen["params"]["q"] == "algebra"

    @pytest.mark.asyncio
    async def test_empty_results_list(self) -> None:
        provider = SearxngProvider(transport=_transport(_json({"results": []})))
        assert await provider.search("nothing") == []

    @pytest.mark.asyncio
    async def test_missing_results_key(self) -> None:
        provider = SearxngProvider(transport=_transport(_json({})))
        assert await provider.search("nothing") == []

    @pytest.mark.asyncio
    async def test_non_dict_items_are_skipped(self) -> None:
        provider = SearxngProvider(
            transport=_transport(
                _json(
                    {
                        "results": [
                            "garbage",
                            {"url": "https://arxiv.org/a", "title": "T", "content": "C"},
                        ]
                    }
                )
            )
        )
        results = await provider.search("algebra")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_unexpected_payload_raises(self) -> None:
        provider = SearxngProvider(transport=_transport(_json(["a", "b"])))
        with pytest.raises(TransportError, match="Unexpected SearXNG payload"):
            await provider.search("algebra")

    @pytest.mark.asyncio
    async def test_extract_returns_empty_for_fallback(self) -> None:
        provider = SearxngProvider(transport=_transport(_json({})))
        assert await provider.extract("https://example.com") == ""

    def test_provider_name(self) -> None:
        assert (
            SearxngProvider(transport=_transport(_json({}))).provider_name is SearchProvider.SEARXNG
        )

    @pytest.mark.asyncio
    async def test_missing_title_falls_back_to_url(self) -> None:
        payload = {"results": [{"url": "https://arxiv.org/a", "content": "C"}]}
        provider = SearxngProvider(transport=_transport(_json(payload)))
        results = await provider.search("algebra")
        assert results[0].title == "https://arxiv.org/a"


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------


TAVILY_PAYLOAD = {
    "results": [
        {
            "url": "https://www.nasa.gov/mars",
            "title": "Mars",
            "content": "Mars is the fourth planet from the Sun.",
            "score": 0.92,
            "published_date": "2024-03-15T00:00:00Z",
        },
        {
            "url": "https://www.quora.com/mars",
            "title": "Mars on Quora",
            "content": "Discussion about Mars.",
            "score": 0.4,
        },
    ]
}


class TestTavilyProvider:
    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        provider = TavilyProvider("key", transport=_transport(_json(TAVILY_PAYLOAD)))
        results = await provider.search("mars")
        assert len(results) == 2
        assert results[0].title == "Mars"

    @pytest.mark.asyncio
    async def test_requires_api_key(self) -> None:
        with pytest.raises(ValueError, match="requires an API key"):
            TavilyProvider("")

    @pytest.mark.asyncio
    async def test_score_is_preserved(self) -> None:
        provider = TavilyProvider("key", transport=_transport(_json(TAVILY_PAYLOAD)))
        results = await provider.search("mars")
        assert results[0].relevance_score == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_authority_classified(self) -> None:
        provider = TavilyProvider("key", transport=_transport(_json(TAVILY_PAYLOAD)))
        results = await provider.search("mars")
        assert results[0].authority is SourceAuthority.INSTITUTIONAL
        assert results[1].authority is SourceAuthority.GENERAL

    @pytest.mark.asyncio
    async def test_published_date_parsed(self) -> None:
        provider = TavilyProvider("key", transport=_transport(_json(TAVILY_PAYLOAD)))
        results = await provider.search("mars")
        assert results[0].published_at is not None
        assert results[0].published_at.year == 2024

    @pytest.mark.asyncio
    async def test_missing_score_defaults_to_zero(self) -> None:
        payload = {"results": [{"url": "https://arxiv.org/a", "content": "C"}]}
        provider = TavilyProvider("key", transport=_transport(_json(payload)))
        results = await provider.search("x")
        assert results[0].relevance_score == 0.0

    @pytest.mark.asyncio
    async def test_malformed_score_defaults_to_zero(self) -> None:
        payload = {"results": [{"url": "https://arxiv.org/a", "content": "C", "score": "high"}]}
        provider = TavilyProvider("key", transport=_transport(_json(payload)))
        assert (await provider.search("x"))[0].relevance_score == 0.0

    @pytest.mark.asyncio
    async def test_out_of_range_score_is_clamped(self) -> None:
        payload = {"results": [{"url": "https://arxiv.org/a", "content": "C", "score": 5.0}]}
        provider = TavilyProvider("key", transport=_transport(_json(payload)))
        assert (await provider.search("x"))[0].relevance_score == 1.0

    @pytest.mark.asyncio
    async def test_bad_published_date_yields_none(self) -> None:
        payload = {
            "results": [
                {"url": "https://arxiv.org/a", "content": "C", "published_date": "not a date"}
            ]
        }
        provider = TavilyProvider("key", transport=_transport(_json(payload)))
        assert (await provider.search("x"))[0].published_at is None

    @pytest.mark.asyncio
    async def test_extract_returns_content(self) -> None:
        payload = {"results": [{"raw_content": "Extracted page text."}]}
        provider = TavilyProvider("key", transport=_transport(_json(payload)))
        assert await provider.extract("https://example.com") == "Extracted page text."

    @pytest.mark.asyncio
    async def test_extract_truncates(self) -> None:
        payload = {"results": [{"raw_content": "x" * 5000}]}
        provider = TavilyProvider(
            "key", transport=_transport(_json(payload)), max_extracted_chars=100
        )
        assert len(await provider.extract("https://example.com")) == 100

    @pytest.mark.asyncio
    async def test_extract_empty_results(self) -> None:
        provider = TavilyProvider("key", transport=_transport(_json({"results": []})))
        assert await provider.extract("https://example.com") == ""

    @pytest.mark.asyncio
    async def test_api_key_is_sent(self) -> None:
        import json

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json=TAVILY_PAYLOAD)

        provider = TavilyProvider("secret-key", transport=_transport(handler))
        await provider.search("mars")
        assert seen["payload"]["api_key"] == "secret-key"

    def test_provider_name(self) -> None:
        provider = TavilyProvider("k", transport=_transport(_json({})))
        assert provider.provider_name is SearchProvider.TAVILY


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------


ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Algebraic
    Reasoning in Learners</title>
    <summary>We present a study of how
    learners reason algebraically.</summary>
    <published>2024-01-01T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <title>Second Paper</title>
    <summary>Another abstract.</summary>
    <published>2024-02-01T12:00:00Z</published>
  </entry>
</feed>"""


class TestArxivProvider:
    @pytest.mark.asyncio
    async def test_search_parses_atom(self) -> None:
        provider = ArxivProvider(transport=_transport(_raw(ARXIV_FEED)))
        results = await provider.search("algebra")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_whitespace_is_collapsed(self) -> None:
        provider = ArxivProvider(transport=_transport(_raw(ARXIV_FEED)))
        results = await provider.search("algebra")
        assert results[0].title == "Algebraic Reasoning in Learners"
        assert "\n" not in results[0].snippet

    @pytest.mark.asyncio
    async def test_results_are_academic(self) -> None:
        provider = ArxivProvider(transport=_transport(_raw(ARXIV_FEED)))
        results = await provider.search("algebra")
        assert all(r.authority is SourceAuthority.ACADEMIC for r in results)

    @pytest.mark.asyncio
    async def test_published_date_parsed(self) -> None:
        provider = ArxivProvider(transport=_transport(_raw(ARXIV_FEED)))
        results = await provider.search("algebra")
        assert results[0].published_at is not None
        assert results[0].published_at.year == 2024

    @pytest.mark.asyncio
    async def test_respects_max_results(self) -> None:
        provider = ArxivProvider(transport=_transport(_raw(ARXIV_FEED)))
        assert len(await provider.search("algebra", max_results=1)) == 1

    @pytest.mark.asyncio
    async def test_malformed_xml_returns_empty(self) -> None:
        """A broken feed must not abort research that already has other results."""
        provider = ArxivProvider(transport=_transport(_raw("<not-xml")))
        assert await provider.search("algebra") == []

    @pytest.mark.asyncio
    async def test_empty_feed(self) -> None:
        feed = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        provider = ArxivProvider(transport=_transport(_raw(feed)))
        assert await provider.search("algebra") == []

    @pytest.mark.asyncio
    async def test_sends_all_prefixed_query(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, text=ARXIV_FEED)

        provider = ArxivProvider(transport=_transport(handler))
        await provider.search("algebra")
        assert seen["params"]["search_query"] == "all:algebra"

    @pytest.mark.asyncio
    async def test_long_query_is_truncated(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, text=ARXIV_FEED)

        provider = ArxivProvider(transport=_transport(handler), max_query_chars=20)
        await provider.search("x" * 500)
        assert len(seen["params"]["search_query"]) <= 20

    @pytest.mark.asyncio
    async def test_entry_without_id_still_parsed(self) -> None:
        feed = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>No Id</title><summary>Summary.</summary></entry>
        </feed>"""
        provider = ArxivProvider(transport=_transport(_raw(feed)))
        results = await provider.search("x")
        assert len(results) == 1
        assert results[0].authority is SourceAuthority.ACADEMIC

    def test_provider_name(self) -> None:
        provider = ArxivProvider(transport=_transport(_raw("")))
        assert provider.provider_name is SearchProvider.ARXIV


# ---------------------------------------------------------------------------
# Wikimedia
# ---------------------------------------------------------------------------


WIKIMEDIA_PAYLOAD = {
    "query": {
        "search": [
            {
                "title": "Algebra",
                "snippet": '<span class="searchmatch">Algebra</span> is a branch of mathematics.',
            },
            {
                "title": "Linear algebra",
                "snippet": "The study of linear equations.",
            },
        ]
    }
}


class TestWikimediaUserAgentCompliance:
    """Regression: Wikimedia returns 403 without a contactable User-Agent.

    Verified live. A User-Agent ending in the prose "contact via repo" was
    refused with ``403 Please respect our robot policy``; one carrying a URL or
    email was accepted. The mocked tests below could never have caught this
    because httpx.MockTransport does not enforce Wikimedia's robot policy.
    """

    def test_user_agent_contains_a_contact(self) -> None:
        from lpf.research.providers.wikimedia import _USER_AGENT

        lowered = _USER_AGENT.lower()
        has_url = "http://" in lowered or "https://" in lowered
        has_email = "@" in _USER_AGENT
        assert has_url or has_email, (
            f"Wikimedia rejects User-Agents without a contact URL or email: {_USER_AGENT!r}"
        )

    def test_user_agent_names_the_project(self) -> None:
        from lpf.research.providers.wikimedia import _USER_AGENT

        assert "lpf" in _USER_AGENT.lower()

    def test_contact_is_overridable_by_environment(self, monkeypatch) -> None:
        import importlib

        import lpf.research.providers.wikimedia as wikimedia

        monkeypatch.setenv("LPF_RESEARCH_CONTACT", "mailto:maintainer@example.org")
        reloaded = importlib.reload(wikimedia)
        try:
            assert "maintainer@example.org" in reloaded._USER_AGENT
        finally:
            monkeypatch.delenv("LPF_RESEARCH_CONTACT", raising=False)
            importlib.reload(wikimedia)

    def test_default_client_sends_the_compliant_user_agent(self) -> None:
        provider = WikimediaProvider()
        user_agent = provider._transport.client.headers["User-Agent"]
        assert "http" in user_agent.lower() or "@" in user_agent


class TestWikimediaProvider:
    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD)))
        results = await provider.search("algebra")
        assert len(results) == 2
        assert results[0].title == "Algebra"

    @pytest.mark.asyncio
    async def test_highlight_markup_is_stripped(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD)))
        results = await provider.search("algebra")
        assert "<span" not in results[0].snippet
        assert "</span>" not in results[0].snippet

    @pytest.mark.asyncio
    async def test_authority_is_secondary(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD)))
        results = await provider.search("algebra")
        assert all(r.authority is SourceAuthority.SECONDARY for r in results)

    @pytest.mark.asyncio
    async def test_article_url_is_constructed(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD)))
        results = await provider.search("algebra")
        assert results[0].url == "https://en.wikipedia.org/wiki/Algebra"
        assert results[1].url == "https://en.wikipedia.org/wiki/Linear_algebra"

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD)), limit=1)
        assert len(await provider.search("algebra")) == 1

    @pytest.mark.asyncio
    async def test_empty_search(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json({"query": {"search": []}})))
        assert await provider.search("nothing") == []

    @pytest.mark.asyncio
    async def test_extract_returns_summary(self) -> None:
        payload = {"extract": "Algebra is a branch of mathematics."}
        provider = WikimediaProvider(transport=_transport(_json(payload)))
        assert await provider.extract("https://en.wikipedia.org/wiki/Algebra") == (
            "Algebra is a branch of mathematics."
        )

    @pytest.mark.asyncio
    async def test_extract_ignores_non_wikipedia_url(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json({})))
        assert await provider.extract("https://example.com/page") == ""

    def test_title_from_url_strips_section(self) -> None:
        assert (
            WikimediaProvider._title_from_url(
                "https://en.wikipedia.org/wiki/History_of_math#Modern"
            )
            == "History of math"
        )

    def test_title_from_url_requires_wiki_path(self) -> None:
        assert WikimediaProvider._title_from_url("https://en.wikipedia.org/") == ""

    @pytest.mark.asyncio
    async def test_missing_extract_yields_empty(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json({})))
        assert await provider.extract("https://en.wikipedia.org/wiki/Algebra") == ""

    def test_provider_name(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json({})))
        assert provider.provider_name is SearchProvider.WIKIMEDIA


# ---------------------------------------------------------------------------
# Cross-provider contract
# ---------------------------------------------------------------------------


class TestProviderContract:
    @pytest.mark.parametrize(
        "provider_factory",
        [
            lambda: SearxngProvider(transport=_transport(_json(SEARXNG_PAYLOAD))),
            lambda: TavilyProvider("k", transport=_transport(_json(TAVILY_PAYLOAD))),
            lambda: WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD))),
        ],
    )
    def test_all_satisfy_protocol(self, provider_factory) -> None:
        from lpf.research.providers.base import SearchProviderProto

        provider = provider_factory()
        assert isinstance(provider, SearchProviderProto)

    @pytest.mark.parametrize(
        "provider_factory",
        [
            lambda: SearxngProvider(transport=_transport(_json(SEARXNG_PAYLOAD))),
            lambda: TavilyProvider("k", transport=_transport(_json(TAVILY_PAYLOAD))),
            lambda: ArxivProvider(transport=_transport(_raw(ARXIV_FEED))),
            lambda: WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD))),
        ],
    )
    def test_provider_names_are_distinct(self, provider_factory) -> None:
        names = {
            SearxngProvider(transport=_transport(_json({}))).provider_name,
            TavilyProvider("k", transport=_transport(_json({}))).provider_name,
            ArxivProvider(transport=_transport(_raw(""))).provider_name,
            WikimediaProvider(transport=_transport(_json({}))).provider_name,
        }
        assert len(names) == 4
        assert provider_factory().provider_name in names

    @pytest.mark.asyncio
    async def test_source_ids_are_unique(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD)))
        results = await provider.search("algebra")
        assert len({r.source_id for r in results}) == len(results)

    @pytest.mark.asyncio
    async def test_retrieved_at_is_set(self) -> None:
        provider = WikimediaProvider(transport=_transport(_json(WIKIMEDIA_PAYLOAD)))
        results = await provider.search("algebra")
        assert all(r.retrieved_at is not None for r in results)
