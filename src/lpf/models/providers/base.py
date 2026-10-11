"""Shared HTTP chat-completion model for live LLM providers.

Implements the :class:`~lpf.models.provider.ModelProvider` protocol over a
plain HTTP POST to a chat endpoint. Subclasses supply the wire details (the
endpoint path, request headers, the payload field that asks a vendor for JSON,
and how to pull the message text out of the vendor response) so the vendors
never leak into the stages.

Structured output: when a Pydantic schema is passed, the request asks the
vendor for JSON and the response body is parsed and validated with ``schema``.
A malformed reply produces a typed :class:`lpf.errors.ValidationError` (a
``LpfError``), so the pipeline fails the run with a readable reason instead of
shipping a garbage artifact. Transport failures raise
:class:`lpf.errors.ProviderError`.

The HTTP client is injectable so tests can substitute ``httpx.MockTransport``
and stay offline; when none is supplied a real client with a timeout is built.
Transport failures and retryable status codes are retried with bounded,
deterministic backoff (reusing ``RetryPolicy`` from the research transport); a
provider that stays down surfaces a stable :class:`lpf.errors.ProviderError`
instead of crashing or hanging the run.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from lpf.errors import ProviderError, ValidationError
from lpf.research.transport import DEFAULT_RETRY, RetryPolicy

logger = logging.getLogger(__name__)

__all__ = ["HttpChatModel"]


def _default_client(timeout_seconds: float = 60.0) -> httpx.AsyncClient:
    """A plain client with a sane timeout, used when no client is injected."""
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))


class HttpChatModel:
    """A chat-completion LLM reached over HTTP(S).

    All PyPI-visible behaviour lives here; subclasses only describe their
    vendor's wire format.
    """

    kind = "http_chat"
    endpoint = "/"
    default_model = "model"
    default_base_url = "http://localhost"

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        retry: RetryPolicy | None = None,
        timeout_seconds: float = 60.0,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> None:
        self.model = model or self.default_model
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.api_key = api_key
        self.retry = retry or DEFAULT_RETRY
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._owns_client = client is None
        self._client = client or _default_client(timeout_seconds)

    async def aclose(self) -> None:
        """Close the HTTP client, but only if this model created it.

        An injected client (e.g. a test ``MockTransport``) belongs to the
        caller; closing it here would break a caller that reuses it.
        """
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------ wire
    def request_headers(self) -> dict[str, str]:
        """Headers sent with every request, e.g. an ``Authorization`` key."""
        return {}

    def json_request_field(self) -> dict[str, Any]:
        """Payload field that asks the vendor for JSON output.

        Returns an empty mapping by default; subclasses override it so that a
        structured call asks the vendor for machine-readable JSON.
        """
        return {}

    def parse_content(self, payload: object) -> str:
        """Extract the assistant text from a decoded vendor response."""
        raise NotImplementedError

    # ------------------------------------------------------------- provider
    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str | BaseModel:
        """POST a chat completion and return text or a validated model.

        ``temperature`` from the caller wins; the constructor value is used
        only when the caller leaves it at the protocol default of ``0.0``.
        """
        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature != 0.0 else self.temperature,
        }
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        if effective_max_tokens is not None:
            body["max_tokens"] = effective_max_tokens
        if schema is not None:
            body.update(self.json_request_field())

        url = f"{self.base_url}{self.endpoint}"
        response = await self._post(url, body=body)

        if response.is_error:
            raise ProviderError(
                code="PROVIDER_HTTP_ERROR",
                message=f"{self.endpoint} returned HTTP {response.status_code}.",
                details={"status_code": response.status_code, "body": response.text[:500]},
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                code="PROVIDER_RESPONSE_NOT_JSON",
                message="Provider returned a non-JSON response body.",
                details={"endpoint": self.endpoint, "body": response.text[:500]},
            ) from exc

        content = self.parse_content(payload)
        if schema is None:
            return content
        return self._validate_structured(content, schema)

    async def _post(self, url: str, *, body: dict[str, Any]) -> httpx.Response:
        """POST ``body`` to ``url`` with bounded retry and deterministic backoff.

        Transport failures and retryable status codes (``retry_on_status``) are
        retried, mirroring the research transport's policy. A 4xx other than
        429 is never retried: it cannot succeed on replay, so it returns now
        and the caller raises ``PROVIDER_HTTP_ERROR``. When every attempt
        fails, a ``ProviderError`` names how many attempts were made, keeping
        the failure readable and deterministic.
        """
        last_failure = "no attempt made"
        max_attempts = self.retry.max_attempts

        for attempt in range(1, max_attempts + 1):
            delay = self.retry.delay_for(attempt)
            if delay > 0:
                logger.warning(
                    "Retrying %s in %.2fs (attempt %d/%d)",
                    url,
                    delay,
                    attempt,
                    max_attempts,
                )
                await asyncio.sleep(delay)

            try:
                response = await self._client.post(
                    url,
                    json=body,
                    headers=self.request_headers(),
                )
            except httpx.HTTPError as exc:
                last_failure = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Model request to %s failed (attempt %d/%d): %s",
                    url,
                    attempt,
                    max_attempts,
                    exc,
                )
                continue

            if response.status_code in self.retry.retry_on_status:
                last_failure = f"HTTP {response.status_code}"
                logger.warning(
                    "Retryable status %d from %s (attempt %d/%d)",
                    response.status_code,
                    url,
                    attempt,
                    max_attempts,
                )
                continue

            return response

        raise ProviderError(
            code="PROVIDER_REQUEST_FAILED",
            message=(
                f"Model request to {self.base_url} failed after "
                f"{max_attempts} attempt(s); last failure: {last_failure}."
            ),
            details={"last_failure": last_failure, "endpoint": self.endpoint},
        )

    async def count_tokens(self, text: str) -> int:
        """Whitespace token estimate, matching the offline model."""
        return len(text.split())

    # ------------------------------------------------------------ structured
    @staticmethod
    def _validate_structured(content: str, schema: type[BaseModel]) -> BaseModel:
        """Parse and validate a structured reply, raising ``ValidationError``."""
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValidationError(
                code="MODEL_OUTPUT_NOT_JSON",
                message="Model returned content that is not valid JSON.",
                details={"content_preview": content[:500]},
            ) from exc

        if not isinstance(data, dict):
            raise ValidationError(
                code="MODEL_OUTPUT_NOT_JSON",
                message="Model returned JSON that is not an object.",
                details={"json_type": type(data).__name__},
            )

        try:
            return schema.model_validate(data)
        except PydanticValidationError as exc:
            raise ValidationError(
                code="MODEL_OUTPUT_INVALID_SCHEMA",
                message=f"Model output does not match schema '{schema.__name__}'.",
                details={"errors": exc.errors(include_url=False)},
            ) from exc
