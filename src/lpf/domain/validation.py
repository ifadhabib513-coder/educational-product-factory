"""Validation functions for cross-artifact consistency."""

from __future__ import annotations

from lpf.domain.curriculum import CurriculumBlueprint
from lpf.errors import ValidationError
from lpf.result import Result, err, ok


def check_objective_references(
    blueprint: CurriculumBlueprint,
    objective_ids: set[str],
) -> Result[CurriculumBlueprint, ValidationError]:
    """Verify that every objective_id in the blueprint resolves to a known objective.

    Also checks belt-and-suspenders: a unit with empty objective_ids is an error
    despite the min_length=1 guard on the model.
    """
    missing: list[dict[str, str]] = []

    for unit in blueprint.units:
        if not unit.objective_ids:
            missing.append({"unit_id": unit.unit_id, "objective_id": "(empty)"})
            continue
        for obj_id in unit.objective_ids:
            if obj_id not in objective_ids:
                missing.append({"unit_id": unit.unit_id, "objective_id": obj_id})

    if missing:
        return err(
            ValidationError(
                code="MISSING_OBJECTIVE_REFS",
                message=f"Blueprint references {len(missing)} unresolvable objective(s)",
                details={"missing": missing},
            )
        )

    return ok(blueprint)
