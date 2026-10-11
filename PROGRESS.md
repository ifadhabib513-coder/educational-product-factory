# Ralph Loop Execution Progress

This document tracks autonomous engineering iterations performed by the Ralph Loop on `AI Educational Product Factory`.

| Iteration | Timestamp | Task ID | Description | Status | Commit |
|-----------|-----------|---------|-------------|--------|--------|
| - | 2026-10-04 | Setup | Initialized Ralph loop harness (`PROMPT.md`, `tasks.md`, `scripts/ralph.ps1`, `scripts/ralph.sh`) | Ready | Initial |
| 1 | 2026-10-04 | TASK-001 | Exact-Title Definitional Signal in Research Scoring | Completed | `f0c0a66` |
| 2 | 2026-10-04 | TASK-002 | Eliminate Spurious False-Positive Conflicts in Mock Sentences | Completed | `ceca889` |
| 3 | 2026-10-05 | TASK-003 | Factual Quality Gate Validator | Completed | `f82be33`, `cf27812`, `0f65e47` |
| 4 | 2026-10-07 | TASK-004 | Numerical Consistency Gate for Worked Examples | Completed | `be905b3` |
| 5 | 2026-10-08 | TASK-005 | Multi-Format Packaging (HTML and ZIP Bundle) | Completed | `2b7a061` |
| 6 | 2026-10-08 | TASK-006 | Bounded Cyclic Stage Machine Revision Loop | Completed | `b116f0c` |
| 7 | 2026-10-11 | TASK-007 | Live Model Provider Adapters (OpenAI-compatible + Ollama) with structured-output validation | Completed | `e9b8f7f` |
| 8 | 2026-10-11 | TASK-008 | Provider Resilience (bounded retry, timeout, deterministic backoff) | Completed | `07bbadc` |
| 9 | 2026-10-11 | TASK-009 | Revision Loop Repairs a Model-Written Worked-Example Defect (model-written worked examples, QA feedback threaded into rebuilds) | Completed | `56aac58` |
| 10 | 2026-10-11 | TASK-010 | Route Retrieval by Query Intent (per-question provider pruning keyed on intent) | Completed | `34e38d1` |
| 11 | 2026-10-11 | TASK-011 | Expose Model Provider Selection in CLI and Config (`--model`, env, `lpf.toml`) | Completed | `419c3c4` |
| 12 | 2026-10-11 | TASK-012 | Fix the Five Verified P0 Bugs from the Whole-Codebase Audit (provider kind mismatch, research-owned gate routing, terminal-state crash, ValueError escapes, decorative schema gate) | Completed | `(pending)` |

> **v0.8.0 milestone complete** — the last task (TASK-011) shipped the CLI/config
> seam: `lpf generate --model openai-compatible|ollama` selects the writer
> built in TASK-007, hardened in TASK-008, proven in TASK-009, and grounded by
> intent-aware retrieval in TASK-010. Offline `mock` remains the default safe
> path.

---
## Detailed Iteration Logs

### Iteration 1 — 2026-10-04: TASK-001
- **Task**: Implement Exact-Title Definitional Signal in Research Scoring (`src/lpf/research/scoring.py`).
- **Rationale**: Resolves the live failure where narrow subtopics (`Basic Linear Algebra Subprograms`) could beat canonical definitional topics (`Linear algebra`).
- **Changes**:
  - Implemented `clean_title_for_matching`, `extract_query_topic`, and `has_exact_title` in `src/lpf/research/scoring.py`.
  - Re-weighted `intent_match` for `DEFINITIONAL` and `EXPLANATORY` intents: coverage (0.50), definition cue (0.30), exact title match (0.20).
  - Exported `has_exact_title` in `__all__`.
  - Added unit test suite `TestExactTitleMatch` and regression test `test_exact_title_separates_canonical_from_narrow_subtopic` in `tests/test_research_intent_scoring.py`.
