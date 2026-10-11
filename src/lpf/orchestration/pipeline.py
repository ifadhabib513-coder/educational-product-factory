"""Factory pipeline — composes the stages into one deterministic run.

The pipeline owns the state machine and the event log. Each stage visit advances
the run exactly once and announces itself on the log, so a completed manifest can
be replayed: the stage history and the artifacts always agree.

The only loop is the QA revision cycle. QA may rewind to content or assessment
for a failure it can attribute to those stages, bounded by ``MAX_REVISIONS``; a
failure it cannot attribute, or a budget that has run out, ends the run instead
of repeating work that would fail the same way.

Failure policy: expected domain failures (``LpfError``) mark the run ``FAILED``
and are returned as a value. Unexpected exceptions are programmer errors and
propagate. Neither is swallowed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel

from lpf.domain.quality import GateStatus, VerificationResult
from lpf.errors import LpfError
from lpf.models.provider import ModelProvider
from lpf.orchestration.assessment_stage import AssessmentBundle, build_assessment
from lpf.orchestration.content_stage import ContentBundle, build_content
from lpf.orchestration.context import RunContext
from lpf.orchestration.discovery_stage import (
    DiscoveryBundle,
    SpecificationBundle,
    build_discovery,
    build_specification,
)
from lpf.orchestration.events import EventLog, EventType
from lpf.orchestration.model import DeterministicMockModel
from lpf.orchestration.packaging_stage import PackageResult, package_run
from lpf.orchestration.qa_stage import QaBundle, build_qa
from lpf.orchestration.research_stage import ResearchBundle, build_research
from lpf.orchestration.revision import route_failed_gates
from lpf.orchestration.state import MAX_REVISIONS, RunStage, RunState
from lpf.orchestration.syllabus_stage import SyllabusBundle, build_syllabus
from lpf.research.audience import AudienceLevel, classify_audience
from lpf.research.providers.base import SearchProviderProto
from lpf.schemas.discovery import DiscoveryInputs
from lpf.schemas.research import SearchProvider


@dataclass
class FactoryRunResult:
    """The outcome of one factory run."""

    run_id: str
    state: RunState
    events: EventLog
    artifacts: list[BaseModel] = field(default_factory=list)
    verification: VerificationResult | None = None
    package: PackageResult | None = None

    @property
    def succeeded(self) -> bool:
        """True only when the run reached ``COMPLETE``."""
        return self.state.stage is RunStage.COMPLETE


class FactoryPipeline:
    """Runs the full offline pipeline: problem in, packaged product out."""

    def __init__(
        self,
        *,
        output_dir: str = "projects",
        model: ModelProvider | None = None,
        audience: AudienceLevel | str | None = None,
        research_providers: Mapping[SearchProvider, SearchProviderProto] | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._model: ModelProvider = model or DeterministicMockModel()
        self._audience = classify_audience(audience) if audience is not None else None
        #: None means "use the deterministic offline providers".
        self._research_providers = research_providers

    async def run(
        self,
        inputs: DiscoveryInputs,
        *,
        run_id: str = "run",
        seed: str = "default",
        write: bool = True,
        required_gates: list[str] | None = None,
    ) -> FactoryRunResult:
        """Execute every stage, recording state and events as it goes."""
        ctx = RunContext(run_id=run_id, seed=seed, output_dir=self._output_dir)
        state = RunState(run_id=run_id)
        events = EventLog(run_id=run_id)
        artifacts: list[BaseModel] = []

        events.emit(
            EventType.RUN_STARTED,
            stage=RunStage.CREATED,
            message=f"Run started for subject={inputs.subject!r} level={inputs.level!r}",
            timestamp=ctx.now(),
        )

        package: PackageResult | None = None
        verification: VerificationResult | None = None

        try:
            # --- Discovery -------------------------------------------------
            self._begin(ctx, state, events, RunStage.DISCOVERY)
            discovery: DiscoveryBundle = build_discovery(ctx, inputs)
            artifacts += _bundle_artifacts(discovery)
            self._complete(ctx, state, events, RunStage.DISCOVERY, _bundle_artifacts(discovery))

            # --- Specification ---------------------------------------------
            self._begin(ctx, state, events, RunStage.SPECIFICATION)
            spec: SpecificationBundle = build_specification(ctx, inputs, discovery)
            artifacts.append(spec.spec)
            self._complete(ctx, state, events, RunStage.SPECIFICATION, [spec.spec])

            # --- Research --------------------------------------------------
            self._begin(ctx, state, events, RunStage.RESEARCH)
            level = discovery.learner.level
            audience = self._audience or classify_audience(level)
            research: ResearchBundle = await build_research(
                ctx,
                product_spec_id=spec.spec.id,
                research_questions=discovery.brief.research_questions,
                topic=discovery.problem.subject,
                audience=audience,
                providers=self._research_providers,
            )
            research_artifacts = [research.plan, research.report, research.evidence_map]
            artifacts += research_artifacts
            self._complete(ctx, state, events, RunStage.RESEARCH, research_artifacts)

            # --- Syllabus --------------------------------------------------
            self._begin(ctx, state, events, RunStage.SYLLABUS)
            syllabus: SyllabusBundle = build_syllabus(
                ctx,
                title=discovery.opportunity.title,
                objectives=list(discovery.outcomes.outcomes),
            )
            artifacts.append(syllabus.blueprint)
            self._complete(ctx, state, events, RunStage.SYLLABUS, [syllabus.blueprint])

            # --- Content, Assessment, QA: the one cycle in the machine ----
            # QA does not have to be the end of the line. When a gate fails on
            # an artifact that an earlier stage produced, the run rewinds to
            # that stage and rebuilds forward, at most MAX_REVISIONS times.
            # Superseded artifacts are dropped from the run as the cycle goes
            # around, so the shipped product never contains a lesson that was
            # thrown away on a later pass.
            rebuild_content = True
            feedback: str | None = None
            content: ContentBundle | None = None
            assessment: AssessmentBundle | None = None
            content_artifacts: list[BaseModel] = []
            assessment_artifacts: list[BaseModel] = []
            verification_artifacts: list[BaseModel] = []

            while True:
                if rebuild_content:
                    _discard(artifacts, content_artifacts)
                    self._begin(ctx, state, events, RunStage.CONTENT)
                    content = await build_content(
                        ctx,
                        blueprint=syllabus.blueprint,
                        objectives_by_id={obj.id: obj for obj in discovery.outcomes.outcomes},
                        level=level,
                        model=self._model,
                        feedback=feedback,
                    )
                    content_artifacts = [
                        *content.lessons,
                        *content.worked_examples,
                        *content.misconceptions,
                    ]
                    artifacts += content_artifacts
                    self._complete(ctx, state, events, RunStage.CONTENT, content_artifacts)
                # content is built on the first pass and retained thereafter.
                assert content is not None

                # --- Assessment ----------------------------------------
                _discard(artifacts, assessment_artifacts)
                self._begin(ctx, state, events, RunStage.ASSESSMENT)
                assessment = build_assessment(
                    ctx,
                    lessons=list(content.lessons),
                    title=f"Check your understanding: {discovery.problem.subject}",
                )
                assessment_artifacts = [
                    *assessment.questions,
                    *assessment.answers,
                    assessment.answer_key,
                    assessment.assessment,
                ]
                artifacts += assessment_artifacts
                self._complete(ctx, state, events, RunStage.ASSESSMENT, assessment_artifacts)

                # --- QA ------------------------------------------------
                _discard(artifacts, verification_artifacts)
                self._begin(ctx, state, events, RunStage.QA)
                qa: QaBundle = build_qa(
                    ctx,
                    blueprint=syllabus.blueprint,
                    objectives=list(discovery.outcomes.outcomes),
                    lessons=list(content.lessons),
                    misconceptions=list(content.misconceptions),
                    questions=list(assessment.questions),
                    answers=list(assessment.answers),
                    answer_key=assessment.answer_key,
                    assessment=assessment.assessment,
                    evidence_map=research.evidence_map,
                    worked_examples=list(content.worked_examples),
                    verified_source_ids={
                        source.source_id for source in research.report.verified_sources
                    },
                    required_gates=required_gates,
                    iteration=state.revisions + 1,
                )
                verification = qa.verification
                verification_artifacts = [verification]
                artifacts.append(verification)
                self._complete(ctx, state, events, RunStage.QA, [verification])

                if verification.overall_status is not GateStatus.FAILED:
                    break

                failed_gates = [
                    gate.gate_name
                    for gate in verification.gates
                    if gate.status is GateStatus.FAILED
                ]
                target = route_failed_gates(failed_gates)

                if target is None:
                    reason = f"QA gates failed and are not repairable: {failed_gates}"
                elif state.revisions_exhausted:
                    reason = (
                        f"QA revision budget of {MAX_REVISIONS} exhausted; "
                        f"gates still failing: {failed_gates}"
                    )
                else:
                    state.begin_revision()
                    feedback = _revision_feedback(verification)
                    rebuild_content = target is RunStage.CONTENT
                    events.emit(
                        EventType.REVISION_STARTED,
                        stage=RunStage.QA,
                        message=(
                            f"QA failed on {failed_gates}; "
                            f"revision {state.revisions} rewinds to "
                            f"'{target.value}'."
                        ),
                        timestamp=ctx.now(),
                    )
                    continue

                state.fail(reason, at=ctx.now())
                events.emit(
                    EventType.RUN_FAILED,
                    stage=RunStage.QA,
                    message=reason,
                    timestamp=ctx.now(),
                )
                return FactoryRunResult(
                    run_id=run_id,
                    state=state,
                    events=events,
                    artifacts=artifacts,
                    verification=verification,
                )

            # --- Packaging -------------------------------------------------
            # Packaging persists the run, so it must see the terminal state and
            # the final event. Otherwise the manifest would record the run as
            # still 'packaging' and the run log would omit 'run_completed'.
            self._begin(ctx, state, events, RunStage.PACKAGING)
            self._complete(ctx, state, events, RunStage.PACKAGING, [])

            state.advance(RunStage.COMPLETE, at=ctx.now())
            events.emit(
                EventType.RUN_COMPLETED,
                stage=RunStage.COMPLETE,
                message=f"Run completed with {len(artifacts)} artifacts.",
                timestamp=ctx.now(),
            )

            if write:
                package = package_run(
                    ctx,
                    state=state,
                    events=events,
                    artifacts=artifacts,
                    verification=verification,
                )

            return FactoryRunResult(
                run_id=run_id,
                state=state,
                events=events,
                artifacts=artifacts,
                verification=verification,
                package=package,
            )

        except LpfError as error:
            state.fail(f"{error.code}: {error.message}", at=ctx.now())
            events.emit(
                EventType.RUN_FAILED,
                stage=state.stage,
                message=f"{error.code}: {error.message}",
                timestamp=ctx.now(),
            )
            return FactoryRunResult(
                run_id=run_id,
                state=state,
                events=events,
                artifacts=artifacts,
                verification=verification,
            )

    @staticmethod
    def _begin(ctx: RunContext, state: RunState, events: EventLog, stage: RunStage) -> None:
        state.advance(stage, at=ctx.now())
        events.emit(
            EventType.STAGE_STARTED,
            stage=stage,
            message=f"Stage '{stage.value}' started.",
            timestamp=ctx.now(),
        )

    @staticmethod
    def _complete(
        ctx: RunContext,
        state: RunState,
        events: EventLog,
        stage: RunStage,
        artifacts: list[BaseModel],
    ) -> None:
        events.emit(
            EventType.STAGE_COMPLETED,
            stage=stage,
            message=f"Stage '{stage.value}' produced {len(artifacts)} artifact(s).",
            timestamp=ctx.now(),
            artifact_ids=tuple(getattr(a, "id", "") for a in artifacts),
        )


def _bundle_artifacts(bundle: DiscoveryBundle) -> list[BaseModel]:
    """Every root artifact in a Discovery bundle, in a stable order."""
    return [
        bundle.learner,
        bundle.problem,
        bundle.outcomes,
        bundle.opportunity,
        bundle.market,
        bundle.brief,
    ]


def _discard(artifacts: list[BaseModel], superseded: list[BaseModel]) -> None:
    """Drop ``superseded`` from the run's live artifact list, in place.

    Called before a stage re-runs. Objects are matched by identity, not by
    value, because the point is "the objects from the pass we just threw
    away", and because content hashes make two distinct passes look similar
    enough that value equality would be a trap.
    """
    if not superseded:
        return
    stale = {id(artifact) for artifact in superseded}
    artifacts[:] = [artifact for artifact in artifacts if id(artifact) not in stale]


def _revision_feedback(verification: VerificationResult) -> str:
    """Collapse a failed verification into the message the writer must repair.

    Deterministic, because it is derived from the verification's own gate output
    and is embedded in the rebuild prompt: the same failure always yields the
    same repair instruction.
    """
    parts: list[str] = []
    for gate in verification.gates:
        if gate.status is not GateStatus.FAILED:
            continue
        problem = gate.findings[0].problem if gate.findings else "gate failed"
        parts.append(f"{gate.gate_name}: {problem}")
    return "; ".join(parts)
