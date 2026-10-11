# Codebase Gaps and Bugs — Remediation Plan

**Date:** 2026-10-11
**Scope:** Whole-codebase analysis; verified bugs + gaps + phased fix plan.
**Method:** Coverage run (878 passing) + four parallel exploration sweeps (orchestration,
research, schemas/discovery, packaging/models/CLI) + direct read-verification of every
item marked **VERIFIED** at its `file:line`. No code changes made by this audit.

Severity key:
- **P0** — produces wrong output or a documented live path that is broken.
- **P1** — violates an ADR/contract (reproducibility, routing semantics).
- **P2** — robustness / CLI hygiene (crash-on-bad-input, unclosed resources).
- **P3** — dead code / architectural drift.

---

## 1. Verified bugs (fix first)

### 1.1 P0 — `openai-compatible` provider kind is unreachable via CLI/env (TASK-011 regression)
**VERIFIED.** `OpenAICompatibleModel.kind = "openai_compatible"` (src/lpf/models/providers/
openai_compatible.py:26) but the CLI choice and env/toml values use the hyphen form
`"openai-compatible"` (cli.py; `LPF_PROVIDER`; README). `create_live_model` keys
`_KIND_CLASSES` by `kind` and looks up `kind.lower()` (models/providers/__init__.py), so
`--model openai-compatible` / `LPF_PROVIDER=openai-compatible` → `KeyError` →
`ConfigError(UNKNOWN_MODEL_KIND)`. Only `ollama` actually wires end-to-end.
TASK-011 tests mock `lpf.cli.create_live_model`, so the real factory was never exercised.

**Fix:** one canonical string. Change `OpenAICompatibleModel.kind = "openai-compatible"`
(hyphen) and keep `ollama`, or add an alias map in `create_live_model`. Add an integration
test that drives the **real** `OpenAICompatibleModel` (real `create_live_model`, injected
fake httpx transport) for `openai-compatible`, `ollama`, and `mock`.

### 1.2 P0 — `factual_consistency` gate is owned by CONTENT but is research-owned
**VERIFIED.** revision.py:36-42 lists `factual_consistency` in `CONTENT_GATES`, but its only
inputs are research artifacts: `evidence_map.claims` and `verified_source_ids`
(qa_stage.py:258-268 → validators/factual.py). The revision cycle re-runs only
CONTENT/ASSESSMENT and never revisits research, so a failed `factual_consistency` with
`supported_claims==0` burns all 3 revisions and then FAILs the run — it can never recover.
A content rewrite cannot clear it; the CONTENT re-run is cosmetic.

**Fix:** move `factual_consistency` to `NON_REPAIRABLE_GATES` (conservative abort, matches
ADR-010), and treat "zero supported claims against cited sources" as a research failure
upstream rather than a content-repairable defect.

### 1.3 P0 — the run-level error handler crashes when the run is already terminal
**VERIFIED.** pipeline.py:309-323 `except LpfError` calls `state.fail(...)` unconditionally;
`fail()` calls `advance(FAILED)` (state.py:179-187), and from COMPLETE / any terminal stage
there is no legal FAILED edge, so `advance` raises `WorkflowError` (state.py:153-173). Today
the failure branch after `state.advance(RunStage.COMPLETE)` (pipeline.py:283) and the
`package_run` call (291-298) is latent, but any future LpfError raised post-completion turns
a failure into a traceback instead of a FAILED `FactoryRunResult`.

**Fix:** guard with `if not state.is_terminal(...)` before `state.fail`; emit the failure
event in both cases. Regression test: force `package_run` to raise `LpfError` after COMPLETE;
assert a FAILED `FactoryRunResult` and no `WorkflowError` escaping.

### 1.4 P0 — bare `ValueError` escapes the run loop as an unhandled traceback
**VERIFIED.** content_stage.py:86-90 raises `ValueError` when a schema'd model request
returns text (`WorkedExampleDraft requested but the model returned text`); model.py:82-85
does the same. These are not `LpfError`, so the `except LpfError` handler misses them and the
CLI surfaces a raw traceback with no FAILED run record.

**Fix:** raise a typed error that is a `LpfError` subclass (e.g. `ProviderError`) at the
boundary, or map `ValueError` → `LpfError` in the run loop. Test: inject a model stub that
returns `str` for a schema request; assert `FactoryRunResult` FAILED, not a raised
`ValueError`.

### 1.5 P0 — `schema_validity` gate can never fail; it is decorative
**VERIFIED.** qa_stage.py:204-214 hard-wires a `schema_validity` gate with
`status=PASSED, score=1.0`. It appears in the gate list, in `NON_REPAIRABLE_GATES`
(revision.py:61), and is referenced by revision/QA docs, but it is never actually evaluated —
pydantic enforces schemas at construction time, so there is nothing for the gate to check.

**Fix:** remove the gate from qa_stage.py and from the revision ownership table, and document
that schema conformance is enforced by pydantic construction (assert artifact models are the
canonical check). Alternative (preferred only if a *recorded* gate matters): actually re-parse
each artifact and emit PASSED/FAILED. Pick one; do not keep a fake gate.