- **Verification**:
  - `python -m pytest tests/`: 698 passed (17 new tests, 0 failures, 0 regressions).
  - `python -m ruff check src/ tests/`: All checks passed.
  - `python -m ruff format --check src/ tests/`: 125 files already formatted.

### Iteration 2 — 2026-10-04: TASK-002
- **Task**: Eliminate spurious false-positive conflicts in research mock sentences.
- **Rationale**: v0.6.0 version history recorded 8 false-positive conflicts on every offline run because the deterministic mock snippets shared bucket words.
- **Changes**:
  - Neutralised the `DeterministicSearchProvider` snippet in `src/lpf/orchestration/research_stage.py` to a single source-neutral string.
  - Offline conflict count dropped 8 → 0; genuine conflict-detection tests untouched.
- **Verification**:
  - `python -m pytest tests/`: all passing, conflict assertions re-run green.
  - Added regression coverage in `tests/test_e2e_pipeline.py::TestMockResearchNoise` (offline `conflicts == []`, `evidence_map.conflicting_claims == 0`) during iteration 3.
  - Commit `ceca889`.

### Iteration 3 — 2026-10-05 → 2026-10-07: TASK-003
- **Task**: Implement the factual quality gate validator (`src/lpf/validators/`).
- **Rationale**: QA previously had no way to fail a run whose claims were unsupported by the retrieved evidence.
- **Changes**:
  - Added `src/lpf/validators/` with `check_factual_claims_reference_valid_evidence` and `check_factual_consistency` (`INVALID_EVIDENCE_REFERENCES`, `CONTRADICTORY_EVIDENCE`, `UNGROUNDED_CLAIMS`).
  - Wired a `factual_consistency` gate into `build_qa` (`src/lpf/orchestration/qa_stage.py`).
  - Replaced the dead self-referential catalogue logic with a real one: `build_qa(..., verified_source_ids=...)` receives `{source.source_id for source in research.report.verified_sources}` from the pipeline, so a claim citing a source this run never verified now fails QA.
  - Corrected the gate `location` to `evidence_map` and rewrote `suggested_fix` to cover both citations and grounding.
  - Tests: `tests/test_validators_factual.py` (16 tests, including pipeline spy and phantom-source failure) plus `TestMockResearchNoise`.
- **Verification**:
  - `python -m pytest tests/`: 717 passed.
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 144 files already formatted.
  - Mutation-tested: removing the pipeline wiring makes both catalogue tests fail; renaming the gate fails 3 tests.
  - Live `--live-research` run (arXiv + Wikimedia) succeeds with the gate green.
  - Commits `f82be33`, `cf27812`, `0f65e47`.

### Iteration 4 — 2026-10-07: TASK-004
- **Task**: Implement numerical/symbolic consistency validation for worked examples.
- **Changes**:
  - Added `src/lpf/validators/numerics.py` with `check_worked_example_arithmetic`:
    - Exact `fractions.Fraction` evaluation over a whitelisted AST (no `eval`, no network, no new dependency), so `0.1 + 0.2` equals `0.3` exactly.
    - Reports `step_mismatch` (a false equation such as `2 + 3 = 6`), `step_contradiction` (a variable silently redefined), `answer_mismatch` (`final_answer` disagreeing with the steps) and `undefined_arithmetic` (division by zero).
    - Pseudocode and prose (`result = apply(method, problem)`) are skipped rather than guessed at, so the default content stage output is never falsely flagged.
  - Wired a `numerical_consistency` gate into `build_qa` and passed `content.worked_examples` from the pipeline.
  - Tests: `tests/test_validators_numerics.py` (31 tests — evaluator exactness/whitelist, passing chains, four defect classes, gate wiring, pipeline spy, run-fails-before-packaging).
- **Verification**:
  - `python -m pytest tests/`: 748 passed (31 new, 0 regressions).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 146 files already formatted.
  - Mutation-tested (5/5 caught): gate short-circuited, step comparison flipped, final-answer check dropped, pipeline stops passing examples, binary floats replace exact decimals.
  - Commit `be905b3`.

