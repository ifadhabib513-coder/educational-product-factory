"""Content stage — generates lessons, worked examples, and misconceptions.

This is the first stage that calls a model. It is handed a ``ModelProvider`` and
calls it exactly as the hosted path will, so the provider seam is exercised rather
than assumed. In the offline run the injected model is deterministic; swapping it
for a real provider requires no change here.
"""

from __future__ import annotations

from dataclasses import dataclass

from lpf.domain.content import SolutionStep
from lpf.domain.curriculum import CurriculumBlueprint
from lpf.domain.identity import with_content_hash
from lpf.domain.lesson import Lesson
from lpf.domain.misconception import Misconception, MisconceptionSeverity
from lpf.domain.objectives import BloomLevel, LearningObjective
from lpf.domain.worked_example import WorkedExample
from lpf.models.provider import ModelProvider
from lpf.orchestration.context import RunContext


@dataclass(frozen=True)
class ContentBundle:
    """Everything the Content stage produces."""

    lessons: tuple[Lesson, ...]
    worked_examples: tuple[WorkedExample, ...]
    misconceptions: tuple[Misconception, ...]


async def _explain(*, model: ModelProvider, title: str, level: str) -> str:
    """Ask the model for an explanation body, routed through the real interface."""
    response = await model.generate(
        messages=[
            {"role": "system", "content": "You explain concepts precisely and briefly."},
            {"role": "user", "content": f"Explain {title} for a {level} learner."},
        ],
        temperature=0.0,
    )
    return response if isinstance(response, str) else str(response)


async def build_content(
    ctx: RunContext,
    *,
    blueprint: CurriculumBlueprint,
    objectives_by_id: dict[str, LearningObjective],
    level: str,
    model: ModelProvider,
) -> ContentBundle:
    """Build one lesson per unit, plus examples and misconceptions where apt."""
    lessons: list[Lesson] = []
    worked_examples: list[WorkedExample] = []
    misconceptions: list[Misconception] = []

    for unit in blueprint.units:
        objective = objectives_by_id.get(unit.objective_ids[0])
        body = await _explain(model=model, title=unit.title, level=level)
        lesson = with_content_hash(
            Lesson(
                id=ctx.id("lesson"),
                created_at=ctx.now(),
                parent_id=blueprint.id,
                title=unit.title,
                unit_id=unit.unit_id,
                objective_ids=list(unit.objective_ids),
                body_markdown=f"## {unit.title}\n\n{body}",
                summary=f"A short introduction to {unit.title}.",
                source_refs=[blueprint.id],
            )
        )
        lessons.append(lesson)

        if objective is not None and objective.bloom_level is BloomLevel.APPLY:
            worked_examples.append(
                with_content_hash(
                    WorkedExample(
                        id=ctx.id("worked_example"),
                        created_at=ctx.now(),
                        parent_id=lesson.id,
                        title=f"Worked example: {unit.title}",
                        lesson_id=lesson.id,
                        problem_statement=f"Apply what you just learned: {unit.title}.",
                        solution_steps=[
                            SolutionStep(order=1, statement="Identify what is being asked."),
                            SolutionStep(order=2, statement="Choose the method that fits."),
                            SolutionStep(
                                order=3,
                                statement="Carry it out and check the result.",
                                expression="result = apply(method, problem)",
                            ),
                        ],
                        final_answer="The problem is solved and the result checked.",
                        common_errors=["Skips the check step."],
                        source_refs=[lesson.id],
                    )
                )
            )

        misconceptions.append(
            with_content_hash(
                Misconception(
                    id=ctx.id("misconception"),
                    created_at=ctx.now(),
                    parent_id=lesson.id,
                    statement=f"{unit.title} is only a formula to memorise.",
                    correction=(
                        f"{unit.title} is a way of reasoning; the formula is a "
                        "consequence of the idea, not the idea itself."
                    ),
                    objective_ids=list(unit.objective_ids),
                    severity=MisconceptionSeverity.COMMON,
                    source_refs=[lesson.id],
                )
            )
        )

    return ContentBundle(
        lessons=tuple(lessons),
        worked_examples=tuple(worked_examples),
        misconceptions=tuple(misconceptions),
    )
