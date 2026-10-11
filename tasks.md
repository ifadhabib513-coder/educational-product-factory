# Ralph Task Backlog: AI Educational Product Factory

> Managed by the Ralph autonomous loop. Tasks are executed sequentially from top to bottom.
> Each Ralph iteration picks the first uncompleted task `[ ]`, tests and verifies, marks it `[x]`, logs in `PROGRESS.md`, and commits to git.

---

## v0.7.0 Milestone Tasks

- [x] **TASK-001**: Implement Exact-Title Definitional Signal in Research Scoring
  - **Objective**: In `src/lpf/research/scoring.py` (and `relevance.py`), when query intent is `DEFINITIONAL` or `EXPLANATORY`, incorporate an exact/normalized title match signal so that an encyclopedic article matching the topic title exactly is promoted over incidental query mentions.
  - **Acceptance Criteria**:
    - Add a function (e.g. `exact_title_match(query: str, title: str) -> bool` or title normalization helper).
    - When intent is `DEFINITIONAL`, boost/weight candidates whose title matches the queried topic.
    - Write unit tests in `tests/test_research_intent_scoring.py` verifying exact-title definitional queries rank encyclopedic articles higher than incidental mentions.
    - Full pytest suite (671+ tests) and ruff linters pass.

- [x] **TASK-002**: Eliminate Spurious False-Positive Conflicts in Research Mock Sentences
  - **Objective**: As identified in v0.6.0 version history, mock canned sentences share bucket words causing the conflict detector to report 8 false-positive conflicts during offline pipeline runs.
  - **Acceptance Criteria**:
    - Inspect mock source texts and conflict detection keywords/buckets.
    - Adjust mock texts or bucket disambiguation so offline pipeline does not trigger spurious false-positive conflicts.
    - Ensure genuine conflict detection tests continue passing with zero regressions.
    - Full pytest suite and ruff linters pass.

- [x] **TASK-003**: Implement Factual Quality Gate Validator
  - **Objective**: Implement the factual consistency hard gate in `src/lpf/validators/` or `src/lpf/qa/` verifying generated lesson/claim assertions align with direct research evidence records.
  - **Acceptance Criteria**:
    - Schema validation and verification logic ensuring factual claims cite valid evidence record IDs.
    - Fails QA when assertions are ungrounded or contradictory to evidence.
    - Unit tests covering passing grounded content and failing ungrounded/conflicting content.
    - Full pytest suite and ruff linters pass.

- [x] **TASK-004**: Implement Numerical and Symbolic Gate Validator
  - **Objective**: Implement numerical/symbolic consistency validation for STEM/quantitative lessons and worked examples (e.g., matching calculation steps to final answers using deterministic Python/SymPy evaluation).
  - **Acceptance Criteria**:
    - Validator verifying mathematical consistency between worked example steps and answers.
    - Unit tests with both correct equations/calculations and flawed examples caught by the gate.
    - Full pytest suite and ruff linters pass.

- [x] **TASK-005**: Add Multi-Format Packaging (HTML and ZIP Bundle)
  - **Objective**: Extend `lpf.packaging` so `lpf generate` / packaging stage outputs clean standalone HTML and an archival ZIP bundle in addition to Markdown and JSON manifests.
  - **Acceptance Criteria**:
    - HTML generator template or converter for `product.md`.
    - ZIP bundler creating `<run_id>.zip` containing manifest, markdown, html, and json artifacts.
    - Unit tests in `tests/test_packaging.py` or `tests/test_e2e_pipeline.py`.
    - Full pytest suite and ruff linters pass.

- [x] **TASK-006**: Support Cyclic Stage Machine Revision Loop
  - **Objective**: Upgrade the stage machine from purely linear to allow cyclic transitions from `qa` failure back to `content` or `assessment` revision before retrying QA (up to a max revision count).
  - **Acceptance Criteria**:
    - Update state machine transition table to permit `qa -> content` on repairable QA findings.
    - Enforce bounded iteration count to prevent infinite revision loops.
    - Add tests verifying successful revision loop and eventual completion or abort.
    - Full pytest suite and ruff linters pass.

