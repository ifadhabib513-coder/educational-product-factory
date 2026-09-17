# ADR-001: Project Foundation

**Status:** Accepted
**Date:** 2026-09-17

## Context

The AI Educational Product Factory repository is empty. We need a minimal, testable foundation before implementing domain logic.

## Decisions

### 1. Package structure: `src/lpf/`

Uses the `src/` layout to avoid import confusion during development. The package is named `lpf` (Learning Product Factory) for brevity.

### 2. Build system: hatchling

PEP 621 compliant, minimal configuration, well-supported. Avoids setuptools complexity.

### 3. Result[T, E] vs Exceptions

**Boundary:**
- `Result[T, E]` is for **expected, recoverable failures** — validation errors, provider timeouts, workflow state failures, missing optional data.
- **Exceptions** are for **programmer errors and exceptional conditions** — `TypeError`, `AttributeError`, `FileNotFoundError` (when file absence is unexpected), configuration system failures.

**Rationale:** Result types make failure paths explicit in function signatures. Callers must handle both cases. Exceptions remain appropriate when the caller cannot reasonably recover.

**Examples:**
- A question schema fails validation → `Err(ValidationError(...))`
- An LLM provider times out → `Err(ProviderError(...))`
- A required argument is missing → `TypeError` (programmer error)
- An enum receives an invalid value → `ValueError` (programmer error)

### 4. Configuration: frozen dataclass + explicit env loading

No magic, no metaclass tricks. `load_config()` reads environment variables explicitly. The dataclass is frozen to prevent accidental mutation after initialization.

### 5. CLI: click

Lightweight, well-tested, no type-safety issues. `typer` adds value for complex CLIs but is unnecessary at this stage.

### 6. Linting: ruff only

`ruff check` for linting, `ruff format` for formatting. Single tool, fast, covers pyflakes, pycodestyle, isort, bugbear, and more. No black, no isort, no flake8.

### 7. CI: GitHub Actions

Two jobs: `lint` (ruff check + format) and `test` (pytest on Python 3.12 and 3.14).

## Consequences

- Clean separation of concerns from day one
- Easy to add new modules without circular imports
- Testable without real LLM providers
- CI catches formatting and lint issues before merge
