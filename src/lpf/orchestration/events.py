"""Run event log — an append-only record of what a run did.

The log is the run's audit trail: which stage ran, which artifacts it produced,
and when, in deterministic order. It is written to disk with the run so a
completed product can be traced back to the steps that made it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lpf.orchestration.state import RunStage


class EventType(StrEnum):
    """What kind of thing happened."""

    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    #: QA rewound to an earlier stage to repair a gate failure.
    REVISION_STARTED = "revision_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True)
class RunEvent:
    """A single thing that happened during a run."""

    run_id: str
    seq: int
    event_type: EventType
    stage: RunStage
    message: str
    timestamp: datetime
    artifact_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialise for the run log file."""
        return {
            "seq": self.seq,
            "event_type": self.event_type.value,
            "stage": self.stage.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "artifact_ids": list(self.artifact_ids),
        }


@dataclass
class EventLog:
    """Collects events for one run in sequence order."""

    run_id: str
    events: list[RunEvent] = field(default_factory=list)

    def emit(
        self,
        event_type: EventType,
        *,
        stage: RunStage,
        message: str,
        timestamp: datetime,
        artifact_ids: tuple[str, ...] = (),
    ) -> RunEvent:
        """Record an event, assigning the next sequence number."""
        event = RunEvent(
            run_id=self.run_id,
            seq=len(self.events) + 1,
            event_type=event_type,
            stage=stage,
            message=message,
            timestamp=timestamp,
            artifact_ids=artifact_ids,
        )
        self.events.append(event)
        return event

    def to_dicts(self) -> list[dict[str, object]]:
        """Serialise every event for the run log file."""
        return [event.to_dict() for event in self.events]