### Iteration 5 — 2026-10-08: TASK-005
- **Task**: Multi-format packaging — standalone HTML and an archival ZIP bundle alongside `product.md`.
- **Changes**:
  - Created the `lpf.packaging` package the backlog names:
    - `lpf/packaging/html.py` — `markdown_to_html` / `render_html_document`. Covers exactly the Markdown the factory emits (headings, paragraphs, bullet/ordered lists, pipe tables, `**bold**`, `*italic*`, `` `code` ``). Text is HTML-escaped *before* emphasis is applied and code spans are parked in placeholders, so `<script>` in a lesson ships as visible text and `a ** b` inside backticks is never reinterpreted. Output is a self-contained document with embedded CSS and no external assets.
    - `lpf/packaging/bundle.py` — `build_run_bundle` writes `<run_id>.zip` with sorted members, a fixed DOS epoch timestamp (1980-01-01), pinned `create_system` and fixed Unix mode, so the archive is byte-identical across runs *and* platforms.
  - `packaging_stage.package_run` now also writes `product.html` and `<run_id>.zip` (containing `manifest.json`, `product.md`, `product.html`, `run_log.json` and every `artifacts/*.json`); `PackageResult` gained `product_html_path` and `bundle_path`.
  - The bundle is built from an explicit member list, so it never packages itself even though it lives inside the run directory.
  - CLI reports `html` and `bundle` alongside `product` in its JSON summary.
- **Verification**:
  - `python -m pytest tests/`: 781 passed (33 new, 0 regressions) — including the existing whole-tree byte-identical determinism test, which now covers the HTML file and the ZIP.
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 150 files already formatted.
  - Mutation-tested (6/6 caught): escaping removed, pipe tables disabled, member sorting dropped, non-epoch timestamp, `product.html` dropped from the bundle, HTML rendered from an empty document.
  - Commit `2b7a061`.

### Iteration 6 — 2026-10-08: TASK-006
- **Task**: Cyclic stage machine revision loop — QA may rewind to `content` or `assessment`, bounded.
- **Changes**:
  - `src/lpf/orchestration/state.py`:
    - `REVISION_TARGETS` declares the machine's only backward edges: `qa → content` and `qa → assessment`. Every other stage still has one successor plus `failed`.
    - `MAX_REVISIONS = 3` and `RunState.revisions`; `begin_revision()` claims from the budget and raises `WorkflowError(code="REVISION_BUDGET_EXHAUSTED")` when it is spent, while `revisions_exhausted` lets the pipeline fail with a message naming the gates that never cleared.
  - New `src/lpf/orchestration/revision.py`: `route_failed_gates` maps failed gates to a stage through an explicit ownership table (`OWNED_GATES`). Ownership is partial — `research_evidence`, `curriculum_coverage`, `objective_references`, `schema_validity`, `required_gates_present` and any unclaimed gate name are unowned, so one of them in the failure set ends the run instead of burning budget on a rebuild that cannot help. A mixed content + assessment failure revisits content, because content rebuilds forward into assessment anyway.
  - `src/lpf/orchestration/pipeline.py`: content → assessment → QA is now a `while True` loop with the routing decision at the bottom. `_discard(artifacts, <last pass's artifacts>)` runs before each rebuild and matches by object identity, so a revised product ships one live set of lessons rather than the rejected pass alongside its replacement.
  - `build_qa(..., iteration=...)` now records which pass of the cycle produced the result; `max_iterations` is derived from `MAX_REVISIONS + 1` so both fields describe the same cycle.
  - New `EventType.REVISION_STARTED` records why a stage is running twice; clean runs never emit it, so their event log is unchanged.
  - Tests: `tests/test_revision_loop.py` (17 tests — repair converges, superseded artifacts dropped, assessment-only routing, budget exhaustion, unowned-gate abort, routing table, byte-identical repetition of both a repaired and an exhausted run) plus `TestRunState.test_revision_budget_is_bounded` and two rewritten transition-table tests in `tests/test_orchestration_context.py`.
