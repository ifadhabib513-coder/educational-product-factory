"""Domain error types for the product factory.

Error hierarchy for expected, recoverable failures. Each error carries a
machine-readable code, a human-readable message, and optional structured details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LpfError(Exception):
    """Base error for all product-factory domain errors."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigError(LpfError):
    """Configuration loading or validation failed."""


class ValidationError(LpfError):
    """Schema or data validation failed."""


class WorkflowError(LpfError):
    """Workflow state transition or execution failed."""


class ProviderError(LpfError):
    """LLM provider call failed or returned invalid data."""


class RenderingError(LpfError):
    """Artifact rendering (PDF, HTML, etc.) failed."""


class VerificationError(LpfError):
    """Post-generation verification failed."""