---

## 2. Reproducibility / contract violations (P1)

### 2.1 Live runs are not reproducible given identical provider responses (ADR-009)
**VERIFIED.** `new_id()` = `uuid.uuid4().hex` (domain/identity.py:15-17); live providers set
`source_id` to a fresh uuid (arxiv.py:95, wikimedia.py:99, tavily.py:100, searxng.py:80).
`source_id` flows into `VerifiedSource.source_id` → `EvidenceClaim.source_ids` →
`content_hash` (identity.py:20-28 hashes `model_dump(exclude={"content_hash"})`). Offline MOCK
is deterministic (`ctx.id`), so the E2E determinism tests pass, but two live replays of
byte-identical provider responses diverge — contradicting ADR-009's
"reproducible given identical provider responses".

**Fix:** make live `source_id` derive deterministically from `(provider, url/doi)` (stable
slug / seeded id), reserving uuid for genuinely unique cases; ensure `_normalise_report`
(research_stage.py:140-152) normalizes `source_id` alongside `verified_at`/`id`/`created_at`.
Regression test: run the same fake-provider responses twice; assert identical report +
`content_hash`.

### 2.2 Gate-name sets are duplicated string literals with no cross-check
**VERIFIED.** revision.py `CONTENT_GATES`/`ASSESSMENT_GATES`/`NON_REPAIRABLE_GATES` duplicate
the literal names passed to `_gate_from_result(name=...)` in qa_stage.py. A typo or a new
gate routes to "unknown → abort" silently instead of being a routing bug.

**Fix:** single source of truth (constants module, e.g. `lpf.qa.gates`); unit test asserting
every gate name emitted by qa_stage appears in exactly one revision set.

---

## 3. Robustness / CLI hygiene (P2)

- **3.1 Bad `LPF_TIMEOUT` crashes with a raw `ValueError`** — `int(os.environ[...])`
  (config.py:124) on `"1.5"`/`"abc"` → traceback. Fix: tolerant parse with a readable
  `ConfigError`, reject non-positive.
- **3.2 `run_id` path traversal** — unvalidated `--run-id` (cli.py:37) becomes the archive
  member name and artifact filenames (bundle.py:43, packaging_stage.py:52-55). `..\..\evil`
  (Windows) and `sub\nested` reproduce. Fix: strict slug/basename validation for `run_id` and
  archive members; traversal regression tests on both separators.
- **3.3 Async HTTP clients never closed** — live model and research providers construct
  `httpx.AsyncClient` and never `aclose()`. One-shot CLI is tolerable; in-process reuse leaks.
  Fix: `aclose()` in `__aexit__` / finalizer, or a pipeline lifespan.
- **3.4 Research providers ignore the configured timeout** — hardcoded 20s in `build_client`
  vs `config.timeout_seconds`; a live run can hang ignoring `LPF_TIMEOUT`. Fix: thread the
  timeout through provider construction; test with an injected `httpx.Transport`.
- **3.5 zlib/zip determinism overclaim** — bundle docs claim byte-identical outputs; verify
  against the pinned-epoch zip and scope the claim, then pin with a determinism test.

---

## 4. Contract honesty (P2 lightweight decisions)

- **`QualitySpec.minimum_score=0.8` is never enforced** — either thread it into gate
  evaluation or remove it; do not leave a dead knob.
- **`ProductSpec.quality.required_gates` is never threaded** — same decide-and-act.
- **`seed` parameter does nothing** — either thread it deterministically (seeded rng for the
  uuid-free id path) or remove/document the no-op. Aligns with ADR-008.
- **`date_span` annotation is wrong** (schemas/curriculum.py) and **`overall_status` ignores
  `SKIPPED`/`NOT_APPLICABLE`** — fix the annotation; decide whether non-PASSED statuses roll
  up.
- **`research_evidence` can only WARN** (qa_stage `_evidence_gate`) — a zero-evidence run
  still completes. Decide: fail with reason (strengthen gate) or document WARN-only intent.

---

## 5. Dead code / architecture drift (P3 — removes the coverage churn)

**Resolved in TASK-016 (Phase E):** the service methods, `discovery/validation.py`,
the scaffolding packages, `domain/evidence.py`, `models/registry.py`, the `prompts/`
templates, and the unreachable `EventType` members below were all removed. The
"parallel model duplication" item remains open as a future ADR (out of scope).

- **`lpf/research/service.py` at 62% coverage** — most public methods unused by the pipeline
  (`search_web`/`search_academic`/`search_wiki`/`extract_url`/`rank_sources`/`verify_source`/
  `execute_plan`); only `execute_plan_questions` is used. Fix-or-remove.
- **`lpf/discovery/validation.py` is unwired and self-contradictory** — `check_discovery_brief`
  (discovery/validation.py:130-139) validates `brief.outcome_ids` against LearningObjective
  ids, but its own producer sets `outcome_ids=[outcomes.id]` (discovery_stage.py:199). Latent
  because nothing calls it. Target: wire it into the stage (after fixing the id contract) or
  delete it.