- **Verification**:
  - `python -m pytest tests/`: 801 passed (20 new, 0 regressions) — including the existing whole-tree byte-identical determinism test. Baseline at `392b8bb` re-measured in a clean worktree: 781 passed.
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 153 files already formatted.
  - Mutation-tested (14/14 caught): both revision edges removed, unowned gates no longer aborting, unknown gate falling back to content, content/assessment routing swapped, each of the three `_discard` calls neutralised, budget exhausted from the first failure, revision counter not incrementing, iteration pinned to 1, and content not rebuilt on a content failure.
  - One mutation survived the first pass — removing the `NON_REPAIRABLE_GATES` early exit changed no behaviour, because the unknown-gate rule already covered it. The redundant branch was deleted in favour of a single ownership rule rather than written around with a test.
  - Docs: `docs/adr/010-bounded-qa-revision-loop.md` added; ADR-008 marked superseded in part; ROADMAP Stage 3 "Retry and repair" moved from PENDING to COMPLETE; `tasks.md` TASK-006 checked and the v0.7.0 milestone marked complete.
  - Commit `b116f0c`.

### Iteration 7 — 2026-10-11: TASK-007
- **Task**: Live model provider adapters — implement the existing `ModelProvider` protocol for OpenAI-compatible and Ollama HTTP endpoints, with structured-output validation so a malformed reply fails the run instead of shipping garbage.
- **Rationale**: v0.8.0 milestone, first task — the "write real prose" work needs a real model seam before the writer itself gets real (TASK-009).
- **Changes**:
  - New `src/lpf/models/providers/` package:
    - `base.py` (`HttpChatModel`) — all PyPI-visible behaviour: request build (`model`, `messages`, `temperature`, optional `max_tokens`, `headers`), `ProviderError` on transport failure / HTTP error status / non-JSON body / malformed vendor envelope, and `_validate_structured`: `json.loads` + `isinstance(dict)` + `schema.model_validate`, mapping failures to `ValidationError(code="MODEL_OUTPUT_NOT_JSON")` / `ValidationError(code="MODEL_OUTPUT_INVALID_SCHEMA")`. Client is injectable for offline tests; default client is a real `httpx.AsyncClient` with a 60s timeout.
    - `openai_compatible.py` (`OpenAICompatibleModel`) — `/chat/completions`, `Authorization: Bearer` when an API key is set, `response_format: {"type": "json_object"}` for structured calls, content from `choices[0].message.content`.
    - `ollama.py` (`OllamaModel`) — native `/api/chat`, no auth, `format: "json"` for structured calls, content from `message.content`.
    - `__init__.py` — `create_live_model(kind, *, model, base_url, api_key, client)` factory keyed on `OpenAICompatibleModel.kind` / `OllamaModel.kind`; unknown kind raises `ConfigError(code="UNKNOWN_MODEL_KIND")`. Exported from `lpf.models` (`__all__`).
  - Content and pipeline stages are untouched: the adapter is injected through the existing `FactoryPipeline(model=...)` seam, which is the requirement's point — no stage code changes.
- **Verification**:
  - `python -m pytest tests/`: 827 passed (26 new, 0 regressions).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 158 files already formatted.
  - Mutation-tested (13/13 caught): JSON decode guard, non-object guard, error-code swap, pydantic error swallowed, JSON request field skipped, HTTP status guard dropped, transport catch changed to leak, both `parse_content` naive indexings, both default model names, auth header dropped, factory silently falling back on unknown kind.
  - Protocol conformance: both adapters satisfy `ModelProvider` (`isinstance` + `protocol_satisfied`).
  - Pipeline wiring: `OpenAICompatibleModel` over `httpx.MockTransport` runs the full offline pipeline and produces a byte-identical tree across two runs; a `ValidationError` from the adapter aborts the run at content before QA (test `TestMalformedOutputFailsRun`).
  - `tests/` never touches the network — every live-ish test runs against `httpx.MockTransport`.

