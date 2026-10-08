"""Run state machine — the legal order of pipeline stages.

The machine is linear from ``created`` to ``packaging``, which makes two bugs
impossible by construction: running a stage before its inputs exist, and
silently skipping a stage. The single departure from linearity is a *bounded*
revision loop owned by QA: a failure whose fix lives in an earlier content or
assessment stage may step back exactly that far, once per revision, until the
budget in :data:`MAX_REVISIONS` runs out. See ADR-008 (linearity) and ADR-010
(the revision loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final

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

#: How many times a run may step back from QA to an earlier stage. Bounded so a
#: deterministic failure can never spin: a run either converges within this many
#: cycles or is reported as FAILED with the gates that never cleared.
MAX_REVISIONS: Final = 3

#: The only backward edges in the machine, keyed by the stage that opens them.
#: QA is the sole revision source, and it may only rewind to the two stages that
#: produce the artifacts its gates check. Anything further back (syllabus,
#: research, specification) is out of scope for this version.
REVISION_TARGETS: Final[dict[RunStage, frozenset[RunStage]]] = {
    RunStage.QA: frozenset({RunStage.CONTENT, RunStage.ASSESSMENT})
}


def _build_transitions() -> dict[RunStage, frozenset[RunStage]]:
    """Forward edge to the successor, plus ``failed`` from every non-terminal stage.

    Revision edges from :data:`REVISION_TARGETS` are added last so a reader can
    see the whole backward surface of the machine in one place.
    """
    transitions: dict[RunStage, set[RunStage]] = {stage: set() for stage in RunStage}
    for current, nxt in zip(_STAGE_ORDER, _STAGE_ORDER[1:], strict=False):
        transitions[current].add(nxt)
    for stage in _STAGE_ORDER:
        if stage not in _TERMINAL:
            transitions[stage].add(RunStage.FAILED)
    for source, targets in REVISION_TARGETS.items():
        transitions[source] |= set(targets)
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
    #: Number of QA-initiated step-backs this run has taken so far.
    revisions: int = 0

    @property
    def is_terminal(self) -> bool:
        """True once the run has completed or failed."""
        return self.stage in _TERMINAL

    @property
    def revisions_exhausted(self) -> bool:
        """True once no further revision cycle may be started."""
        return self.revisions >= MAX_REVISIONS

    def begin_revision(self) -> int:
        """Claim one revision from the budget, returning the new revision number.

        The stage transition itself is left to the caller's normal ``advance``,
        so an illegal target is still reported as ``ILLEGAL_TRANSITION``. What
        this method guards is the budget: it raises ``WorkflowError`` rather
        than let a run revise forever.
        """
        if self.revisions_exhausted:
            raise WorkflowError(
                code="REVISION_BUDGET_EXHAUSTED",
                message=(
                    f"Run {self.run_id!r} already used all {MAX_REVISIONS} "
                    f"revision(s) and may not revise again."
                ),
                details={
                    "run_id": self.run_id,
                    "revisions": self.revisions,
                    "max_revisions": MAX_REVISIONS,
                    "stage": self.stage.value,
                },
            )
        self.revisions += 1
        return self.revisions

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
