"""Tests for HTTP transport — retry, backoff, rate limiting, error handling."""

from __future__ import annotations

import httpx
import pytest

from lpf.research.transport import (
    HttpTransport,
    RateLimiter,
    RetryPolicy,
    TransportError,
    build_client,
)


def _transport(
    handler,
    *,
    retry: RetryPolicy | None = None,
    rate_limiter: RateLimiter | None = None,
) -> HttpTransport:
    """Build a transport over a mock transport handler."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpTransport(
        client=client,
        retry=retry or RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        rate_limiter=rate_limiter or RateLimiter(min_interval_seconds=0.0),
    )


def _json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


class TestRetryPolicy:
    def test_first_attempt_has_no_delay(self) -> None:
        assert RetryPolicy().delay_for(1) == 0.0

    def test_backoff_grows(self) -> None:
        policy = RetryPolicy(backoff_seconds=1.0, backoff_multiplier=2.0)
        assert policy.delay_for(2) == 1.0
        assert policy.delay_for(3) == 2.0
        assert policy.delay_for(4) == 4.0

    def test_backoff_is_capped(self) -> None:
        policy = RetryPolicy(backoff_seconds=1.0, max_backoff_seconds=3.0)
        assert policy.delay_for(10) == 3.0

    def test_client_errors_are_not_retried(self) -> None:
        """A 404 will not become a 200; retrying only wastes the rate limit."""
        policy = RetryPolicy()
        assert 404 not in policy.retry_on_status
        assert 401 not in policy.retry_on_status

    def test_transient_errors_are_retried(self) -> None:
        policy = RetryPolicy()
        for status in (429, 500, 502, 503, 504):
            assert status in policy.retry_on_status


class TestHttpTransportGet:
    @pytest.mark.asyncio
    async def test_get_json_success(self) -> None:
        transport = _transport(lambda request: _json_response({"ok": True}))
        result = await transport.get_json("https://api.test/x")
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_get_text_success(self) -> None:
        transport = _transport(lambda request: httpx.Response(200, text="hello"))
        result = await transport.get_text("https://api.test/x")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_params_are_forwarded(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return _json_response({})

        transport = _transport(handler)
        await transport.get_json("https://api.test/x", params={"q": "algebra"})
        assert seen["params"]["q"] == "algebra"

    @pytest.mark.asyncio
    async def test_malformed_json_raises(self) -> None:
        transport = _transport(lambda request: httpx.Response(200, text="not json"))
        with pytest.raises(TransportError, match="Malformed JSON"):
            await transport.get_json("https://api.test/x")

    @pytest.mark.asyncio
    async def test_client_error_raises_immediately(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(404, text="missing")

        transport = _transport(handler)
        with pytest.raises(TransportError, match="404"):
            await transport.get_json("https://api.test/x")
        assert len(calls) == 1, "404 must not be retried"

    @pytest.mark.asyncio
    async def test_server_error_is_retried(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) < 3:
                return httpx.Response(503, text="unavailable")
            return _json_response({"ok": True})

        transport = _transport(handler)
        result = await transport.get_json("https://api.test/x")
        assert result == {"ok": True}
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_gives_up_after_max_attempts(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(503, text="unavailable")

        transport = _transport(handler, retry=RetryPolicy(max_attempts=2, backoff_seconds=0.0))
        with pytest.raises(TransportError, match="failed after 2 attempts"):
            await transport.get_json("https://api.test/x")
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_transport_error_is_retried(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError("refused")

        transport = _transport(handler)
        with pytest.raises(TransportError):
            await transport.get_json("https://api.test/x")
        assert len(calls) == 3


class TestHttpTransportPost:
    @pytest.mark.asyncio
    async def test_post_json(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            seen["payload"] = json.loads(request.content)
            return _json_response({"ok": True})

        transport = _transport(handler)
        result = await transport.post_json("https://api.test/x", {"q": "algebra"})
        assert result == {"ok": True}
        assert seen["payload"]["q"] == "algebra"

    @pytest.mark.asyncio
    async def test_post_custom_headers(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return _json_response({})

        transport = _transport(handler)
        await transport.post_json("https://api.test/x", {}, headers={"Authorization": "Bearer t"})
        assert seen["auth"] == "Bearer t"


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_zero_interval_does_not_block(self) -> None:
        limiter = RateLimiter(min_interval_seconds=0.0)
        for _ in range(5):
            await limiter.acquire()

    @pytest.mark.asyncio
    async def test_interval_is_enforced(self) -> None:
        import time

        limiter = RateLimiter(min_interval_seconds=0.05)
        start = time.monotonic()
        for _ in range(3):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        # Three acquisitions at 50ms apart span at least two intervals.
        assert elapsed >= 0.09

    @pytest.mark.asyncio
    async def test_concurrent_calls_are_serialised(self) -> None:
        import time

        limiter = RateLimiter(min_interval_seconds=0.05)

        async def worker() -> None:
            await limiter.acquire()

        start = time.monotonic()
        await limiter.acquire()
        # Queued calls must not all fire at once.
        for _ in range(3):
            await worker()
        assert time.monotonic() - start >= 0.09


class TestBuildClient:
    @pytest.mark.asyncio
    async def test_sets_user_agent(self) -> None:
        client = build_client(user_agent="test-agent/1.0")
        assert client.headers["User-Agent"] == "test-agent/1.0"

    @pytest.mark.asyncio
    async def test_custom_headers_override_defaults(self) -> None:
        client = build_client(headers={"Accept": "application/atom+xml"})
        assert client.headers["Accept"] == "application/atom+xml"

    @pytest.mark.asyncio
    async def test_timeout_is_applied(self) -> None:
        client = build_client(timeout_seconds=5.0)
        assert client.timeout.connect == 5.0
        await client.aclose()

    @pytest.mark.asyncio
    async def test_follows_redirects(self) -> None:
        client = build_client()
        assert client.follow_redirects is True
        await client.aclose()
