"""Tests for domain schemas — quality models (Stage 2b-ii)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.identity import compute_content_hash, with_content_hash
from lpf.domain.quality import (
    Finding,
    GateStatus,
    QualityGate,
    Severity,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding() -> Finding:
    return Finding(
        severity=Severity.CRITICAL,
        location="chapter_3.exercise_5",
        problem="Incorrect answer: 2+2=5",
        evidence="Answer key states 5",
        suggested_fix="Change answer to 4",
    )


def _make_gate(gate_name: str = "factual_accuracy") -> QualityGate:
    return with_content_hash(
        QualityGate(
            gate_name=gate_name,
            status=GateStatus.PASSED,
            score=0.95,
            findings=[],
        )
    )


def _make_verification() -> VerificationResult:
    return with_content_hash(
        VerificationResult(
            gates=[
                _make_gate("schema_validity"),
                with_content_hash(
                    QualityGate(
                        gate_name="factual_accuracy",
                        status=GateStatus.PASSED,
                        score=0.9,
                    )
                ),
                with_content_hash(
                    QualityGate(
                        gate_name="math_correctness",
                        status=GateStatus.WARNING,
                        score=0.7,
                        findings=[
                            Finding(
                                severity=Severity.MAJOR,
                                location="chapter_2",
                                problem="Approximate answer",
                            )
                        ],
                    )
                ),
            ],
            overall_status=GateStatus.WARNING,
            overall_score=0.85,
            iteration=1,
            max_iterations=3,
        )
    )


# ---------------------------------------------------------------------------
# Tests: GateStatus enum
# ---------------------------------------------------------------------------


class TestGateStatus:
    def test_all_values(self) -> None:
        values = [gs.value for gs in GateStatus]
        assert "passed" in values
        assert "failed" in values
        assert "warning" in values
        assert "skipped" in values
        assert "not_applicable" in values

    def test_count(self) -> None:
        assert len(GateStatus) == 5


# ---------------------------------------------------------------------------
# Tests: Severity enum
# ---------------------------------------------------------------------------


class TestSeverity:
    def test_all_values(self) -> None:
        values = [s.value for s in Severity]
        assert "critical" in values
        assert "major" in values
        assert "minor" in values

    def test_count(self) -> None:
        assert len(Severity) == 3


# ---------------------------------------------------------------------------
# Tests: Finding
# ---------------------------------------------------------------------------


class TestFinding:
    def test_construction(self) -> None:
        f = _make_finding()
        assert f.severity == Severity.CRITICAL
        assert f.location == "chapter_3.exercise_5"
        assert f.problem == "Incorrect answer: 2+2=5"
        assert f.evidence == "Answer key states 5"
        assert f.suggested_fix == "Change answer to 4"

    def test_minimal(self) -> None:
        f = Finding(
            severity=Severity.MINOR,
            location="intro",
            problem="Typo",
        )
        assert f.evidence is None
        assert f.suggested_fix is None

    def test_frozen(self) -> None:
        f = _make_finding()
        with pytest.raises(ValidationError, match="frozen"):
            f.severity = Severity.MINOR  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        f1 = _make_finding()
        data = f1.model_dump(mode="json")
        f2 = Finding.model_validate(data)
        assert f1 == f2


# ---------------------------------------------------------------------------
# Tests: QualityGate
# ---------------------------------------------------------------------------


class TestQualityGate:
    def test_construction(self) -> None:
        g = _make_gate()
        assert g.artifact_type == "quality_gate"
        assert g.gate_name == "factual_accuracy"
        assert g.status == GateStatus.PASSED
        assert g.score == 0.95
        assert g.findings == []

    def test_defaults(self) -> None:
        g = QualityGate(
            gate_name="coverage",
            status=GateStatus.FAILED,
        )
        assert g.score is None
        assert g.findings == []
        assert g.checked_at is not None

    def test_with_findings(self) -> None:
        f = _make_finding()
        g = QualityGate(
            gate_name="consistency",
            status=GateStatus.FAILED,
            score=0.3,
            findings=[f],
        )
        assert len(g.findings) == 1
        assert g.findings[0].severity == Severity.CRITICAL

    def test_frozen(self) -> None:
        g = _make_gate()
        with pytest.raises(ValidationError, match="frozen"):
            g.gate_name = "new_name"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        g1 = _make_gate()
        h1 = compute_content_hash(g1)
        data = g1.model_dump(mode="json")
        g2 = QualityGate.model_validate(data)
        h2 = compute_content_hash(g2)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: VerificationResult
# ---------------------------------------------------------------------------


class TestVerificationResult:
    def test_construction(self) -> None:
        vr = _make_verification()
        assert vr.artifact_type == "verification_result"
        assert len(vr.gates) == 3
        assert vr.overall_status == GateStatus.WARNING
        assert vr.overall_score == 0.85
        assert vr.iteration == 1
        assert vr.max_iterations == 3

    def test_defaults(self) -> None:
        vr = VerificationResult(
            gates=[_make_gate()],
            overall_status=GateStatus.PASSED,
        )
        assert vr.overall_score is None
        assert vr.iteration == 1
        assert vr.max_iterations == 3

    def test_empty_gates_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            VerificationResult(
                gates=[],
                overall_status=GateStatus.PASSED,
            )

    def test_frozen(self) -> None:
        vr = _make_verification()
        with pytest.raises(ValidationError, match="frozen"):
            vr.iteration = 2  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        vr1 = _make_verification()
        h1 = compute_content_hash(vr1)
        data = vr1.model_dump(mode="json")
        vr2 = VerificationResult.model_validate(data)
        h2 = compute_content_hash(vr2)
        assert h1 == h2

    def test_single_gate(self) -> None:
        vr = VerificationResult(
            gates=[_make_gate("only_gate")],
            overall_status=GateStatus.PASSED,
            overall_score=1.0,
        )
        assert len(vr.gates) == 1
        assert vr.gates[0].gate_name == "only_gate"
