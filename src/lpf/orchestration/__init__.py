"""Deterministic offline pipeline: discovery through packaging.

Everything here is reproducible: given the same inputs and the same provider
responses, two runs produce byte-identical output. The model is used only where a
model is unavoidable (lesson prose); every decision — ids, timing, ranking, gate
verdicts — is deterministic.
"""

from lpf.orchestration.assessment_stage import AssessmentBundle, build_assessment
from lpf.orchestration.content_stage import ContentBundle, build_content
from lpf.orchestration.context import RunContext
from lpf.orchestration.discovery_stage import (
    DiscoveryBundle,
    SpecificationBundle,
    build_discovery,
    build_specification,
)
from lpf.orchestration.events import EventLog, EventType, RunEvent
from lpf.orchestration.model import DeterministicMockModel, protocol_satisfied
from lpf.orchestration.packaging_stage import PackageResult, package_run
from lpf.orchestration.pipeline import FactoryPipeline, FactoryRunResult
from lpf.orchestration.qa_stage import QaBundle, build_qa
from lpf.orchestration.research_stage import ResearchBundle, build_research
from lpf.orchestration.state import (
    LEGAL_TRANSITIONS,
    PIPELINE_STAGES,
    RunStage,
    RunState,
    StageTransition,
)
from lpf.orchestration.syllabus_stage import SyllabusBundle, build_syllabus

__all__ = [
    "AssessmentBundle",
    "ContentBundle",
    "DeterministicMockModel",
    "DiscoveryBundle",
    "EventLog",
    "EventType",
    "FactoryPipeline",
    "FactoryRunResult",
    "LEGAL_TRANSITIONS",
    "PIPELINE_STAGES",
    "PackageResult",
    "QaBundle",
    "ResearchBundle",
    "RunContext",
    "RunEvent",
    "RunStage",
    "RunState",
    "SpecificationBundle",
    "StageTransition",
    "SyllabusBundle",
    "build_assessment",
    "build_content",
    "build_discovery",
    "build_qa",
    "build_research",
    "build_specification",
    "build_syllabus",
    "package_run",
    "protocol_satisfied",
]