---

> **v0.7.0 milestone complete.** TASK-001 through TASK-006 are all checked. The
> next iteration should start a new milestone section rather than hunting for an
> unfinished `[ ]` above.

---

## v0.8.0 Milestone Tasks — Live Content (real writers behind the same seam)

> Motivation (from `version_history.md`): "the writing is the last major
> fiction." Evidence is already real (`--live-research`); lesson prose is still
> `DeterministicMockModel` text. These tasks turn the content stage from a mock
> into a real LLM call through the existing `ModelProvider` seam, keep the
> offline default byte-identical, and prove TASK-006's revision loop repairs a
> model-written defect. Assign the next sequence number; new tasks go to the
> newest section only, never the completed one.

- [x] **TASK-007**: Implement Live Model Provider Adapters (OpenAI-compatible and Ollama)
  - **Objective**: Turn `src/lpf/models/provider.py` into a real provider layer (ROADMAP Stage 7) — implement the existing `ModelProvider` protocol for OpenAI-compatible and Ollama HTTP endpoints, selectable per-run without touching any stage code. Structured output: lesson JSON parsed and pydantic-validated so a malformed reply is a typed `ValidationError` that fails the run, never a silent artifact.
  - **Acceptance Criteria**:
    - Adapters conform to `ModelProvider` and are injected via `FactoryPipeline(model=...)`; the offline default stays `DeterministicMockModel`.
    - Malformed provider output (bad JSON, wrong schema) raises `ValidationError` and fails the run before QA.
    - Unit tests use a deterministic fake HTTP transport; `tests/` never touches the network.
    - Full pytest suite and ruff linters pass.
  - **Implementation**:
    - New `src/lpf/models/providers/` package: `base.py` (`HttpChatModel` — the whole PyPI-visible behaviour: request build, `ProviderError` for transport/HTTP failures, `ModelProvider`-shaped `generate`, whitespace `count_tokens`), `openai_compatible.py` (`OpenAICompatibleModel`, `/chat/completions`, Bearer auth, `response_format: json_object`), `ollama.py` (`OllamaModel`, native `/api/chat`, `format: json`, no auth), and a `create_live_model(kind, ...)` factory (`ConfigError / UNKNOWN_MODEL_KIND`).
    - Structured output: when a schema is passed, the reply is parsed; malformed JSON or non-object JSON raises `ValidationError(code="MODEL_OUTPUT_NOT_JSON")` and a schema mismatch raises `ValidationError(code="MODEL_OUTPUT_INVALID_SCHEMA")`, both `LpfError`s so the pipeline fails the run cleanly (pipeline test: run FAILED at content, no QA events).
    - Selectable per run: `FactoryPipeline(model=OpenAICompatibleModel(...))` runs the full pipeline; the default stays `DeterministicMockModel`. End-to-end run with the live adapter is byte-identical across two runs (tree-hash test).
    - Tests: `tests/test_model_providers.py` (26 tests) over `httpx.MockTransport` — the same offline-transport convention as the research providers.
    - Mutation-tested 13/13 caught (JSON guard, non-dict guard, error codes, pydantic swallow, JSON request field, HTTP status guard, transport catch, both `parse_content` paths, both default model names, auth header, factory fallback).

