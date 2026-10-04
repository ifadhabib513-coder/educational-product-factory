"""Run state machine — the legal order of pipeline stages.

Stages are strictly linear. A linear machine is enough for a deterministic
mock pipeline, and it makes two bugs impossible by construction: running a stage
before its inputs exist, and silently skipping a stage. Branching, retry, and
repair loops are deliberately out of scope for this version; see ADR-008.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lpf.errors import WorkflowError


class RunStage(StrEnum):
    """Every stage a run moves through, in order."""

    CREATED = "created"
    DISCOVERY = "discovery"
    SPECIFICATION = "specification"
    RESEARCH = "research"
    SYLLABUS = "syllabus"
    CONTENT = "content"
    ASSESSMENT = "assessment"
    QA = "qa"
    PACKAGING = "packaging"
    COMPLETE = "complete"
    FAILED = "failed"


# Forward order. Each stage may only advance to its immediate successor, so a run
# cannot skip a stage whose output the next one reads.
_STAGE_ORDER: tuple[RunStage, ...] = (
    RunStage.CREATED,
    RunStage.DISCOVERY,
    RunStage.SPECIFICATION,
    RunStage.RESEARCH,
    RunStage.SYLLABUS,
    RunStage.CONTENT,
    RunStage.ASSESSMENT,
    RunStage.QA,
    RunStage.PACKAGING,
    RunStage.COMPLETE,
)

_TERMINAL: frozenset[RunStage] = frozenset({RunStage.COMPLETE, RunStage.FAILED})


def _build_transitions() -> dict[RunStage, frozenset[RunStage]]:
    """Forward edge to the successor, plus ``failed`` from every non-terminal stage."""
    transitions: dict[RunStage, set[RunStage]] = {stage: set() for stage in RunStage}
    for current, nxt in zip(_STAGE_ORDER, _STAGE_ORDER[1:], strict=False):
        transitions[current].add(nxt)
    for stage in _STAGE_ORDER:
        if stage not in _TERMINAL:
            transitions[stage].add(RunStage.FAILED)
    return {stage: frozenset(targets) for stage, targets in transitions.items()}


LEGAL_TRANSITIONS: dict[RunStage, frozenset[RunStage]] = _build_transitions()

# Order the pipeline actually executes, excluding the synthetic endpoints.
PIPELINE_STAGES: tuple[RunStage, ...] = tuple(
    stage for stage in _STAGE_ORDER if stage not in {RunStage.CREATED, RunStage.COMPLETE}
)


@dataclass(frozen=True)
class StageTransition:
    """One accepted transition, recorded for the run log."""

    from_stage: RunStage
    to_stage: RunStage
    at: datetime


@dataclass
class RunState:
    """Mutable position of a run within the stage machine."""

    run_id: str
    stage: RunStage = RunStage.CREATED
    history: list[StageTransition] = field(default_factory=list)
    failure_reason: str | None = None

    @property
    def is_terminal(self) -> bool:
        """True once the run has completed or failed."""
        return self.stage in _TERMINAL

    def can_advance(self, to_stage: RunStage) -> bool:
        """Whether a transition from the current stage would be legal."""
        return to_stage in LEGAL_TRANSITIONS[self.stage]

    def advance(self, to_stage: RunStage, *, at: datetime) -> StageTransition:
        """Move to ``to_stage``, raising ``WorkflowError`` if the move is illegal.

        Illegal transitions are a programming error, not an input error: they mean
        the pipeline tried to run a stage out of order or reuse a finished run.
        """
        if not self.can_advance(to_stage):
            allowed = sorted(s.value for s in LEGAL_TRANSITIONS[self.stage])
            raise WorkflowError(
                code="ILLEGAL_TRANSITION",
                message=(
                    f"Cannot move run {self.run_id!r} from "
                    f"'{self.stage.value}' to '{to_stage.value}'."
                ),
                details={
                    "run_id": self.run_id,
                    "from_stage": self.stage.value,
                    "to_stage": to_stage.value,
                    "allowed": allowed,
                },
            )
        transition = StageTransition(from_stage=self.stage, to_stage=to_stage, at=at)
        self.history.append(transition)
        self.stage = to_stage
        return transition

    def fail(self, reason: str, *, at: datetime) -> StageTransition:
        """Move the run to ``FAILED``, recording why.

        Converts an illegal transition into a ``WorkflowError`` if the run is
        already terminal, so a failure cannot overwrite a completed run.
        """
        transition = self.advance(RunStage.FAILED, at=at)
        self.failure_reason = reason
        return transition
