"""Tests for the deterministic run context and the stage machine.

These are the two foundations that make a run reproducible. If either breaks,
the end-to-end determinism test is the backstop, but the failure here is far
easier to read.
"""

from __future__ import annotations

import pytest

from lpf.errors import WorkflowError
from lpf.orchestration.context import RunContext
from lpf.orchestration.state import (
    LEGAL_TRANSITIONS,
    MAX_REVISIONS,
    PIPELINE_STAGES,
    REVISION_TARGETS,
    RunStage,
    RunState,
)

_AT = RunContext(run_id="clock").now()


class TestRunContext:
    def test_ids_are_sequential_per_kind(self) -> None:
        ctx = RunContext(run_id="r")
        assert ctx.id("lesson") == "r-lesson-0001"
        assert ctx.id("lesson") == "r-lesson-0002"
        assert ctx.id("unit") == "r-unit-0001"

    def test_id_kinds_do_not_interfere(self) -> None:
        ctx = RunContext(run_id="r")
        ctx.id("a")
        ctx.id("a")
        assert ctx.id("b") == "r-b-0001"

    def test_clock_is_monotonic_from_a_fixed_epoch(self) -> None:
        ctx = RunContext(run_id="r")
        first = ctx.now()
        second = ctx.now()
        assert first < second
        assert first.year == 2026
        assert ctx.tick == 2

    def test_two_fresh_contexts_are_identical(self) -> None:
        left = RunContext(run_id="same")
        right = RunContext(run_id="same")
        assert left.id("x") == right.id("x")
        assert left.now() == right.now()


class TestRunState:
    def test_forward_successor_is_legal(self) -> None:
        state = RunState(run_id="r")
        state.advance(RunStage.DISCOVERY, at=_AT)
        assert state.stage is RunStage.DISCOVERY
        assert state.history[-1].from_stage is RunStage.CREATED
        assert state.history[-1].to_stage is RunStage.DISCOVERY

    def test_skipping_a_stage_is_illegal(self) -> None:
        state = RunState(run_id="r")
        state.advance(RunStage.DISCOVERY, at=_AT)
        with pytest.raises(WorkflowError) as raised:
            state.advance(RunStage.QA, at=_AT)
        assert raised.value.code == "ILLEGAL_TRANSITION"
        assert state.stage is RunStage.DISCOVERY

    def test_failure_is_reachable_from_every_non_terminal_stage(self) -> None:
        for stage in PIPELINE_STAGES:
            assert RunStage.FAILED in LEGAL_TRANSITIONS[stage], stage

    def test_terminal_stages_have_no_outgoing_transitions(self) -> None:
        assert LEGAL_TRANSITIONS[RunStage.COMPLETE] == frozenset()
        assert LEGAL_TRANSITIONS[RunStage.FAILED] == frozenset()

    def test_fail_records_reason_and_is_terminal(self) -> None:
        state = RunState(run_id="r")
        state.advance(RunStage.DISCOVERY, at=_AT)
        state.fail("provider exploded", at=_AT)
        assert state.stage is RunStage.FAILED
        assert state.failure_reason == "provider exploded"
        assert state.is_terminal
        assert not state.can_advance(RunStage.SPECIFICATION)

    def test_pipeline_stages_are_linear_except_the_qa_revision_edges(self) -> None:
        """Every stage has one successor, except QA which may also rewind."""
        revision_edges: dict[RunStage, set[RunStage]] = {
            RunStage.QA: {RunStage.CONTENT, RunStage.ASSESSMENT}
        }
        for current, nxt in zip(PIPELINE_STAGES, PIPELINE_STAGES[1:], strict=False):
            expected = {nxt, RunStage.FAILED} | revision_edges.get(current, set())
            assert LEGAL_TRANSITIONS[current] == frozenset(expected)
        assert LEGAL_TRANSITIONS[PIPELINE_STAGES[-1]] == frozenset(
            {RunStage.COMPLETE, RunStage.FAILED}
        )

    def test_revision_edges_are_only_opened_by_qa(self) -> None:
        assert set(REVISION_TARGETS) == {RunStage.QA}
        assert REVISION_TARGETS[RunStage.QA] == frozenset({RunStage.CONTENT, RunStage.ASSESSMENT})

    def test_revision_edges_point_backwards(self) -> None:
        for source, targets in REVISION_TARGETS.items():
            for target in targets:
                assert PIPELINE_STAGES.index(target) < PIPELINE_STAGES.index(source)

    def test_revision_budget_is_bounded(self) -> None:
        state = RunState(run_id="r")
        for expected in range(1, MAX_REVISIONS + 1):
            assert state.begin_revision() == expected
        assert state.revisions_exhausted
        with pytest.raises(WorkflowError) as raised:
            state.begin_revision()
        assert raised.value.code == "REVISION_BUDGET_EXHAUSTED"
        assert state.revisions == MAX_REVISIONS
