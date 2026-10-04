"""Syllabus stage — turns objectives into an ordered curriculum blueprint.

The blueprint is the contract between planning and content: content may only
reference objectives that exist, and every objective must appear in a unit.
``check_objective_references`` enforces the first half; the QA stage enforces the
second by asserting full objective coverage.
"""

from __future__ import annotations

from dataclasses import dataclass

from lpf.domain.curriculum import CurriculumBlueprint, CurriculumUnit
from lpf.domain.identity import with_content_hash
from lpf.domain.objectives import LearningObjective
from lpf.orchestration.context import RunContext


@dataclass(frozen=True)
class SyllabusBundle:
    """The ordered blueprint plus the objectives it indexes."""

    blueprint: CurriculumBlueprint
    objectives: tuple[LearningObjective, ...]


def build_syllabus(
    ctx: RunContext,
    *,
    title: str,
    objectives: list[LearningObjective],
) -> SyllabusBundle:
    """Create one ordered unit per objective.

    One-unit-per-objective is the simplest structure that keeps every objective
    independently addressable by content, practice, and assessment. Grouping
    several objectives into a unit is a later curriculum-engine concern (Phase 6).
    """
    units = [
        CurriculumUnit(
            unit_id=ctx.id("unit"),
            title=objective.statement.rstrip("."),
            objective_ids=[objective.id],
            order=index + 1,
        )
        for index, objective in enumerate(objectives)
    ]

    blueprint = with_content_hash(
        CurriculumBlueprint(
            id=ctx.id("blueprint"),
            created_at=ctx.now(),
            title=title,
            units=units,
        )
    )
    return SyllabusBundle(blueprint=blueprint, objectives=tuple(objectives))