### Iteration 8 — 2026-10-11: TASK-008
- **Task**: Provider resilience — bounded retry, timeout, and deterministic backoff for live model calls, surfacing a stable `ProviderError` when a provider stays down.
- **Rationale**: Hosts fail; a content run must neither crash nor hang. TASK-007 shipped the HTTP seam but with a single-shot call.
- **Changes**:
  - `base.py` (`HttpChatModel`) gains `retry: RetryPolicy | None = None` (defaults to `DEFAULT_RETRY` from `research/transport.py`) and `timeout_seconds: float = 60.0` (baked into the injectable/real `AsyncClient`).
  - New `_post()` is one bounded loop over `range(1, max_attempts + 1)`: retries transport `httpx.HTTPError` and statuses in `retry_on_status` (429, 5xx); any other 4xx returns immediately so the caller raises `PROVIDER_HTTP_ERROR` (never replayed). Backoff is `retry.delay_for(attempt)` — deterministic, no jitter. Exhaustion raises `PROVIDER_REQUEST_FAILED` with `"{max_attempts} attempt(s); last failure: ..."`.
  - `OpenAICompatibleModel`, `OllamaModel`, and `create_live_model` forward `retry`/`timeout_seconds`.
- **Verification**:
  - `python -m pytest tests/`: 834 passed (7 new, 0 regressions).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 158 files already formatted.
  - Mutation-tested (8/8 caught): retry loop pinned to one attempt, loop unbounded up to 10, retryable-status branch disabled, transport-retry replaced with a re-raise, lost `last_failure` recording, message dropping the attempt count, backoff sleep disabled, HTTP-error guard dropped.
  - New tests: flaky status/transport recovery (recovered after 3 tries), bounded call count on constant failure, non-retryable 401 never replayed, deterministic exhaustion message with `last_failure`, recorded backoff delays `[0.25, 0.5]` (backoff_multiplier 2.0), and an end-to-end constant-failure run whose `failure_reason` carries `PROVIDER_REQUEST_FAILED` and `3 attempt(s)`.

### Iteration 9 — 2026-10-11: TASK-009
- **Task**: Prove the revision loop repairs a **model-written** defect — a fake live model writes a wrong worked-example answer on its first draft, is retried on the `qa → content` re-run, and the run completes.
- **Rationale**: TASK-006 proved the cycle with a monkeypatched defect. The real writer seam (TASK-007) meant the "defect" should come from the model the pipeline actually calls, and repair should be driven by actually telling the writer what QA found.
- **Changes**:
  - New `WorkedExampleDraft` writer schema in `src/lpf/domain/worked_example.py` — the authored content only (no artifact identity), which the Content stage stamps with `id`/`created_at`/`parent_id`/`source_refs`.
  - `content_stage.py`: APPLY-unit worked examples are now produced by `_write_worked_example()` (a structured `model.generate(schema=WorkedExampleDraft)`), so bad arithmetic is the writer's defect. `build_content` gains `feedback`; the prompt carries "The previous draft failed QA: …" on a rebuild, so a second draft is a repair, not a repeat.
  - `pipeline.py`: on a `qa → content` rewind, `_revision_feedback(verification)` collapses the failed gates' problems into a deterministic repair instruction passed into the rebuild.
  - `orchestration/model.py`: `DeterministicMockModel` answers `WorkedExampleDraft` with exactly the old canonical template, so the offline package stays byte-identical; any other schema is still refused loudly.
- **Verification**:
  - `python -m pytest tests/`: 839 passed (5 new, 0 regressions).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 159 files already formatted.
  - Mutation-tested (4/4 caught): pipeline drops the feedback, content stage ignores the feedback, content writes a canned template instead of the draft's fields, mock returns an empty step list.
  - `tests/test_model_revision_loop.py`: first draft `3 + 4 = 8` fails `numerical_consistency`; rebuild (prompt carries the failure) writes `3 + 4 = 7`; run completes with `VerificationResult.iteration == 2`, `revisions == 1`, `(QA, CONTENT)` hop, only the repaired verification shipped with the gate passed; repaired and exhausted runs are byte-identical across two runs; constant-defect run fails on "revision budget" after `MAX_REVISIONS`.