- [x] **TASK-008**: Add Provider Resilience (retry, timeout, backoff)
  - **Objective**: Hosts fail; a content run must neither crash nor hang. Add bounded retry, timeout, and exponential backoff to live model calls and surface a stable `ProviderError` (an `LpfError`) when a provider stays down.
  - **Acceptance Criteria**:
    - A flaky fake provider (fails once then succeeds) completes; a constant-failure fake provider fails the run with a readable, deterministic message.
    - Retries are budgeted (no unbounded loops), reusing the HTTP transport patterns already in `research/transport.py`.
    - Unit tests with flaky/always-failing fake providers; full pytest suite and ruff linters pass.
  - **Implementation notes**: `HttpChatModel` gains `retry: RetryPolicy | None = None` (defaults to `DEFAULT_RETRY`) and `timeout_seconds` (builds the injected/real `AsyncClient` with it). `_post()` is one bounded loop over `range(1, max_attempts + 1)`: retries transport `httpx.HTTPError` and statuses in `retry_on_status` (429, 5xx), returns non-retryable responses immediately for the caller's `PROVIDER_HTTP_ERROR`. Backoff is `retry.delay_for(attempt)` (deterministic, no jitter). Exhaustion raises `PROVIDER_REQUEST_FAILED` carrying `"{attempts} attempt(s); last failure: ..."`. `OpenAICompatibleModel`/`OllamaModel`/`create_live_model` forward both options. Tests: flaky status/transport recovery, bounded call counts, non-retryable 4xx never replayed, recorded backoff delays `[0.25, 0.5]`, and an end-to-end constant-failure run whose `failure_reason` contains `PROVIDER_REQUEST_FAILED` and `3 attempt(s)`. Plus 8/8 mutation-kill harness. Suite: 834 passed, ruff clean.

- [x] **TASK-009**: Prove the Revision Loop Repairs a Model-Written Defect
  - **Objective**: TASK-006's cycle must hold with a real writer, not just an injected one: a (fake) live model that emits a wrong worked-example answer on its first draft is retried on the `qa  content` re-run, and the run completes.
  - **Acceptance Criteria**:
    - End-to-end test where the first draft fails `numerical_consistency` (or `factual_consistency`) and the repaired draft passes; `VerificationResult.iteration == 2`.
    - On-disk output is byte-identical across two identical runs; the budget-exhausted variant still fails cleanly.
    - Full pytest suite and ruff linters pass.
  - **Implementation notes**: APPLY-unit worked examples are now *written by the model* against the new `WorkedExampleDraft` schema (identity stamped by the Content stage), so a bad answer is genuinely the writer's defect, not a monkeypatched one. On a `qa  content` rewind the pipeline threads the failed gates' problems back into the rebuilt content prompts as `feedback` (`_revision_feedback` in `pipeline.py`), so the second draft is a repair: a fake live model over `httpx.MockTransport` writes `3 + 4 = 8` on a first draft and `3 + 4 = 7` once the prompt carries the failure. `DeterministicMockModel` answers `WorkedExampleDraft` with exactly the old canonical template, keeping the offline package byte-identical. New `tests/test_model_revision_loop.py`: repair converges (`iteration == 2`, `revisions == 1`, `qa  content` hop), only the repaired verification ships with `numerical_consistency` passed, repaired and exhausted runs are byte-identical, and the constant-defect run fails on "revision budget". Plus 4/4 mutation-kill harness. Suite: 839 passed, ruff clean.

- [x] **TASK-010**: Route Retrieval by Query Intent
  - **Objective**: "Retrieval is unrefined: questions are sent to every provider regardless of intent" (`version_history.md`). Prune the provider list per question so a beginner's definitional query does not retrieve preprints the scorer rejects by design.
  - **Acceptance Criteria**:
    - Per-question provider filtering/weighting keyed on intent, implemented in `research` (not in tests); offline mock behaviour unchanged or strictly improved.
    - Regression tests: definitional/explainatory queries no longer rank preprint-type sources ahead of encyclopedic ones for the canonical topic.
    - Live `--live-research` run still succeeds; full pytest suite and ruff linters pass.
  - **Implementation notes**: new `src/lpf/research/routing.py` owns the intent→provider suitability table (`provider_suitability`) and the never-empty prune (`prune_providers`). `ARXIV` is excluded for the beginner intents (DEFINITIONAL, EXPLANATORY, PROCEDURAL) and `WIKIMEDIA` for the paper intents (ACADEMIC_LITERATURE, EVIDENCE_SYNTHESIS, CURRENT); `GENERAL` keeps everything. `MOCK` (and `OFFICIAL`) appear in every set so the deterministic offline provider is never pruned away, and a single-suitable-empty set falls back to the caller's full list — a lone injected provider still retrieves. Both `ResearchRouter.plan` and the plan builder in `orchestration/research_stage.py` prune and rebuild each question's `SearchStrategy`/`SearchQuery`s, so the plan artifact and execution agree on which providers ran (router rebuild preserves per-provider `max_results`). New `tests/test_research_intent_routing.py` (23 tests) plus reworked `tests/test_research_provider_injection.py` cover the suitability table, router-level pruning independent of the plan builder, execution never calling a pruned provider, and end-to-end runs where a definitional "What is linear algebra?" yields only encyclopedic sources while "find papers about …" still queries arXiv. Six-point mutation harness, 6/6 killed. Suite: 862 passed, ruff clean. Live path is unchanged code-wise (the stage injects live providers and the router prunes them) but needs network to exercise.

