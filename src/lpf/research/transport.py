"""HTTP transport for research providers — timeout, retry, and rate limiting.

Every real provider goes through :class:`HttpTransport` so that one place owns
retry policy and rate limiting. Backoff is deterministic (no jitter) to keep
provider behaviour reproducible under test.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


class TransportError(RuntimeError):
    """Raised when a request cannot be completed after retries."""


@dataclass(frozen=True)
class RetryPolicy:
    """Retry behaviour for a transport.

    ``retry_on_status`` holds the status codes worth retrying. 4xx other than
    429 is deliberately absent: a 404 or 401 will not become a 200 on retry, and
    retrying it only burns the rate limit.
    """

    max_attempts: int = 3
    backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 8.0
    retry_on_status: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )

    def delay_for(self, attempt: int) -> float:
        """Backoff before attempt ``attempt`` (1-based; attempt 1 waits 0)."""
        if attempt <= 1:
            return 0.0
        delay = self.backoff_seconds * (self.backoff_multiplier ** (attempt - 2))
        return min(delay, self.max_backoff_seconds)


DEFAULT_RETRY = RetryPolicy()


class RateLimiter:
    """Simple minimum-interval limiter shared across concurrent requests.

    Serialises call starts so N concurrent tasks cannot burst past a provider's
    published rate limit.
    """

    def __init__(self, min_interval_seconds: float = 0.0) -> None:
        self._min_interval = min_interval_seconds
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0
        self._loop_time = 0.0

    async def acquire(self) -> None:
        """Wait until the next call is permitted."""
        if self._min_interval <= 0:
            return

        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            self._loop_time = max(now, self._next_allowed)
            self._next_allowed = self._loop_time + self._min_interval
        delay = self._loop_time - now
        if delay > 0:
            await asyncio.sleep(delay)


@dataclass
class HttpTransport:
    """Shared httpx client with retry and rate limiting."""

    client: httpx.AsyncClient
    retry: RetryPolicy = DEFAULT_RETRY
    rate_limiter: RateLimiter = field(default_factory=RateLimiter)

    async def get_json(self, url: str, params: dict | None = None) -> object:
        """GET and parse a JSON body, retrying retryable failures."""
        return await self._request(url, params=params, parse="json")

    async def get_text(self, url: str, params: dict | None = None) -> str:
        """GET and return the raw body as text."""
        return str(await self._request(url, params=params, parse="text"))

    async def post_json(self, url: str, payload: dict, headers: dict | None = None) -> object:
        """POST a JSON body and parse a JSON response."""
        return await self._request(
            url, method="POST", payload=payload, headers=headers, parse="json"
        )

    async def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict | None = None,
        payload: dict | None = None,
        headers: dict | None = None,
        parse: str = "json",
    ) -> object:
        last_error: Exception | None = None

        for attempt in range(1, self.retry.max_attempts + 1):
            await self.rate_limiter.acquire()
            delay = self.retry.delay_for(attempt)
            if delay > 0:
                logger.debug(
                    "Retrying %s %s in %.2fs (attempt %d/%d)",
                    method,
                    url,
                    delay,
                    attempt,
                    self.retry.max_attempts,
                )
                await asyncio.sleep(delay)

            try:
                response = await self.client.request(
                    method, url, params=params, json=payload, headers=headers
                )
            except httpx.HTTPError as e:
                last_error = e
                logger.warning("Transport error for %s (attempt %d): %s", url, attempt, e)
                continue

            if response.status_code in self.retry.retry_on_status:
                last_error = TransportError(f"{response.status_code} from {url}")
                logger.warning(
                    "Retryable status %d from %s (attempt %d/%d)",
                    response.status_code,
                    url,
                    attempt,
                    self.retry.max_attempts,
                )
                continue

            if response.is_error:
                raise TransportError(f"{response.status_code} from {url}: {response.text[:200]}")

            if parse == "json":
                try:
                    return response.json()
                except ValueError as e:
                    raise TransportError(f"Malformed JSON from {url}: {e}") from e
            return response.text

        raise TransportError(
            f"{method} {url} failed after {self.retry.max_attempts} attempts"
        ) from last_error


def build_client(
    *,
    timeout_seconds: float = 20.0,
    user_agent: str = "lpf-research/0.1",
    headers: dict | None = None,
) -> httpx.AsyncClient:
    """Create an AsyncClient configured for research providers.

    Redirects are capped and the client is created without a connection pool
    size override so httpx uses sensible defaults.
    """
    merged = {"User-Agent": user_agent, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        headers=merged,
        follow_redirects=True,
        max_redirects=5,
    )
