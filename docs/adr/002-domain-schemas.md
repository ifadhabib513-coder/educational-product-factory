# ADR-002: Domain Schemas

**Status:** Accepted
**Date:** 2026-09-17

## Context

The product factory needs typed, versioned domain models that all pipeline stages consume. These models must be subject-agnostic, serializable, and verifiable.

## Decisions

### 1. Pydantic v2 BaseModel for all domain models

Pydantic v2 provides serialization, validation, JSON schema generation, and frozen models out of the box. No custom ORM, no dataclass reimplementation.

### 2. Shared model config: frozen=True, extra="forbid"

- **frozen=True** — immutable after creation; copy-on-update via `model_copy(update=...)`
- **extra="forbid"** — rejects unknown fields; prevents silent data drift

### 3. IDs: uuid4 hex strings

Generated at creation time via `new_id()`. IDs are opaque identifiers, not content-addressed. Reproducibility is carried by `content_hash`, not by IDs.

### 4. content_hash: SHA-256 over canonical JSON

- Computed via `compute_content_hash(model)`
- Excludes the `content_hash` field itself
- Uses `model_dump(mode="json")`, `sort_keys=True`, `separators=(",",":")`, `ensure_ascii=False`
- `with_content_hash(model)` returns a copy with hash set

### 5. Timestamps: UTC datetimes

All `created_at` fields default to `datetime.now(UTC)`. No timezone-naive timestamps.

### 6. Referential integrity via functions returning Result

Cross-artifact validation (e.g., `check_objective_references`) returns `Result[T, ValidationError]` rather than raising exceptions. Callers handle both paths.

### 7. Artifact hierarchy

- **Root artifacts** inherit `ArtifactBase`: ProductDefinition, CurriculumBlueprint, LearningObjective, LearnerProfile
- **Embedded value objects** are plain `BaseModel`: Prerequisite, CurriculumUnit, GeneratorInfo

### 8. Two-layer validation (belt and suspenders)

Schema guards and validation functions both exist. For example, `CurriculumUnit.objective_ids` has `Field(min_length=1)` as the first line of defense. The `check_objective_references()` function independently checks for empty objective_ids as a second line of defense. This ensures code paths that bypass Pydantic validation (e.g., `model_construct()`) are still caught by the validation function.

## Consequences

- Models are self-documenting via JSON schema
- Serialization is trivial (`.model_dump_json()`, `.model_validate_json()`)
- Frozen models prevent accidental mutation
- Content hashes enable change detection and deduplication
