"""Packaging stage — writes a completed run to disk.

Output layout under ``<output_dir>/<run_id>/``::

    manifest.json        run metadata: stages, counts, artifact ids and hashes
    run_log.json         the ordered event log
    product.md           human-readable product document
    product.html         the same document as standalone HTML
    <run_id>.zip         archival bundle: manifest, markdown, html, artifacts
    artifacts/           one JSON file per root artifact

JSON is written with sorted keys and a fixed indent so two runs with the same
inputs produce identical bytes. The HTML document and the ZIP bundle follow
the same rule: no wall clock, no host-specific metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from lpf.domain.quality import GateStatus, VerificationResult
from lpf.orchestration.context import RunContext
from lpf.orchestration.events import EventLog
from lpf.orchestration.state import RunState
from lpf.packaging import build_run_bundle, render_html_document


@dataclass(frozen=True)
class PackageResult:
    """Where the run was written, and how much was written."""

    root: Path
    manifest_path: Path
    product_path: Path
    product_html_path: Path
    run_log_path: Path
    bundle_path: Path
    artifact_paths: tuple[Path, ...]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _artifact_filename(artifact: BaseModel) -> str:
    artifact_type = getattr(artifact, "artifact_type", "artifact")
    artifact_id = getattr(artifact, "id", "unknown")
    return f"{artifact_type}__{artifact_id}.json"


def render_product_markdown(
    *,
    title: str,
    level: str,
    problem_statement: str,
    objectives: list,
    lessons: list,
    questions: list,
    verification: VerificationResult,
) -> str:
    """Render a plain, readable product document from the run's artifacts."""
    lines: list[str] = [
        f"# {title}",
        "",
        f"**Level:** {level}",
        "",
        "## The problem this solves",
        "",
        problem_statement,
        "",
        "## What you will be able to do",
        "",
    ]
    lines += [f"- {objective.statement}" for objective in objectives]
    lines += ["", "## Lessons", ""]
    for lesson in lessons:
        lines += [f"### {lesson.title}", "", lesson.body_markdown, ""]
    lines += ["## Practice", ""]
    for index, question in enumerate(questions, start=1):
        lines.append(f"{index}. {question.stem}")
    lines += [
        "",
        "## Quality",
        "",
        f"- Overall: `{verification.overall_status.value}`",
        f"- Score: {verification.overall_score:.2f}",
        "",
        "| Gate | Status |",
        "| --- | --- |",
    ]
    lines += [f"| {gate.gate_name} | {gate.status.value} |" for gate in verification.gates]
    lines.append("")
    return "\n".join(lines)


def package_run(
    ctx: RunContext,
    *,
    state: RunState,
    events: EventLog,
    artifacts: list[BaseModel],
    verification: VerificationResult,
) -> PackageResult:
    """Write the manifest, run log, product document, and every artifact."""
    root = Path(ctx.output_dir) / ctx.run_id
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths: list[Path] = []
    manifest_entries: list[dict[str, object]] = []
    for artifact in artifacts:
        path = artifacts_dir / _artifact_filename(artifact)
        _write_json(path, artifact.model_dump(mode="json"))
        artifact_paths.append(path)
        manifest_entries.append(
            {
                "id": getattr(artifact, "id", None),
                "artifact_type": getattr(artifact, "artifact_type", None),
                "content_hash": getattr(artifact, "content_hash", ""),
            }
        )

    manifest = {
        "run_id": ctx.run_id,
        "seed": ctx.seed,
        "stage": state.stage.value,
        "failure_reason": state.failure_reason,
        "timestamps_issued": ctx.tick,
        "stage_history": [
            {
                "from": transition.from_stage.value,
                "to": transition.to_stage.value,
                "at": transition.at.isoformat(),
            }
            for transition in state.history
        ],
        "artifact_count": len(artifacts),
        "artifacts": manifest_entries,
        "verification": {
            "overall_status": verification.overall_status.value,
            "overall_score": verification.overall_score,
            "gates_passed": sum(
                1 for gate in verification.gates if gate.status is GateStatus.PASSED
            ),
            "gates_total": len(verification.gates),
        },
    }

    manifest_path = root / "manifest.json"
    run_log_path = root / "run_log.json"
    product_path = root / "product.md"
    product_html_path = root / "product.html"

    _write_json(manifest_path, manifest)
    _write_json(run_log_path, {"run_id": ctx.run_id, "events": events.to_dicts()})

    title = _product_title(artifacts)
    product_markdown = render_product_markdown(
        title=title,
        level=_learner_level(artifacts),
        problem_statement=_problem_statement(artifacts),
        objectives=_objectives(artifacts),
        lessons=[a for a in artifacts if getattr(a, "artifact_type", "") == "lesson"],
        questions=[a for a in artifacts if getattr(a, "artifact_type", "") == "practice_question"],
        verification=verification,
    )
    product_path.write_text(product_markdown, encoding="utf-8")
    product_html_path.write_text(
        render_html_document(product_markdown, title=title),
        encoding="utf-8",
    )

    bundle_path = build_run_bundle(
        root=root,
        run_id=ctx.run_id,
        members=[
            ("manifest.json", manifest_path),
            ("product.html", product_html_path),
            ("product.md", product_path),
            ("run_log.json", run_log_path),
            *((f"artifacts/{path.name}", path) for path in artifact_paths),
        ],
    )

    return PackageResult(
        root=root,
        manifest_path=manifest_path,
        product_path=product_path,
        product_html_path=product_html_path,
        run_log_path=run_log_path,
        bundle_path=bundle_path,
        artifact_paths=tuple(artifact_paths),
    )


def _first(artifacts: list[BaseModel], artifact_type: str) -> BaseModel | None:
    return next((a for a in artifacts if getattr(a, "artifact_type", "") == artifact_type), None)


def _product_title(artifacts: list[BaseModel]) -> str:
    spec = _first(artifacts, "product_spec")
    return getattr(spec, "title", "Untitled product")


def _learner_level(artifacts: list[BaseModel]) -> str:
    spec = _first(artifacts, "product_spec")
    audience = getattr(spec, "audience", None)
    return getattr(audience, "level", "unspecified")


def _problem_statement(artifacts: list[BaseModel]) -> str:
    spec = _first(artifacts, "product_spec")
    return getattr(spec, "problem_statement", "")


def _objectives(artifacts: list[BaseModel]) -> list:
    outcomes = _first(artifacts, "outcome_definition")
    if outcomes is None:
        return []
    return list(getattr(outcomes, "outcomes", []))