### Iteration 10 — 2026-10-11: TASK-010
- **Task**: Route retrieval by query intent — prune the per-question provider set so a beginner's definitional query is never sent to arXiv, where preprints the scorer rejects by design arrive as pure noise.
- **Rationale**: "Retrieval is unrefined: questions are sent to every provider regardless of intent" (`version_history.md`). The intent-conditional *scorer* (TASK-001) knew preprints fit a definition poorly, but they were still retrieved and then buried — a retrieval-side fix is cleaner and cheaper.
- **Changes**:
  - New `src/lpf/research/routing.py`: `provider_suitability(intent)` (the intent→provider table) and `prune_providers(intent, providers)` (never-empty, order-preserving, deduping prune). `ARXIV` is excluded for DEFINITIONAL/EXPLANATORY/PROCEDURAL; `WIKIMEDIA` is excluded for ACADEMIC_LITERATURE/EVIDENCE_SYNTHESIS/CURRENT; `GENERAL` keeps every provider. `MOCK`/`OFFICIAL` sit in every set (offline determinism can never be pruned away) and an empty suitable-intersection falls back to the caller's full set (a lone injected provider still retrieves).
  - `ResearchRouter.plan` rebuilds each question's strategy: pruned providers + regenerated `SearchQuery`s (preserving per-provider `max_results`). The plan builder in `orchestration/research_stage.py` prunes identically, so the plan artifact and execution agree on which providers ran.
- **Verification**:
  - `python -m pytest tests/`: 862 passed (23 new, 0 regressions).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 161 files already formatted.
  - Mutation-tested (6/6 caught): router keeps all providers, plan builder skips pruning, DEFINITIONAL retains ARXIV, suitability falls back to GENERAL, empty prune not fallen back, router classifies every question as GENERAL.
  - New `tests/test_research_intent_routing.py` (suitability table, router pruning independent of the plan builder, execution never calls a pruned provider, query budgets survive rebuilds) plus reworked `tests/test_research_provider_injection.py`: a definitional "What is linear algebra?" over injected {ARXIV, WIKIMEDIA} retrieves only encyclopedic sources and never calls the arXiv provider, while "find papers about …" still queries arXiv end-to-end. Offline mock runs unchanged (`prune_providers(MOCK) == (MOCK,)` for every intent).
  - Live path is the same code — the stage injects live providers and the router prunes them — but needs network to exercise, so it is verified only by the offline suite here.

### Iteration 11 — 2026-10-11: TASK-011
- **Task**: Expose model provider selection in the CLI and config — `lpf generate` can choose the writer via `--model mock|openai-compatible|ollama`, plus env/`lpf.toml` for endpoint and key, defaulting to `mock` (offline).
- **Rationale**: TASK-007..TASK-010 built the live model seam, resilience, a repair proof, and intent-aware retrieval, but `lpf generate` still hard-refused anything but mock ("only mock is implemented" — stale since TASK-007). The last v0.8.0 task was wiring the seam in.
- **Changes**:
  - `cli.py`: replaced the obsolete `--mock/--no-mock` guard with `--model <mock|openai-compatible|ollama>`. Resolution: flag > `LPF_PROVIDER` / `lpf.toml [model].kind` > default `mock`. Non-mock kinds go through `create_live_model(model=..., base_url=..., api_key=..., timeout_seconds=...)` from config; unknown kinds exit 1 with a readable `UNKNOWN_MODEL_KIND` message; `mock` leaves `model=None` so the pipeline default (deterministic offline) produces the unchanged output. CLI prints a `Writer model:` line.
  - `config.py`: new `model_name`/`model_endpoint`/`api_key` fields plus `LPF_MODEL_NAME`/`LPF_MODEL_ENDPOINT`/`LPF_API_KEY` env vars, and an optional `lpf.toml` (`[model]` kind/name/endpoint/api_key, `[run]` log_level/output_dir/timeout) read with `tomllib`. Env always wins over the file; a missing or malformed file is a no-op; unknown keys are ignored.
  - README: provider matrix table + offline-default admonition + `lpf.toml` example.
