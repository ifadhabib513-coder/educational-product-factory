"""OpenCode server chat adapter.

Targets a locally running ``opencode serve`` instance. Uses the OpenCode
session/message API to send prompts and receive responses. Structured output
is requested via a system prompt instructing JSON output, then parsed and
validated against the provided Pydantic schema.

The session is created on first use and reused for the lifetime of the adapter.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from lpf.errors import ProviderError
from lpf.models.providers.base import HttpChatModel
from lpf.research.transport import RetryPolicy

logger = logging.getLogger(__name__)

__all__ = ["OpenCodeServerModel"]

_STRUCTURED_SYSTEM_PROMPT = (
    "You are a precise JSON generator. Output ONLY a single valid JSON object "
    "that conforms to the schema implied by the user's request. No markdown, "
    "no commentary, no extra keys. If you cannot produce valid JSON, respond "
    "with an empty object {}."
)


class OpenCodeServerModel(HttpChatModel):
    """A model reached via a local OpenCode server."""

    kind = "opencode-server"
    endpoint = "/session"
    default_model = "big-pickle"
    default_base_url = "http://127.0.0.1:4120"

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
        provider_id: str = "opencode",
    ) -> None:
        super().__init__(
            model=model,
            base_url=base_url,
            api_key=api_key,
            client=client,
            retry=retry,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self.provider_id = provider_id
        self._session_id: str | None = None

    def request_headers(self) -> dict[str, str]:
        return {}

    def json_request_field(self) -> dict[str, Any]:
        return {}

    def parse_content(self, payload: object) -> str:
        raise NotImplementedError("OpenCodeServerModel uses custom generate()")

    async def _ensure_session(self) -> str:
        """Create a session on first use, return its ID."""
        if self._session_id is not None:
            return self._session_id

        url = f"{self.base_url}{self.endpoint}"
        try:
            response = await self._client.post(url, json={})
        except httpx.HTTPError as exc:
            raise ProviderError(
                code="OPENCODE_SESSION_CREATE_FAILED",
                message="Failed to create OpenCode session.",
                details={"endpoint": url, "error": str(exc)},
            ) from exc

        if response.is_error:
            raise ProviderError(
                code="OPENCODE_SESSION_CREATE_FAILED",
                message=f"OpenCode session creation returned HTTP {response.status_code}.",
                details={"status_code": response.status_code, "body": response.text[:500]},
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                code="OPENCODE_SESSION_RESPONSE_NOT_JSON",
                message="OpenCode session response is not valid JSON.",
                details={"body": response.text[:500]},
            ) from exc

        session_id = data.get("id")
        if not session_id:
            raise ProviderError(
                code="OPENCODE_SESSION_MISSING_ID",
                message="OpenCode session response missing 'id' field.",
                details={"payload": data},
            )

        self._session_id = session_id
        logger.debug("Created OpenCode session %s", session_id)
        return session_id

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str | BaseModel:
        session_id = await self._ensure_session()

        parts = [{"type": "text", "text": m["content"]} for m in messages if m.get("content")]

        if schema is not None:
            parts.insert(0, {"type": "text", "text": _STRUCTURED_SYSTEM_PROMPT})

        body: dict[str, Any] = {"parts": parts}
        if model is not None:
            body["model"] = {"providerID": self.provider_id, "modelID": model}
        elif self.model:
            body["model"] = {"providerID": self.provider_id, "modelID": self.model}

        url = f"{self.base_url}/session/{session_id}/message"
        response = await self._post(url, body=body)

        if response.is_error:
            raise ProviderError(
                code="OPENCODE_MESSAGE_FAILED",
                message=f"OpenCode message returned HTTP {response.status_code}.",
                details={"status_code": response.status_code, "body": response.text[:500]},
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                code="OPENCODE_RESPONSE_NOT_JSON",
                message="OpenCode response is not valid JSON.",
                details={"endpoint": url, "body": response.text[:500]},
            ) from exc

        content = self._extract_text(data)
        if schema is None:
            return content
        return self._validate_structured(content, schema)

    def _extract_text(self, payload: dict[str, Any]) -> str:
        parts = payload.get("parts")
        if not isinstance(parts, list):
            raise ProviderError(
                code="OPENCODE_RESPONSE_MALFORMED",
                message="OpenCode response missing 'parts' array.",
                details={"payload_preview": repr(payload)[:500]},
            )

        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    return text

        raise ProviderError(
            code="OPENCODE_RESPONSE_MALFORMED",
            message="OpenCode response contains no text part.",
            details={"payload_preview": repr(payload)[:500]},
        )

    async def aclose(self) -> None:
        if self._session_id and self._owns_client:
            url = f"{self.base_url}/session/{self._session_id}"
            try:
                await self._client.delete(url)
                logger.debug("Deleted OpenCode session %s", self._session_id)
            except (httpx.HTTPError, RuntimeError):
                pass
        await super().aclose()
