"""Run context — deterministic identity and clock for a factory run.

Artifacts default to ``uuid4`` ids and ``datetime.now``. Both would make a run
irreproducible, so every stage constructs artifacts through this context instead.
Given the same seed and inputs, a run produces byte-identical artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# A fixed, arbitrary epoch. Fixed rather than ``now()`` so runs are reproducible;
# the value itself carries no meaning.
_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


@dataclass
class RunContext:
    """Deterministic source of ids and timestamps for one pipeline run."""

    run_id: str
    seed: str = "default"
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
