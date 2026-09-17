"""Typed configuration with explicit environment-variable loading.

Uses a plain frozen dataclass. Environment variables are read explicitly in
load_config(), not via pydantic-settings or magic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LpfConfig:
    """Application configuration."""

    log_level: str = "INFO"
    output_dir: str = "projects"
    provider: str = "mock"
    timeout_seconds: int = 120


def load_config() -> LpfConfig:
    """Load configuration from environment variables.

    Environment variables (all optional):
        LPF_LOG_LEVEL   — log level (default: INFO)
        LPF_OUTPUT_DIR  — output directory (default: projects)
        LPF_PROVIDER    — LLM provider name (default: mock)
        LPF_TIMEOUT     — timeout in seconds (default: 120)
    """
    return LpfConfig(
        log_level=os.environ.get("LPF_LOG_LEVEL", "INFO"),
        output_dir=os.environ.get("LPF_OUTPUT_DIR", "projects"),
        provider=os.environ.get("LPF_PROVIDER", "mock"),
        timeout_seconds=int(os.environ.get("LPF_TIMEOUT", "120")),
    )