- **Verification**:
  - `python -m pytest tests/`: 877 passed (15 new, 0 regressions) — `tests/test_config.py` (toml/env precedence, malformed/missing files, unknown keys) and `tests/test_cli.py` (flag advertised, flag-beats-env, config-provider fallback, env→endpoint/key wiring into `create_live_model`, readable unknown-kind failure, live model passed to `FactoryPipeline`, and `--model mock` byte-identical to the default run tree).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 161 files already formatted.
  - Mutation-tested (6/6 caught): CLI flag ignored, mock entering the live branch, live-provider config (endpoint/key/name) dropped, live model not passed to the pipeline, toml overriding env, config dropping the model fields.

### Iteration 12 — 2026-10-11: TASK-012
- **Task**: Fix the five verified P0 bugs from the whole-codebase audit (`docs/audits/codebase-gaps-and-bugs.md`, Phase A).
- **Rationale**: The audit (coverage run + four exploration sweeps + direct read-verification of every finding) surfaced correctness bugs that produce wrong output or break a documented live path — including one introduced by TASK-011.
- **Changes**:
  - **1.1 provider-kind mismatch (TASK-011 regression)**: `OpenAICompatibleModel.kind` is now the canonical `"openai-compatible"` (matching `--model`, `LPF_PROVIDER`, `lpf.toml`, README) and `create_live_model` normalizes `_ → -` with case/whitespace folding, so `--model openai-compatible` resolves the real adapter instead of `UNKNOWN_MODEL_KIND`. Tests now drive the **real** factory with the exact CLI/env values (hyphen, underscore alias, `OLLAMA`/` oLLaMa`).
  - **1.2 research-owned gate routing**: `factual_consistency` moves to `NON_REPAIRABLE_GATES` — its inputs (`evidence_map.claims`, `verified_source_ids`) are research artifacts the revision cycle never revisits, so a zero-supported-claims failure used to burn all 3 revisions and then fail. The run now aborts at revision 0 (`test_ungrounded_evidence...` asserts `revisions == 0`). ADR-010 section 2 updated.
  - **1.3 terminal-state crash**: the `except LpfError` handler guarded `state.fail` with `is_terminal`. Packaging runs after COMPLETE, so a post-completion `LpfError` previously triggered `advance(FAILED)` → `WorkflowError` crash; it now records `failure_reason`, keeps the terminal state, and returns `package=None`. Regression: forced `package_run` `RenderingError` → no crash, failure recorded, last event still `run_completed`.
  - **1.4 ValueError escapes**: content-stage structured-reply mismatch now raises `ProviderError(STRUCTURED_REPLY_REQUIRED)` and the deterministic mock's unknown-schema guard raises `WorkflowError(UNSUPPORTED_SCHEMA)`, both `LpfError`s, so the run loop returns a FAILED run instead of a traceback.
  - **1.5 decorative gate**: the always-passed `schema_validity` gate (qa_stage.py) and its `NON_REPAIRABLE_GATES` entry are gone; schema conformance is enforced by pydantic at construction. Tests assert no `schema_validity` in a run's gate list, and the packaging HTML fixture/assertion no longer cites it.
- **Verification**:
  - `python -m pytest tests/`: 889 passed (11 new, 0 regressions).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: all 161 files formatted.
  - Mutation-tested (5/5 killed, `%TEMP%\opencode\mutate_p0_fixes.py`): kind back to underscore, `factual_consistency` back to CONTENT_GATES, `state.fail` unconditional, bare `ValueError` in content stage, decorative gate re-added.
