"""Tests for domain schemas — enhanced ProductSpec (Phase 1 alignment)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.identity import compute_content_hash, with_content_hash
from lpf.domain.objectives import BloomLevel
from lpf.domain.product import (
    ConstraintsSpec,
    FormatSpec,
    LearningSpec,
    ProductDefinition,
    ProductSpec,
    ProductType,
    QualitySpec,
    TargetAudience,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_target_audience() -> TargetAudience:
    return TargetAudience(
        level="high-school",
        age_range="14-18",
        exam_target="GCSE Chemistry",
        language="en",
    )


def _make_format_spec() -> FormatSpec:
    return FormatSpec(
        primary=ProductType.BOOK,
        pages=120,
        exercise_count=60,
        assessment_count=3,
        answer_key=True,
        include_citations=True,
    )


def _make_learning_spec() -> LearningSpec:
    return LearningSpec(
        progression=["understand", "apply", "analyze", "master"],
        mastery_criteria="Score 80% on final assessment",
        bloom_target=BloomLevel.APPLY,
    )


def _make_constraints_spec() -> ConstraintsSpec:
    return ConstraintsSpec(
        evidence_required=True,
        citation_required=True,
        calculator_allowed=False,
        exam_alignment="AQA GCSE Chemistry",
        max_pages=150,
    )


def _make_quality_spec() -> QualitySpec:
    return QualitySpec(
        minimum_score=0.85,
        required_gates=["schema", "factual", "math", "coverage"],
    )


def _make_product_spec() -> ProductSpec:
    return with_content_hash(
        ProductSpec(
            title="Chemical Equations Mastery",
            product_type=ProductType.BOOK,
            subject="Chemistry",
            topic="Chemical Equations",
            language="en",
            audience=_make_target_audience(),
            format=_make_format_spec(),
            learning=_make_learning_spec(),
            constraints=_make_constraints_spec(),
            quality=_make_quality_spec(),
            problem_statement="Students struggle with balancing chemical equations",
            learner_profile_id="profile_001",
        )
    )


# ---------------------------------------------------------------------------
# Tests: ProductType enum
# ---------------------------------------------------------------------------


class TestProductType:
    def test_all_values(self) -> None:
        values = [pt.value for pt in ProductType]
        assert "book" in values
        assert "workbook" in values
        assert "revision_guide" in values
        assert "exam_prep" in values
        assert "practice_pack" in values
        assert "flashcard_pack" in values
        assert "study_planner" in values
        assert "diagnostic" in values
        assert "recovery_program" in values
        assert "learning_system" in values
        assert "course" in values
        assert "worksheet_pack" in values
        assert "challenge_pack" in values
        assert "product_suite" in values

    def test_count(self) -> None:
        assert len(ProductType) == 14


# ---------------------------------------------------------------------------
# Tests: TargetAudience
# ---------------------------------------------------------------------------


class TestTargetAudience:
    def test_construction(self) -> None:
        ta = _make_target_audience()
        assert ta.level == "high-school"
        assert ta.age_range == "14-18"
        assert ta.exam_target == "GCSE Chemistry"
        assert ta.language == "en"

    def test_defaults(self) -> None:
        ta = TargetAudience(level="university")
        assert ta.age_range is None
        assert ta.exam_target is None
        assert ta.language == "en"

    def test_frozen(self) -> None:
        ta = _make_target_audience()
        with pytest.raises(ValidationError, match="frozen"):
            ta.level = "primary"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: FormatSpec
# ---------------------------------------------------------------------------


class TestFormatSpec:
    def test_construction(self) -> None:
        fs = _make_format_spec()
        assert fs.primary == ProductType.BOOK
        assert fs.pages == 120
        assert fs.exercise_count == 60
        assert fs.assessment_count == 3
        assert fs.answer_key is True
        assert fs.include_citations is True

    def test_defaults(self) -> None:
        fs = FormatSpec(primary=ProductType.WORKBOOK)
        assert fs.pages is None
        assert fs.exercise_count is None
        assert fs.assessment_count is None
        assert fs.answer_key is True
        assert fs.include_citations is True


# ---------------------------------------------------------------------------
# Tests: LearningSpec
# ---------------------------------------------------------------------------


class TestLearningSpec:
    def test_construction(self) -> None:
        ls = _make_learning_spec()
        assert ls.progression == ["understand", "apply", "analyze", "master"]
        assert ls.mastery_criteria == "Score 80% on final assessment"
        assert ls.bloom_target == BloomLevel.APPLY

    def test_defaults(self) -> None:
        ls = LearningSpec()
        assert ls.progression == []
        assert ls.mastery_criteria is None
        assert ls.bloom_target is None


# ---------------------------------------------------------------------------
# Tests: ConstraintsSpec
# ---------------------------------------------------------------------------


class TestConstraintsSpec:
    def test_construction(self) -> None:
        cs = _make_constraints_spec()
        assert cs.evidence_required is True
        assert cs.citation_required is True
        assert cs.calculator_allowed is False
        assert cs.exam_alignment == "AQA GCSE Chemistry"
        assert cs.max_pages == 150

    def test_defaults(self) -> None:
        cs = ConstraintsSpec()
        assert cs.evidence_required is True
        assert cs.citation_required is True
        assert cs.calculator_allowed is None
        assert cs.exam_alignment is None
        assert cs.max_pages is None


# ---------------------------------------------------------------------------
# Tests: QualitySpec
# ---------------------------------------------------------------------------


class TestQualitySpec:
    def test_construction(self) -> None:
        qs = _make_quality_spec()
        assert qs.minimum_score == 0.85
        assert qs.required_gates == ["schema", "factual", "math", "coverage"]

    def test_defaults(self) -> None:
        qs = QualitySpec()
        assert qs.minimum_score == 0.8
        assert qs.required_gates == []


# ---------------------------------------------------------------------------
# Tests: ProductSpec (root artifact)
# ---------------------------------------------------------------------------


class TestProductSpec:
    def test_construction(self) -> None:
        ps = _make_product_spec()
        assert ps.artifact_type == "product_spec"
        assert ps.title == "Chemical Equations Mastery"
        assert ps.product_type == ProductType.BOOK
        assert ps.subject == "Chemistry"
        assert ps.topic == "Chemical Equations"
        assert ps.language == "en"
        assert ps.audience.level == "high-school"
        assert ps.format.primary == ProductType.BOOK
        assert ps.learning.bloom_target == BloomLevel.APPLY
        assert ps.constraints.calculator_allowed is False
        assert ps.quality.minimum_score == 0.85
        assert ps.learner_profile_id == "profile_001"

    def test_frozen(self) -> None:
        ps = _make_product_spec()
        with pytest.raises(ValidationError, match="frozen"):
            ps.title = "New title"  # type: ignore[misc]

    def test_unknown_field_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ProductSpec(
                title="Test",
                product_type=ProductType.BOOK,
                subject="Math",
                topic="Algebra",
                audience=TargetAudience(level="HS"),
                format=FormatSpec(primary=ProductType.BOOK),
                learning=LearningSpec(),
                constraints=ConstraintsSpec(),
                quality=QualitySpec(),
                problem_statement="test",
                learner_profile_id="p1",
                bogus_field="nope",  # type: ignore[call-arg]
            )

    def test_json_roundtrip(self) -> None:
        ps1 = _make_product_spec()
        h1 = compute_content_hash(ps1)
        data = ps1.model_dump(mode="json")
        ps2 = ProductSpec.model_validate(data)
        h2 = compute_content_hash(ps2)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: ProductDefinition (backward compatibility)
# ---------------------------------------------------------------------------


class TestProductDefinitionBackwardCompat:
    def test_still_works(self) -> None:
        pd = ProductDefinition(
            title="Old Style Product",
            subject="Physics",
            topic="Motion",
            level="high-school",
            problem_statement="Students confuse velocity and speed",
            learner_profile_id="profile_old",
        )
        assert pd.artifact_type == "product_definition"
        assert pd.title == "Old Style Product"

    def test_frozen(self) -> None:
        pd = ProductDefinition(
            title="Test",
            subject="Math",
            topic="Algebra",
            level="HS",
            problem_statement="test",
            learner_profile_id="p1",
        )
        with pytest.raises(ValidationError, match="frozen"):
            pd.title = "New"  # type: ignore[misc]
