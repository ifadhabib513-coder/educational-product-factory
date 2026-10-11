"""Identity and content-hash utilities for domain artifacts."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def new_id() -> str:
    """Generate a new UUID4 hex string."""
    return uuid.uuid4().hex


def seeded_id(*parts: str) -> str:
    """Deterministic 32-hex id derived from the given string parts.

    The same parts always yield the same id (``sha256(parts)`` truncated to
    32 hex chars), so identically-shaped live provider responses produce
    byte-identical runs. Reserve this for ids that are a pure function of the
    source content — e.g. ``seeded_id(provider, url)`` — and keep
    :func:`new_id` for genuinely unique instances.
    """
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def compute_content_hash(model: BaseModel) -> str:
    """Compute SHA-256 content hash over canonical JSON of the model.

    Excludes the 'content_hash' field itself. Uses compact separators,
    sorted keys, and ensure_ascii=False for reproducibility.
    """
    data = model.model_dump(mode="json", exclude={"content_hash"})
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def with_content_hash(model: T) -> T:
    """Return a copy of the model with content_hash set.

    The model must be a frozen Pydantic BaseModel with a content_hash field.
    """
    h = compute_content_hash(model)
    return model.model_copy(update={"content_hash": h})
