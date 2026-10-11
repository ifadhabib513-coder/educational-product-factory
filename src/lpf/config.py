"""Typed configuration with explicit environment-variable loading.

Uses a plain frozen dataclass. Environment variables are read explicitly in
load_config(), not via pydantic-settings or magic.

An optional ``lpf.toml`` in the working directory provides defaults; explicit
environment variables always win over the file. Both are optional — the
dataclass defaults keep every live provider safely turned off unless the user
asks for one.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LpfConfig:
    """Application configuration."""

    log_level: str = "INFO"
    output_dir: str = "projects"
    #: The model provider kind (``mock``, ``openai-compatible`` or ``ollama``).
    provider: str = "mock"
    timeout_seconds: int = 120
    #: Provider-side model name, e.g. ``gpt-4o-mini`` or ``llama3.2``.
    model_name: str | None = None
    #: Provider base URL, e.g. ``http://localhost:11434``.
    model_endpoint: str | None = None
    #: Provider API key when the endpoint needs one.
    api_key: str | None = None


# Environment variable -> config field. Only these are read.
_ENV_FIELDS: tuple[tuple[str, str], ...] = (
    ("LPF_LOG_LEVEL", "log_level"),
    ("LPF_OUTPUT_DIR", "output_dir"),
    ("LPF_PROVIDER", "provider"),
    ("LPF_TIMEOUT", "timeout_seconds"),
    ("LPF_MODEL_NAME", "model_name"),
    ("LPF_MODEL_ENDPOINT", "model_endpoint"),
    ("LPF_API_KEY", "api_key"),
)


def _default_config() -> dict[str, str | None]:
    """Base values: the dataclass defaults as a mutable mapping.

    String fields preserve their defaults; None fields (endpoint/key/name)
    start unset so a missing ``lpf.toml`` entry is not a needless value.
    """
    return {
        "log_level": LpfConfig.log_level,
        "output_dir": LpfConfig.output_dir,
        "provider": LpfConfig.provider,
        "timeout_seconds": str(LpfConfig.timeout_seconds),
        "model_name": None,
        "model_endpoint": None,
        "api_key": None,
    }


def _load_toml(path: Path | None) -> dict[str, str | None]:
    """Read ``[model]`` and ``[run]`` sections from ``lpf.toml``, if present.

    Returns a mapping keyed by config field name. Unknown keys are ignored so a
    forward-looking config file never breaks ``lpf``.
    """
    if path is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}

    model_section = data.get("model") or {}
    run_section = data.get("run") or {}

    toml: dict[str, str | None] = {}
    section_mapping = {
        "kind": "provider",
        "name": "model_name",
        "endpoint": "model_endpoint",
        "api_key": "api_key",
    }
    for toml_key, field_name in section_mapping.items():
        raw = model_section.get(toml_key)
        if raw is not None:
            toml[field_name] = str(raw)
    for toml_key, field_name in {
        "log_level": "log_level",
        "output_dir": "output_dir",
        "timeout": "timeout_seconds",
    }.items():
        raw = run_section.get(toml_key)
        if raw is not None:
            toml[field_name] = str(raw)
    return toml


def load_config(path: str | os.PathLike | None = None) -> LpfConfig:
    """Load configuration from ``lpf.toml`` (optional) and environment.

    Precedence, lowest to highest: dataclass defaults, ``lpf.toml``, environment
    variables. ``path`` defaults to ``lpf.toml`` in the working directory.
    """
    values = _default_config()
    toml_values = _load_toml(Path(path) if path is not None else Path("lpf.toml"))
    for field_name, value in toml_values.items():
        if value is not None:
            values[field_name] = value
    for env_name, field_name in _ENV_FIELDS:
        if env_name in os.environ:
            values[field_name] = os.environ[env_name]

    return LpfConfig(
        log_level=str(values["log_level"]),
        output_dir=str(values["output_dir"]),
        provider=str(values["provider"]),
        timeout_seconds=int(values["timeout_seconds"]),
        model_name=values["model_name"],
        model_endpoint=values["model_endpoint"],
        api_key=values["api_key"],
    )
