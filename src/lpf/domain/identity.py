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
