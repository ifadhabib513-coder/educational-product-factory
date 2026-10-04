"""Tests for the run event log."""

from __future__ import annotations

from lpf.orchestration.context import RunContext
from lpf.orchestration.events import EventLog, EventType
from lpf.orchestration.state import RunStage


class TestEventLog:
    def test_sequence_numbers_are_assigned_in_order(self) -> None:
        ctx = RunContext(run_id="r")
        log = EventLog(run_id="r")
        first = log.emit(
            EventType.RUN_STARTED, stage=RunStage.CREATED, message="go", timestamp=ctx.now()
        )
        second = log.emit(
            EventType.STAGE_STARTED,
            stage=RunStage.DISCOVERY,
            message="discovery",
            timestamp=ctx.now(),
        )
        assert first.seq == 1
        assert second.seq == 2

    def test_artifact_ids_default_to_empty_tuple(self) -> None:
        log = EventLog(run_id="r")
        event = log.emit(
            EventType.STAGE_COMPLETED,
            stage=RunStage.DISCOVERY,
            message="done",
            timestamp=RunContext(run_id="r").now(),
        )
        assert event.artifact_ids == ()

    def test_to_dicts_round_trips_enums_to_strings(self) -> None:
        ctx = RunContext(run_id="r")
        log = EventLog(run_id="r")
        log.emit(
            EventType.STAGE_COMPLETED,
            stage=RunStage.DISCOVERY,
            message="done",
            timestamp=ctx.now(),
            artifact_ids=("a-1",),
        )
        payload = log.to_dicts()
        assert payload[0]["event_type"] == "stage_completed"
        assert payload[0]["stage"] == "discovery"
        assert payload[0]["artifact_ids"] == ["a-1"]
