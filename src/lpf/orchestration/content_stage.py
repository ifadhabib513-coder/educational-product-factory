"""Content stage — generates lessons, worked examples, and misconceptions.

This is the first stage that calls a model. It is handed a ``ModelProvider`` and
calls it exactly as the hosted path will, so the provider seam is exercised rather
than assumed. In the offline run the injected model is deterministic; swapping it
for a real provider requires no change here.

Worked examples for APPLY objectives are *written by the model* against
``WorkedExampleDraft`` — the Content stage stamps identity onto the draft but does
not invent the arithmetic. That makes a wrong answer the writer's defect: one the
QA ``numerical_consistency`` gate can find and the ``qa  content`` re-run can
repair, because the rebuild carries the failure back to the writer as
``feedback``.
"""

from __future__ import annotations

from dataclasses import dataclass

from lpf.domain.curriculum import CurriculumBlueprint
from lpf.domain.identity import with_content_hash
from lpf.domain.lesson import Lesson
from lpf.domain.misconception import Misconception, MisconceptionSeverity
from lpf.domain.objectives import BloomLevel, LearningObjective
from lpf.domain.worked_example import WorkedExample, WorkedExampleDraft
from lpf.errors import ProviderError
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


def _worked_example_prompt(*, title: str, level: str, feedback: str | None) -> str:
    """Prompt the writer for a worked example, carrying QA feedback on a re-run.

    The feedback is the only way a stateless writer can know this is a repair
    pass rather than a first draft: when ``feedback`` is ``None`` the prompt is a
    first draft, and when it names a failed gate the writer is told what to fix.
    """
    prompt = f'Write a worked example for "{title}" for a {level} learner.'
    if feedback:
        prompt += f" The previous draft failed QA: {feedback}. Fix the arithmetic."
    return prompt


async def _write_worked_example(
    *,
    model: ModelProvider,
    title: str,
    level: str,
    feedback: str | None,
) -> WorkedExampleDraft:
    """Ask the model for a structured worked-example draft."""
    reply = await model.generate(
        messages=[
            {
                "role": "system",
                "content": "You write exact, checkable worked examples step by step.",
            },
            {
                "role": "user",
                "content": _worked_example_prompt(title=title, level=level, feedback=feedback),
            },
        ],
        temperature=0.0,
        schema=WorkedExampleDraft,
    )
    if isinstance(reply, str):
        raise ProviderError(
            code="STRUCTURED_REPLY_REQUIRED",
            message=(
                "WorkedExampleDraft requested but the model returned text; "
                "a structured reply is required for worked examples."
            ),
        )
    return reply


async def build_content(
    ctx: RunContext,
    *,
    blueprint: CurriculumBlueprint,
    objectives_by_id: dict[str, LearningObjective],
    level: str,
    model: ModelProvider,
    feedback: str | None = None,
) -> ContentBundle:
    """Build one lesson per unit, plus examples and misconceptions where apt.

    ``feedback`` is the QA failure message from the previous pass, threaded into
    the worked-example prompt so a re-run is a *repair* rather than a repeat.
    """
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
            draft = await _write_worked_example(
                model=model, title=unit.title, level=level, feedback=feedback
            )
            worked_examples.append(
                with_content_hash(
                    WorkedExample(
                        id=ctx.id("worked_example"),
                        created_at=ctx.now(),
                        parent_id=lesson.id,
                        title=f"Worked example: {unit.title}",
                        lesson_id=lesson.id,
                        problem_statement=draft.problem_statement,
                        solution_steps=list(draft.solution_steps),
                        final_answer=draft.final_answer,
                        common_errors=list(draft.common_errors),
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