- [x] **TASK-011**: Expose Model Provider Selection in CLI and Config
  - **Objective**: `lpf generate` can choose the writer: `--model mock|openai-compatible|ollama` plus env/`lpf.toml` for endpoint and key, defaulting to `mock` (offline). README documents the matrix and that offline is the default safe path.
  - **Acceptance Criteria**:
    - CLI flag and env/config parse; `--model mock` produces the current byte-identical output.
    - README documents providers, env vars, and the offline default.
    - CLI tests run offline with the mock provider; full pytest suite and ruff linters pass.
  - **Implementation notes**: `generate` drops the stale `--mock/--no-mock` guard (providers are implemented since TASK-007) for a `--model mock|openai-compatible|ollama` option. Resolution precedence: flag > `LPF_PROVIDER`/`lpf.toml [model].kind` > default `mock`. Non-mock kinds build the writer through `create_live_model` with `LPF_MODEL_NAME`/`LPF_MODEL_ENDPOINT`/`LPF_API_KEY`/`LPF_TIMEOUT`; an unknown kind (e.g. `LPF_PROVIDER=claude`) exits 1 with a readable `UNKNOWN_MODEL_KIND` message. `config.py` also reads an optional `lpf.toml` (`[model]` name/endpoint/api_key/kind, `[run]` log_level/output_dir/timeout) with env always winning; a missing or malformed file is a no-op. `--model mock` is byte-identical to the default run (test compares the full output trees). README gained the provider matrix and the offline-safe default. New `tests/test_config.py` (toml/env precedence, malformed/missing files, unknown keys) and `tests/test_cli.py` (flag advertised, flag-beats-env, config-provider fallback, env→endpoint/key wiring, readable unknown-kind failure, live model passed to the pipeline, byte-identical trees). Six-point mutation harness, 6/6 killed. Suite: 877 passed, ruff clean.

---

## v0.8.1 Milestone Tasks — Whole-Codebase Audit Fixes (Phase A: P0 correctness)

> A whole-codebase audit (`docs/audits/codebase-gaps-and-bugs.md`) found five
> verified P0 bugs and a long tail of P1/P2/P3 gaps. Phase A fixes the P0s; later
> phases (TASK-013 onward) take the determinism, CLI-hygiene, contract, and
> dead-code workstreams from the same plan.

