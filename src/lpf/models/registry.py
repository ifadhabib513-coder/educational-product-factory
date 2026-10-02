"""Prompt registry — versioned prompt templates for all agents."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptTemplate:
    """A single versioned prompt template."""

    name: str
    version: str
    system_prompt: str
    user_prompt_template: str
    description: str = ""

    def render_user(self, **kwargs: Any) -> str:
        """Render the user prompt with provided variables."""
        return self.user_prompt_template.format(**kwargs)


@dataclass
class PromptRegistry:
    """Registry of versioned prompt templates.

    Loads from YAML files or accepts programmatic registration.
    """

    _templates: dict[str, PromptTemplate] = field(default_factory=dict)
    _versions: dict[str, str] = field(default_factory=dict)  # name → current version

    def register(self, template: PromptTemplate) -> None:
        """Register a prompt template."""
        key = f"{template.name}:v{template.version}"
        self._templates[key] = template
        self._versions[template.name] = template.version
        logger.debug("Registered prompt: %s (v%s)", template.name, template.version)

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        """Get a prompt template by name and optional version.

        If version is None, returns the current (latest) version.
        """
        if version is None:
            version = self._versions.get(name)
            if version is None:
                raise KeyError(f"No prompt registered with name '{name}'")
        key = f"{name}:v{version}"
        template = self._templates.get(key)
        if template is None:
            raise KeyError(f"No prompt registered: {key}")
        return template

    def list_prompts(self) -> list[str]:
        """List all registered prompt names."""
        return sorted(self._versions.keys())

    def list_versions(self, name: str) -> list[str]:
        """List all versions of a prompt."""
        versions = [k.split(":v", 1)[1] for k in self._templates if k.startswith(f"{name}:v")]
        return sorted(versions)

    def load_from_directory(self, directory: str | Path) -> int:
        """Load prompt templates from a directory of JSON files.

        Each file should be a JSON object with:
        name, version, system_prompt, user_prompt_template, description

        Returns the number of templates loaded.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            return 0

        count = 0
        for file_path in sorted(dir_path.glob("*.json")):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                template = PromptTemplate(**data)
                self.register(template)
                count += 1
            except Exception:
                logger.warning("Failed to load prompt from %s", file_path)

        return count
