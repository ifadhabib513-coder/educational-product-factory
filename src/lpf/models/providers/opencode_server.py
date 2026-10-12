"""OpenCode server chat adapter.

Targets a locally running ``opencode serve`` instance. Uses the OpenCode
session/message API to send prompts and receive responses. Structured output
is requested via a schema-aware system prompt, then parsed and validated
against the provided Pydantic schema. A bounded repair loop feeds validation
errors back to the model for correction.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel

from lpf.errors import ProviderError, ValidationError
from lpf.models.providers.base import HttpChatModel
from lpf.research.transport import RetryPolicy

logger = logging.getLogger(__name__)

__all__ = ["OpenCodeServerModel"]


def _schema_to_prompt(schema: type[BaseModel]) -> str:
    """Generate a concise JSON schema description for the system prompt."""
    fields = []
    for name, field in schema.model_fields.items():
        field_type = _field_type_str(field)
        required = "required" if field.is_required() else "optional"
        desc = field.description or ""
        fields.append(f'  "{name}": {field_type} ({required}){f" - {desc}" if desc else ""}')
    return "{\n" + ",\n".join(fields) + "\n}"


def _field_type_str(field) -> str:
    """Convert a Pydantic field to a human-readable type string."""
    from typing import get_args, get_origin

    annotation = field.annotation
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is list:
        item_type = _field_type_str_from_annotation(args[0]) if args else "any"
        return f"list[{item_type}]"
    elif origin is dict:
        return "object"
    elif origin is type(None) or annotation is None:
        return "null"
    else:
        return _field_type_str_from_annotation(annotation)


def _field_type_str_from_annotation(annotation) -> str:
    from typing import get_args, get_origin

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is list:
        item_type = _field_type_str_from_annotation(args[0]) if args else "any"
        return f"list[{item_type}]"
    elif origin is dict:
        return "object"
    elif hasattr(annotation, "__name__"):
        return annotation.__name__
    elif origin is not None:
        return str(origin)
    return str(annotation)


def _extract_json(content: str) -> str:
    """Extract JSON from content, handling markdown code fences."""
    # Try to find JSON in markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    # Try to find bare JSON object
    brace_match = re.search(r"(\{.*\})", content, re.DOTALL)
    if brace_match:
        return brace_match.group(1)
    return content


class OpenCodeServerModel(HttpChatModel):
    """A model reached via a local OpenCode server."""

    kind = "opencode-server"
    endpoint = "/session"
    default_model = "big-pickle"
    default_base_url = "http://127.0.0.1:4120"

    # Max attempts for structured output repair (schema validation failures)
    MAX_STRUCTURED_RETRIES = 3

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
        if schema is None:
            return await self._generate_text(
                messages=messages, model=model, temperature=temperature, max_tokens=max_tokens
            )
        return await self._generate_structured(
            messages=messages,
            schema=schema,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _generate_text(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        session_id = await self._ensure_session()

        parts = [{"type": "text", "text": m["content"]} for m in messages if m.get("content")]

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

        return self._extract_text(data)

    async def _generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> BaseModel:
        session_id = await self._ensure_session()

        # Build schema-aware system prompt
        schema_desc = _schema_to_prompt(schema)
        system_prompt = (
            f"You are a precise JSON generator. Output ONLY a single valid JSON object "
            f"that conforms exactly to this schema:\n{schema_desc}\n\n"
            f"No markdown, no commentary, no extra keys. Every field is required unless marked optional. "
            f"Use the exact field names and types shown."
        )

        # Combine user messages into a single prompt
        user_content = "\n\n".join(m["content"] for m in messages if m.get("content"))

        parts = [
            {"type": "text", "text": system_prompt},
            {"type": "text", "text": user_content},
        ]

        body: dict[str, Any] = {"parts": parts}
        if model is not None:
            body["model"] = {"providerID": self.provider_id, "modelID": model}
        elif self.model:
            body["model"] = {"providerID": self.provider_id, "modelID": self.model}

        url = f"{self.base_url}/session/{session_id}/message"

        last_schema_error: ValidationError | None = None

        for attempt in range(self.MAX_STRUCTURED_RETRIES + 1):
            if attempt > 0 and last_schema_error is not None:
                # Repair attempt: feed validation errors back
                repair_prompt = (
                    f"Your previous response failed validation. Errors:\n"
                    f"{last_schema_error.message}\n"
                    f"Details: {json.dumps(last_schema_error.details, indent=2)}\n\n"
                    f"Output ONLY the corrected JSON object. No explanations."
                )
                parts = [
                    {"type": "text", "text": system_prompt},
                    {"type": "text", "text": user_content},
                    {"type": "text", "text": repair_prompt},
                ]
                body = {"parts": parts}
                if model is not None:
                    body["model"] = {"providerID": self.provider_id, "modelID": model}
                elif self.model:
                    body["model"] = {"providerID": self.provider_id, "modelID": self.model}
                logger.debug("Structured output repair attempt %d/%d", attempt, self.MAX_STRUCTURED_RETRIES)

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

            # Step 1: Extract and parse JSON - fatal errors, no retry
            try:
                json_content = _extract_json(content)
                data_obj = json.loads(json_content)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValidationError(
                    code="MODEL_OUTPUT_NOT_JSON",
                    message="Model returned content that is not valid JSON.",
                    details={"content_preview": content[:500]},
                ) from exc

            if not isinstance(data_obj, dict):
                raise ValidationError(
                    code="MODEL_OUTPUT_NOT_JSON",
                    message="Model returned JSON that is not an object.",
                    details={"json_type": type(data_obj).__name__},
                )

            # Step 2: Validate against schema - schema mismatches can be retried
            try:
                return schema.model_validate(data_obj)
            except Exception as exc:  # PydanticValidationError
                from pydantic import ValidationError as PydanticValidationError
                if not isinstance(exc, PydanticValidationError):
                    raise
                last_schema_error = ValidationError(
                    code="MODEL_OUTPUT_INVALID_SCHEMA",
                    message=f"Model output does not match schema '{schema.__name__}'.",
                    details={"errors": exc.errors(include_url=False)},
                )

                if attempt == self.MAX_STRUCTURED_RETRIES:
                    raise ValidationError(
                        code="MODEL_OUTPUT_INVALID_SCHEMA",
                        message=(
                            f"Model output does not match schema '{schema.__name__}' "
                            f"after {self.MAX_STRUCTURED_RETRIES + 1} attempt(s)."
                        ),
                        details={"errors": last_schema_error.details.get("errors"), "attempts": attempt + 1},
                    ) from exc
                # Continue to repair loop
                continue

        # Should not reach here
        raise ValidationError(
            code="MODEL_OUTPUT_INVALID_SCHEMA",
            message=f"Model output does not match schema '{schema.__name__}' after all retries.",
            details={"attempts": self.MAX_STRUCTURED_RETRIES + 1},
        )

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
