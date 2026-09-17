"""Validation functions for cross-artifact consistency."""

from __future__ import annotations

from lpf.domain.curriculum import CurriculumBlueprint
from lpf.domain.misconception import Misconception
from lpf.errors import ValidationError
from lpf.result import Result, err, ok


def _check_id_refs(
    source_id: str,
    ref_label: str,
    ids: list[str],
    known_ids: set[str],
) -> list[dict[str, str]]:
    """Check a list of IDs against known IDs; return missing entries."""
    missing: list[dict[str, str]] = []
    for obj_id in ids:
        if obj_id not in known_ids:
            missing.append({ref_label: source_id, "objective_id": obj_id})
    return missing


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
        missing.extend(_check_id_refs(unit.unit_id, "unit_id", unit.objective_ids, objective_ids))

    if missing:
        return err(
            ValidationError(
                code="MISSING_OBJECTIVE_REFS",
                message=f"Blueprint references {len(missing)} unresolvable objective(s)",
                details={"missing": missing},
            )
        )

    return ok(blueprint)


def check_misconception_objective_refs(
    misconceptions: list[Misconception],
    objective_ids: set[str],
) -> Result[list[Misconception], ValidationError]:
    """Verify that every objective_id in each misconception resolves to a known objective."""
    missing: list[dict[str, str]] = []

    for m in misconceptions:
        if not m.objective_ids:
            missing.append({"misconception_id": m.id, "objective_id": "(empty)"})
            continue
        missing.extend(_check_id_refs(m.id, "misconception_id", m.objective_ids, objective_ids))

    if missing:
        return err(
            ValidationError(
                code="MISSING_OBJECTIVE_REFS",
                message=f"Misconceptions reference {len(missing)} unresolvable objective(s)",
                details={"missing": missing},
            )
        )

    return ok(misconceptions)
