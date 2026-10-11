"""Routing of failed QA gates back into the stage machine.

QA is not a dead end: when a gate fails, the useful question is *which stage
produced the artifact the gate is complaining about*, because that is the stage
that has to be re-run. This module answers that question with an explicit
ownership table rather than a guess.

Gate ownership is a partial function. A gate is owned by exactly one revisitable
stage; a gate with no owner - an unknown gate, or one of the
:data:`NON_REPAIRABLE_GATES` whose inputs come from stages the revision cycle
does not revisit - cannot be cleared by re-running anything, so its failure ends
the run. Among the gates that *are* owned, a content failure wins, because
content rebuilds forward into assessment anyway.

Conservative by construction: an abort costs a clear failure, while a wrong
re-run costs a plausible-looking product built from stale inputs.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from lpf.orchestration.state import RunStage

__all__ = [
    "ASSESSMENT_GATES",
    "CONTENT_GATES",
    "NON_REPAIRABLE_GATES",
    "OWNED_GATES",
    "route_failed_gates",
]

#: Gates whose evidence lives in the content stage (``lessons``,
#: ``worked_examples``, ``misconceptions``). ``factual_consistency`` is *not*
#: owned here: its inputs are research artifacts (``evidence_map.claims``,
#: ``verified_source_ids``) that the content rebuild does not touch, so a content
#: re-run can never clear it — it belongs in :data:`NON_REPAIRABLE_GATES`.
CONTENT_GATES: Final[frozenset[str]] = frozenset(
    {
        "misconception_references",
        "numerical_consistency",
    }
)

#: Gates whose evidence lives in the assessment stage (``questions``,
#: ``answers``, ``answer_key``, ``assessment``).
ASSESSMENT_GATES: Final[frozenset[str]] = frozenset(
    {
        "question_references",
        "assessment_references",
        "answer_references",
        "answer_key_references",
    }
)

#: The named gates a content or assessment re-run cannot clear: their inputs
#: come from stages the revision cycle does not revisit (discovery, research,
#: syllabus) or from run configuration itself. ``factual_consistency`` sits here
#: because its evidence lives in research, which the revision cycle never
#: revisits; ``schema_validity`` is absent because schema conformance is enforced
#: by pydantic at construction and no gate exists to route. Every one of these is
#: unowned, and any gate outside the two owned sets is unowned too.
NON_REPAIRABLE_GATES: Final[frozenset[str]] = frozenset(
    {
        "curriculum_coverage",
        "objective_references",
        "research_evidence",
        "factual_consistency",
        "required_gates_present",
    }
)

#: The ownership table: every gate a revisitable stage can actually fix.
OWNED_GATES: Final[dict[str, RunStage]] = {
    **{name: RunStage.CONTENT for name in CONTENT_GATES},
    **{name: RunStage.ASSESSMENT for name in ASSESSMENT_GATES},
}


def route_failed_gates(gate_names: Iterable[str]) -> RunStage | None:
    """Return the stage to re-run, or ``None`` if the run must abort.

    ``gate_names`` is the list of gates that reported ``FAILED``. An empty set
    is a caller error and returns ``None`` rather than inventing a revision.
    """
    targets = {OWNED_GATES.get(name) for name in set(gate_names)}
    if not targets or None in targets:
        return None
    if RunStage.CONTENT in targets:
        return RunStage.CONTENT
    return RunStage.ASSESSMENT
