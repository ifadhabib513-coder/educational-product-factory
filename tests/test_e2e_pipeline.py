"""End-to-end tests for the deterministic offline pipeline.

The determinism test is the important one. It is the regression guard for the
two real reproducibility defects this stage surfaced in the research pipeline:
``claim_id=new_id()`` and ``QualityGate.checked_at`` defaulting to ``now()``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lpf.orchestration.pipeline import FactoryPipeline, FactoryRunResult
from lpf.orchestration.state import PIPELINE_STAGES
from lpf.schemas.discovery import DiscoveryInputs


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="I am a year 10 student and I keep failing at linear algebra.",
        subject="linear algebra",
        level="year 10",
    )


async def _run(output_dir: Path, *, run_id: str = "run", seed: str = "default") -> FactoryRunResult:
    pipeline = FactoryPipeline(output_dir=str(output_dir))
    return await pipeline.run(_inputs(), run_id=run_id, seed=seed)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for name, data in _tree_bytes(root).items():
        digest.update(name.encode())
        digest.update(data)
    return digest.hexdigest()


class TestPipelineCompletes:
    async def test_run_reaches_complete_and_writes_output(self, tmp_path: Path) -> None:
        result = await _run(tmp_path)
        assert result.succeeded
        assert result.verification is not None
        assert result.package is not None
        root = result.package.root
        assert (root / "manifest.json").is_file()
        assert (root / "run_log.json").is_file()
        assert (root / "product.md").is_file()

    async def test_every_artifact_has_a_content_hash(self, tmp_path: Path) -> None:
        result = await _run(tmp_path)
        assert result.artifacts
        assert all(artifact.content_hash for artifact in result.artifacts)

    async def test_artifact_files_match_artifact_count(self, tmp_path: Path) -> None:
        result = await _run(tmp_path)
        written = list((result.package.root / "artifacts").glob("*.json"))
        assert len(written) == len(result.artifacts)

    async def test_product_document_is_readable(self, tmp_path: Path) -> None:
        result = await _run(tmp_path)
        text = result.package.product_path.read_text(encoding="utf-8")
        assert text.startswith("# ")
        assert "## Lessons" in text
        assert "## Quality" in text


class TestManifestAndLog:
    async def test_manifest_agrees_with_the_run(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, run_id="manifest-check")
        manifest = json.loads((result.package.root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["run_id"] == "manifest-check"
        assert manifest["stage"] == "complete"
        assert manifest["artifact_count"] == len(result.artifacts)
        # Nine hops: created -> discovery, then one per pipeline stage, then
        # packaging -> complete.
        assert len(manifest["stage_history"]) == len(PIPELINE_STAGES) + 1
        assert {entry["id"] for entry in manifest["artifacts"]} == {
            artifact.id for artifact in result.artifacts
        }

    async def test_run_log_records_start_and_finish_for_every_stage(self, tmp_path: Path) -> None:
        result = await _run(tmp_path)
        events = json.loads((result.package.root / "run_log.json").read_text(encoding="utf-8"))[
            "events"
        ]
        assert events[0]["event_type"] == "run_started"
        assert events[-1]["event_type"] == "run_completed"
        for stage in PIPELINE_STAGES:
            started = [
                e
                for e in events
                if e["stage"] == stage.value and e["event_type"] == "stage_started"
            ]
            completed = [
                e
                for e in events
                if e["stage"] == stage.value and e["event_type"] == "stage_completed"
            ]
            assert len(started) == 1, stage
            assert len(completed) == 1, stage


class TestDeterminism:
    async def test_two_runs_produce_byte_identical_output(self, tmp_path: Path) -> None:
        first = await _run(tmp_path / "a")
        second = await _run(tmp_path / "b")
        assert _tree_hash(first.package.root) == _tree_hash(second.package.root)

    async def test_artifact_content_hashes_are_stable(self, tmp_path: Path) -> None:
        first = await _run(tmp_path / "a")
        second = await _run(tmp_path / "b")
        left = {artifact.id: artifact.content_hash for artifact in first.artifacts}
        right = {artifact.id: artifact.content_hash for artifact in second.artifacts}
        assert left == right

    async def test_research_claim_ids_are_scoped_to_the_run(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, run_id="scoped")
        report = next(
            artifact for artifact in result.artifacts if artifact.artifact_type == "research_report"
        )
        claim_ids = [claim.claim_id for claim in report.claims]
        assert claim_ids
        assert all(claim_id.startswith("scoped-claim-") for claim_id in claim_ids)
        assert len(claim_ids) == len(set(claim_ids))


class TestMockResearchNoise:
    """Canned mock snippets must not manufacture conflicts (TASK-002)."""

    async def test_offline_run_reports_no_spurious_conflicts(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, run_id="noise")
        assert result.succeeded
        report = next(
            artifact for artifact in result.artifacts if artifact.artifact_type == "research_report"
        )
        assert report.conflicts == []

    async def test_mock_claims_record_no_contradictions(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, run_id="neutral")
        evidence = next(
            artifact for artifact in result.artifacts if artifact.artifact_type == "evidence_map"
        )
        assert evidence.conflicting_claims == 0
