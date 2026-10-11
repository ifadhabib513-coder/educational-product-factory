"""End-to-end proof that the revision loop repairs a *model-written* defect.

TASK-006 proved the ``qa  content`` re-run with an injected defect. TASK-009
proves the same cycle with a real writer seam: a fake live model (over
``httpx.MockTransport``) writes a worked example whose arithmetic is wrong on
its first draft. QA's ``numerical_consistency`` gate fails it, the pipeline
rewinds to content, and the rebuild carries the failure back to the writer as
``feedback`` in the prompt — so the second draft is actually a repair, not a
monkeypatched repeat. The budget-exhausted variant still fails cleanly and both
outcomes are byte-identical across identical runs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

from lpf.models import OpenAICompatibleModel
from lpf.orchestration.pipeline import FactoryPipeline, FactoryRunResult
from lpf.orchestration.state import MAX_REVISIONS, RunStage
from lpf.research.transport import RetryPolicy
from lpf.schemas.discovery import DiscoveryInputs


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="I am a year 10 student and I keep failing at linear algebra.",
        subject="linear algebra",
        level="year 10",
    )


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _openai_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _hops(result: FactoryRunResult) -> list[tuple[RunStage, RunStage]]:
    return [(t.from_stage, t.to_stage) for t in result.state.history]


def _worked_examples(result: FactoryRunResult) -> list:
    return [a for a in result.artifacts if a.artifact_type == "worked_example"]


def _writer_handler(*, repair_on_feedback: bool):
    """Fake live model whose worked-example drafts describe the repair story.

    * Text (lesson-body) calls return deterministic prose.
    * Structured (worked-example) calls return ``3 + 4 = 8`` on a plain first
      draft and ``3 + 4 = 7`` when the prompt carries QA feedback, as long as
      ``repair_on_feedback`` is set. When it is not, every draft is wrong, so
      the run can only end by exhausting the revision budget.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        structured = bool(body.get("response_format") or body.get("format"))
        user = next(
            message["content"]
            for message in reversed(body["messages"])
            if message.get("role") == "user"
        )

        if not structured:
            title = user.replace("Explain ", "").split(" for a")[0]
            content = (
                f"{title} is defined by a clear rule that links the idea to its use. "
                "The key idea is introduced in plain language and applied in one example. "
                "The common mistake is treating the rule as a formula to memorise."
            )
            return httpx.Response(200, json=_openai_payload(content))

        wrong = not repair_on_feedback or "failed QA" not in user
        expression = "3 + 4 = 8" if wrong else "3 + 4 = 7"
        final_answer = "3 + 4 = 8" if wrong else "7"
        draft = {
            "problem_statement": "Apply what you just learned to the sum 3 + 4.",
            "solution_steps": [
                {"order": 1, "statement": "Identify what is being asked."},
                {"order": 2, "statement": f"Carry out the sum: {expression}."},
            ],
            "final_answer": final_answer,
            "common_errors": ["Forgetting to re-check the arithmetic."],
        }
        return httpx.Response(200, json=_openai_payload(json.dumps(draft)))

    return handler


def _model(handler) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        client=_client(handler),
        retry=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )


class TestModelWrittenDefectRepair:
    async def test_first_draft_fails_numbers_and_rebuild_repairs_it(self, tmp_path: Path) -> None:
        result = await FactoryPipeline(
            output_dir=str(tmp_path), model=_model(_writer_handler(repair_on_feedback=True))
        ).run(_inputs(), run_id="writer")

        assert result.succeeded
        assert result.state.revisions == 1
        assert result.verification is not None
        assert result.verification.iteration == 2
        assert (RunStage.QA, RunStage.CONTENT) in _hops(result)
        assert (RunStage.QA, RunStage.ASSESSMENT) not in _hops(result)

        examples = _worked_examples(result)
        assert examples
        assert all(example.final_answer == "7" for example in examples)
        assert all(
            "3 + 4 = 8" not in step.statement
            for example in examples
            for step in example.solution_steps
        )

    async def test_only_the_repaired_verification_is_shipped(self, tmp_path: Path) -> None:
        result = await FactoryPipeline(
            output_dir=str(tmp_path), model=_model(_writer_handler(repair_on_feedback=True))
        ).run(_inputs(), run_id="writer-verification")

        assert result.succeeded
        verifications = [a for a in result.artifacts if a.artifact_type == "verification_result"]
        assert len(verifications) == 1
        numeric = [
            gate
            for gate in verifications[0].gates  # type: ignore[attr-defined]
            if gate.gate_name == "numerical_consistency"
        ]
        assert numeric and numeric[0].status.value == "passed"

    async def test_a_repaired_run_is_byte_identical(self, tmp_path: Path) -> None:
        model = _model(_writer_handler(repair_on_feedback=True))
        first = await FactoryPipeline(output_dir=str(tmp_path / "a"), model=model).run(
            _inputs(), run_id="det"
        )
        second = await FactoryPipeline(output_dir=str(tmp_path / "b"), model=model).run(
            _inputs(), run_id="det"
        )

        assert first.succeeded and second.succeeded
        assert first.state.revisions == second.state.revisions == 1
        assert first.package is not None and second.package is not None
        assert _tree_hash(first.package.root) == _tree_hash(second.package.root)


class TestModelWrittenDefectBudgetExhaustion:
    async def test_a_constant_defect_fails_cleanly_once_the_budget_is_spent(
        self, tmp_path: Path
    ) -> None:
        result = await FactoryPipeline(
            output_dir=str(tmp_path), model=_model(_writer_handler(repair_on_feedback=False))
        ).run(_inputs(), run_id="doomed")

        assert not result.succeeded
        assert result.state.stage is RunStage.FAILED
        assert result.state.revisions == MAX_REVISIONS
        assert result.state.revisions_exhausted
        assert result.state.failure_reason is not None
        assert "revision budget" in result.state.failure_reason
        assert result.package is None
        assert not (tmp_path / "doomed").exists()

    async def test_an_exhausted_run_is_byte_identical(self, tmp_path: Path) -> None:
        model = _model(_writer_handler(repair_on_feedback=False))
        first = await FactoryPipeline(output_dir=str(tmp_path / "a"), model=model).run(
            _inputs(), run_id="doomed"
        )
        second = await FactoryPipeline(output_dir=str(tmp_path / "b"), model=model).run(
            _inputs(), run_id="doomed"
        )

        assert not first.succeeded and not second.succeeded
        assert first.state.revisions == second.state.revisions
        assert first.state.failure_reason == second.state.failure_reason