- **Scaffolding packages** with single-line `__init__`: `agents/`, `crews/`, `api/`,
  `content/`, `exercises/`, `learning/`, `memory/`, `qa/`, `rendering/`, `review/`,
  `revision/`, `tools/`, `verification/` — remove or map to ROADMAP milestones.
- **`domain/evidence.py` and oversized `__all__` exports** — several exports have no
  reachable consumer; trim or document.
- **Parallel model duplication** — three product-intent representations (domain vs schemas),
  two evidence concepts, three validation layers. **Big refactor: out of scope here, record as
  a future ADR.**
- **Dead `prompts/` templates and unused `EventType` members** — stages inline their prompts;
  every emitted event name should be reachable. Tie to the removals above.

---

## 6. Coverage targets for the next milestone

Resolved by TASK-016 (Phase E). `research/service.py` and `models/registry.py` were
removed or trimmed to their reachable surface; `cli.py` is now covered by the
failure-reporting and live-research tests.

| Package | Before | After TASK-016 | Target |
|---|---|---|---|
| `research/service.py` | 62% | removed (1 method kept, 100%) | ≥ 80% (or removed) |
| `models/registry.py` | 70% | removed (dead prompt machinery) | ≥ 80% |
| `cli.py` | 91% | 99% | ≥ 95% |
| **Total** | 96% | **97.81%** (881 passing) | `--cov-fail-under=97` |

---

## 7. Phased remediation plan

Each phase = its own TASK entry in `tasks.md`, with: implementation, regression tests, full
`pytest -q` + ruff, a mutation micro-harness where the fix is non-trivial, docs touch, commit
+ push. Marker for stepwise work; never stage `research/scoring.py`.

- **Phase A — P0 correctness:** items 1.1–1.5. **DONE — TASK-012.**
- **Phase B — reproducibility (ADR-008/009):** items 2.1–2.2. **DONE — TASK-013.**
  (`source_id` is now `seeded_id(provider, url)` in every shipped adapter; stage
  boundary normalises the rest, so identical responses → byte-identical runs.
  Gate names now live in `lpf.orchestration.gates` and route through it.)
- **Phase C — CLI hygiene:** items 3.1–3.5. **DONE — TASK-014.**
  (`LPF_TIMEOUT` parses tolerantly; `validate_run_id` guards the pipeline
  boundary; owned HTTP clients are closed via `aclose()`; providers take the
  configured timeout; the bundle's byte-identity claim is scoped to a zlib build
  and pinned by a metadata test.)
- **Phase D — contract honesty:** items 4.*. **DONE — TASK-015.**
  (`QualitySpec.minimum_score` and `required_gates` are now enforced by the QA stage
  via a new `minimum_score` gate and the `required_gates_present` check; the stale
  `schema_validity` default was removed; the dead `seed` knob (CLI/`RunContext`/manifest)
  was deleted; `date_span` returns POSIX floats; `overall_status` documents that
  `SKIPPED`/`NOT_APPLICABLE` do not roll up; `ConstraintsSpec.evidence_required` now
  makes a zero-evidence run fail or merely warn.)
- **Phase E — dead code removal (the coverage lever):** items 5.* scoped removals, then
  re-run coverage and record new numbers. **DONE — TASK-016.**
  (`research/service.py` trimmed to the one method the pipeline uses; `discovery/validation.py`
  and its tests deleted; all scaffolding packages (`agents/`, `crews/`, `api/`, `content/`,
  `exercises/`, `learning/`, `memory/`, `qa/`, `rendering/`, `review/`, `revision/`, `tools/`,
  `verification/`, `prompts/`) deleted along with `schemas/contract.py`, the dead
  `models/registry.py` prompt machinery, `domain/evidence.py`, and the unreachable
  `EventType.STAGE_FAILED`/`VALIDATION_WARNING` members; the `crew`/`render`/`api`/`all`
  extras left `pyproject.toml`. Suite 881 passing; total coverage
  97.81% with a `--cov-fail-under=97` gate now in `[tool.pytest.ini_options]`.)
- **Phase F — docs + milestone:** ROADMAP/version_history update, milestone bump.
  **DONE — TASK-017.** (The v0.8.1 audit milestone is closed: ROADMAP Phase 26 now
  records the enforced 97% coverage floor, `tasks.md` marks the milestone complete and
  opens v0.9.0 ("real prose end to end"), and `version_history.md` Current Status
  declares v0.8.1 done. The audit's remediation plan as a whole is complete.)

## 8. Proposed task tracking

- TASK-012 — Phase A (P0 bug fixes 1.1–1.5)
- TASK-013 — Phase B (determinism/source-of-truth gates)
- TASK-014 — Phase C (CLI/config hygiene)
- TASK-015 — Phase D (contract knobs are real or gone)
- TASK-016 — Phase E (dead code removal + coverage gate)
- TASK-017 — Phase F (milestone close: ROADMAP/version_history update)