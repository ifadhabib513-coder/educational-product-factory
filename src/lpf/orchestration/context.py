"""Run context — deterministic identity and clock for a factory run.

Artifacts default to ``uuid4`` ids and ``datetime.now``. Both would make a run
irreproducible, so every stage constructs artifacts through this context instead.
Given the same inputs, a run produces byte-identical artifacts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from lpf.errors import ConfigError

# A run id becomes a directory name, an archive name, and (through ``ctx.id``)
# part of every artifact filename. Restrict it to a flat, separator-free slug so
# ``..\\..\\evil`` or ``sub/nested`` cannot escape the output directory.
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_run_id(run_id: str) -> str:
    """Return ``run_id`` if it is a safe flat slug, else raise ``ConfigError``.

    Rejects path separators (both ``/`` and ``\\``), parent-directory segments,
    a leading dot, and empty or over-long ids. Called at the pipeline boundary
    so both the CLI and programmatic callers are covered.
    """
    if not _RUN_ID_PATTERN.match(run_id):
        raise ConfigError(
            code="INVALID_RUN_ID",
            message=(
                f"Invalid run id {run_id!r}: use 1-64 characters of letters, "
                "digits, '.', '_' or '-', starting with a letter or digit."
            ),
        )
    return run_id


# A fixed, arbitrary epoch. Fixed rather than ``now()`` so runs are reproducible;
# the value itself carries no meaning.
_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


@dataclass
class RunContext:
    """Deterministic source of ids and timestamps for one pipeline run."""

    run_id: str
    output_dir: str = "projects"
    _counters: dict[str, int] = field(default_factory=dict)
    _tick: int = 0

    def id(self, kind: str) -> str:
        """Return a stable, unique id of the form ``<run_id>-<kind>-<n>``.

        Numbering is per ``kind`` and monotonic, so ids do not depend on how many
        artifacts of other kinds were built first.
        """
        n = self._counters.get(kind, 0) + 1
        self._counters[kind] = n
        return f"{self.run_id}-{kind}-{n:04d}"

    def now(self) -> datetime:
        """Return a deterministic timestamp, one second later per call.

        Monotonic so that ``created_at`` ordering matches build order, which makes
        both manifests and content hashes stable across runs.
        """
        self._tick += 1
        return _EPOCH + timedelta(seconds=self._tick)

    @property
    def tick(self) -> int:
        """Number of timestamps issued so far."""
        return self._tick
