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
Retries and backoff are deliberately out of scope here (owned by the provider
resilience task) — a failed request raises immediately.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from lpf.errors import ProviderError, ValidationError

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
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> None:
        self.model = model or self.default_model
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = client or _default_client()

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
        try:
            response = await self._client.post(
                url,
                json=body,
                headers=self.request_headers(),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                code="PROVIDER_REQUEST_FAILED",
                message=f"Model request to {self.base_url} failed: {exc}",
                details={"endpoint": self.endpoint},
            ) from exc

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