- [x] **TASK-012**: Fix the Five Verified P0 Bugs
  - **Objective**: Close the audit's Phase A: (1) `openai-compatible` provider kind was unreachable via `--model`/`LPF_PROVIDER` (TASK-011 regression: class `kind="openai_compatible"` vs the hyphen the CLI/config/docs use); (2) `factual_consistency` was routed to a content rebuild whose inputs are research-owned → guaranteed 3 wasted revisions + FAIL; (3) the run-level `except LpfError` handler called `state.fail()` post-COMPLETE → `WorkflowError` crash instead of a failed result; (4) bare `ValueError`s escaped the run loop as tracebacks; (5) `schema_validity` was a decorative always-passed gate.
  - **Acceptance Criteria**:
    - `--model openai-compatible` / `LPF_PROVIDER=openai-compatible` resolves the real adapter via the real factory (not a monkeypatched one).
    - A zero-supported-claims `factual_consistency` failure aborts the run at revision 0 instead of burning the budget.
    - A packaging `LpfError` raised after COMPLETE yields a result (no `WorkflowError` escapes), with `package=None` and the failure recorded.
    - Structured-reply mismatches surface as typed `ProviderError`/`WorkflowError` failed runs, never raw tracebacks.
    - No `schema_validity` gate in a real run's verification.
    - Full pytest suite and ruff linters pass; 5-point mutation harness killed 5/5.
  - **Implementation notes**: `OpenAICompatibleModel.kind` becomes the canonical `"openai-compatible"` and `create_live_model` normalizes `_ → -` (case/whitespace-insensitive), so the documented spelling and the class never drift again; tests drive the real factory with the exact `--model`/env values. `factual_consistency` moves to `NON_REPAIRABLE_GATES` (ADR-010 updated) — the routing unit tests and the E2E ungrounded-evidence test now assert `revisions == 0`. The `except LpfError` handler guards `state.fail` with `is_terminal` (packaging runs post-COMPLETE; a terminal run records `failure_reason` instead of re-entering the machine). Content-stage schema mismatches raise `ProviderError(STRUCTURED_REPLY_REQUIRED)` and the deterministic mock raises `WorkflowError(UNSUPPORTED_SCHEMA)` for unknown schemas instead of `ValueError`. The always-passed `schema_validity` gate and its `NON_REPAIRABLE_GATES` entry are removed (pydantic enforces schemas at construction). New regression tests: real-factory kind resolution (incl. underscore alias, case-insensitivity), unowned `factual_consistency` routing, post-completion packaging failure, text-for-structured-call failed run, and no-decorative-gate assertion. Suite: 890 passed, ruff clean. Mutation harness `%TEMP%\opencode\mutate_p0_fixes.py`, 5/5 killed.

---

## v0.8.1 Milestone Tasks — Whole-Codebase Audit Fixes (Phase B: reproducibility)

> Phase B closes the audit's determinism workstream: items 2.1 (live `source_id`
> was a uuid, so two runs given identical provider responses still produced
> different report/evidence-map hashes) and 2.2 (gate-name sets were duplicated
> string literals with no cross-check against what `qa_stage` actually emits).

- [x] **TASK-013**: Make Live Runs Deterministic Given Identical Responses + Gate-Name Single Source of Truth
  - **Objective**: (1) `SearchResult.source_id` from the four live providers (and the stage boundary) must be a pure function of `(provider, url)` so identical provider responses yield identical research artifacts — file the uuid-only use under genuinely unique instances; (2) stop duplicating gate-name literals between `qa_stage` (which emits them) and `revision` (which owns them): one catalog, and a test proving every emitted gate name is in exactly one ownership set.
  - **Acceptance Criteria**:
    - Live providers derive deterministic source ids from `(provider, url)`; no hidden `uuid4` in the shipped adapters.
    - Two staged research runs with identical canned live responses produce identical report/evidence-map content hashes (stage-level byte-identical regression test).
    - `src/lpf/orchestration/gates.py` is the single source of truth; `revision` owns gates through it and `qa_stage` emits through it.
    - Cross-check tests: catalog == union of the ownership sets; each catalog gate in exactly one set; a default run emits every unconditional catalog gate; a `required_gates` run emits the whole catalog.
    - Full pytest suite and ruff linters pass; 5-point mutation harness killed 5/5.
  - **Implementation notes**: new `lpf.domain.identity.seeded_id(*parts)` — `sha256("|".join(parts))` truncated to 32 hex — used by all four adapters (`arxiv`, `wikimedia`, `tavily`, `searxng`); the mock keeps `ctx.id` and dedupe still keys on URL, so offline bytes are unchanged. `_normalise_report` continues to normalise stage-boundary ids/timestamps; with seeded ids the whole research output is reproducible given identical responses (ADR-009 limitations bullet updated). New `src/lpf/orchestration/gates.py` catalog; `revision.py` and `qa_stage.py` import the constants. Tests: `TestSeededId` (+3), provider-level determinism across all four adapters, staged-live E2E determinism in `test_e2e_pipeline.py`, and `TestRoutingTable`/`TestGateCatalogSurface` cross-checks in `test_revision_loop.py`. Suite: 902 passed, ruff clean. Mutation harness `%TEMP%\opencode\mutate_phase_b.py`, 5/5 killed.
