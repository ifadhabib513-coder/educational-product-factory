"""Tests for domain schemas — planning spine."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.curriculum import CurriculumBlueprint, CurriculumUnit
from lpf.domain.identity import compute_content_hash, new_id, with_content_hash
from lpf.domain.learner import LearnerProfile
from lpf.domain.objectives import BloomLevel, LearningObjective, Prerequisite
from lpf.domain.product import ProductDefinition
from lpf.domain.validation import check_objective_references

# ---------------------------------------------------------------------------
# Helpers: build a full valid plan
# ---------------------------------------------------------------------------


def _make_profile() -> LearnerProfile:
    return LearnerProfile(
        subject="Physics",
        level="high-school",
        goals=["Understand projectile motion"],
        challenges=["Confusion about vertical vs horizontal components"],
        prior_knowledge=["Basic kinematics"],
        constraints=["No calculus"],
    )


def _make_product(profile: LearnerProfile) -> ProductDefinition:
    return ProductDefinition(
        title="Projectile Motion Mastery",
        subject="Physics",
        topic="Projectile Motion",
        level="high-school",
        problem_statement="Student confuses vertical and horizontal motion components",
        learner_profile_id=profile.id,
    )


def _make_objectives() -> list[LearningObjective]:
    return [
        LearningObjective(
            statement="Define horizontal and vertical components of projectile motion",
            bloom_level=BloomLevel.REMEMBER,
        ),
        LearningObjective(
            statement="Calculate range and maximum height of a projectile",
            bloom_level=BloomLevel.APPLY,
        ),
        LearningObjective(
            statement="Explain why horizontal velocity is constant in ideal conditions",
            bloom_level=BloomLevel.UNDERSTAND,
        ),
    ]


def _make_prerequisites(objs: list[LearningObjective]) -> list[Prerequisite]:
    return [
        Prerequisite(
            prerequisite_objective_id=objs[0].id,
            objective_id=objs[1].id,
            rationale="Must understand components before calculating",
        ),
    ]


def _make_blueprint(objs: list[LearningObjective]) -> CurriculumBlueprint:
    return CurriculumBlueprint(
        title="Projectile Motion Curriculum",
        units=[
            CurriculumUnit(
                unit_id="u1",
                title="Components",
                objective_ids=[objs[0].id],
                order=1,
            ),
            CurriculumUnit(
                unit_id="u2",
                title="Calculations",
                objective_ids=[objs[1].id, objs[2].id],
                order=2,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tests: extra="forbid"
# ---------------------------------------------------------------------------


class TestExtraForbid:
    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            LearnerProfile(subject="Math", level="HS", bogus_field="nope")  # type: ignore[call-arg]

    def test_frozen_assignment_raises(self) -> None:
        profile = _make_profile()
        with pytest.raises(ValidationError, match="frozen"):
            profile.subject = "Chemistry"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self) -> None:
        p1 = _make_profile()
        p2 = p1.model_copy()
        h1 = compute_content_hash(p1)
        h2 = compute_content_hash(p2)
        assert h1 == h2

    def test_sensitive_to_change(self) -> None:
        p1 = _make_profile()
        p2 = p1.model_copy(update={"subject": "Chemistry"})
        assert compute_content_hash(p1) != compute_content_hash(p2)

    def test_stable_across_json_roundtrip(self) -> None:
        p1 = _make_profile()
        h1 = compute_content_hash(p1)
        data = p1.model_dump(mode="json")
        p2 = LearnerProfile.model_validate(data)
        h2 = compute_content_hash(p2)
        assert h1 == h2

    def test_with_content_hash_excludes_itself(self) -> None:
        p = with_content_hash(_make_profile())
        h = compute_content_hash(p)
        assert h == p.content_hash


# ---------------------------------------------------------------------------
# Tests: new_id
# ---------------------------------------------------------------------------


class TestNewId:
    def test_unique(self) -> None:
        assert new_id() != new_id()

    def test_hex_format(self) -> None:
        id_val = new_id()
        assert len(id_val) == 32
        int(id_val, 16)  # should not raise


# ---------------------------------------------------------------------------
# Tests: full valid plan
# ---------------------------------------------------------------------------


class TestFullPlan:
    def test_build_complete_plan(self) -> None:
        profile = _make_profile()
        product = _make_product(profile)
        objectives = _make_objectives()
        prereqs = _make_prerequisites(objectives)
        blueprint = _make_blueprint(objectives)

        assert product.artifact_type == "product_definition"
        assert product.learner_profile_id == profile.id
        assert len(objectives) == 3
        assert len(blueprint.units) == 2
        assert len(prereqs) == 1


# ---------------------------------------------------------------------------
# Tests: check_objective_references
# ---------------------------------------------------------------------------


class TestCheckObjectiveReferences:
    def test_ok_path(self) -> None:
        objs = _make_objectives()
        blueprint = _make_blueprint(objs)
        obj_ids = {o.id for o in objs}
        result = check_objective_references(blueprint, obj_ids)
        from lpf.result import is_ok

        assert is_ok(result)

    def test_err_path_missing_id(self) -> None:
        objs = _make_objectives()
        blueprint = _make_blueprint(objs)
        obj_ids = {objs[0].id}
        result = check_objective_references(blueprint, obj_ids)
        from lpf.result import is_err

        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_OBJECTIVE_REFS"
        assert "missing" in error.details
        assert len(error.details["missing"]) > 0

    def test_err_path_empty_objective_ids(self) -> None:
        bad_unit = CurriculumUnit.model_construct(
            unit_id="u1", title="Empty", objective_ids=[], order=1
        )
        blueprint = CurriculumBlueprint.model_construct(title="Bad Blueprint", units=[bad_unit])
        result = check_objective_references(blueprint, set())
        from lpf.result import is_err

        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_OBJECTIVE_REFS"
        assert any(m["objective_id"] == "(empty)" for m in error.details["missing"])
