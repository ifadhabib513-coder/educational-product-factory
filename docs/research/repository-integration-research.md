# Repository Integration Research — Candidate Portfolio Evaluation

> **Status**: research complete, no production change made. This document is the
> deliverable of the repository integration research mission and is the record for
> the TASK-018 draft in Appendix A. Nothing here has been implemented, installed,
> or wired into the factory.
>
> **Date**: 2026-10-12
> **Target system**: AI Educational Product Factory (`lpf`) — this repository.
> **Method**: 13 candidate repositories were shallow-cloned (`git clone --depth 1`)
> to a temp sandbox and inspected at the source level (license file, dependency
> manifest, README, and core modules) — not assessed from READMEs alone. The
> project's own source, manifests, and tests were read first. No candidate was
> installed into the project, no dependency was added, and no production behaviour
> was modified.

---

## 1. Current implementation summary

Verified from the working tree on 2026-10-12 (`HEAD = 7581ed0`, clean).

**Stack.** Python ≥3.11, `hatchling` build, package `lpf` v0.1.0.
Runtime deps: `click>=8.1`, `pydantic>=2.7,<3`, `httpx>=0.27`,
`pydantic-settings>=2.0`, `sqlalchemy[asyncio]>=2.0`, `aiosqlite>=0.20`.
Dev deps: `pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`.
Tests: **881 passing, total coverage 97.81%, enforced floor `--cov-fail-under=97`**
(`[tool.pytest.ini_options] addopts` in `pyproject.toml`).

**Pipeline.** Deterministic, offline by default, no LLM runtime dependency:
`discovery → specification → research → syllabus → curriculum → content → assessment
→ QA → packaging`, with a bounded revision loop (`MAX_REVISIONS`) and on-disk run
events. The stage machine permits a `qa → content` rewind on repairable gates
(ADR-006); `factual_consistency` and other research-owned gates are non-repairable
(ADR-010).

**Contracts.** Pydantic v2 models in `src/lpf/domain/` (product, curriculum, lesson,
objectives, practice, assessment, misconception, worked_example, learner, quality)
and `src/lpf/schemas/` (discovery, research). Identity is a SHA-256 content hash over
canonical JSON (`domain/identity.py:33 compute_content_hash` / `with_content_hash`);
`seeded_id(*parts)` gives deterministic 32-hex ids for content-addressed objects.

**Validation surface (the thing most relevant to this research).**

- `src/lpf/domain/validation.py` — pure reference/coverage checks:
  `check_objective_references`, `check_misconception_objective_refs`,
  `check_question_references`, `check_assessment_references`,
  `check_answer_references`, `check_answer_key_references`,
  `check_quality_gate_references`, `check_prerequisite_chain` (DFS cycle detection).
  These prove **IDs resolve and the prerequisite graph is acyclic** — they do *not*
  check semantic content.
- `src/lpf/validators/factual.py` — `check_factual_claims_reference_valid_evidence`
  and `check_factual_consistency`. Fails on invalid evidence references
  (`INVALID_EVIDENCE_REFERENCES`), purely contradictory evidence
  (`CONTRADICTORY_EVIDENCE`), or entirely unsupported claims (`UNGROUNDED_CLAIMS`).
- `src/lpf/validators/numerics.py` — `check_worked_example_arithmetic`. Re-derives
  numeric claims with **exact `Fraction` arithmetic** over an **AST whitelist** of
  arithmetic nodes, **no `eval`**, and applies "skip, never guess": anything not a
  pure arithmetic expression is reported *not checkable*, never executed. Detects
  `step_mismatch`, `step_contradiction`, `answer_mismatch`, `undefined_arithmetic`
  (`NUMERIC_INCONSISTENCY`).

**QA gates.** `src/lpf/orchestration/gates.py` is the single source of truth for gate
names (12 constants in `ALL_GATES`): `curriculum_coverage`, `objective_references`,
`misconception_references`, `question_references`, `assessment_references`,
`answer_references`, `answer_key_references`, `research_evidence`,
`factual_consistency`, `numerical_consistency`, `required_gates_present`,
`minimum_score`. `orchestration/qa_stage.py` builds each gate by delegating to a
validator or an explicit coverage assertion; `orchestration/revision.py` owns the
repairable/non-repairable routing.

**Research.** Provider seam with a deterministic `Mock` default plus live
`arXiv`/`Wikimedia`/`Tavily`/`SearXNG` adapters behind `--live-research`;
`research/authority.py` classifies source authority by deterministic domain tiers
(primary/institutional/academic/educational/textbook/secondary/general/unknown);
`research/routing.py` prunes providers by query intent; `schemas/research.py` defines
`EvidenceMap`/`EvidenceClaim`/`SourceAuthority`.

**Persistence.** `src/lpf/db/` (sqlalchemy async + aiosqlite) exists but is
**unwired** — a known follow-up, not part of this research.

---

## 2. Candidate comparison matrix

Legend — Class: what the artifact actually *is*. Relevance: to an educational
product-generation factory whose strength is deterministic, offline, evidence-backed
quality gates.

| Repository | Lang / runtime | License | What it actually is (source evidence) | Class | Relevance | Disposition |
|---|---|---|---|---|---|---|
| `https://github.com/QWED-AI/qwed-verification` | Python ≥3.10 | Apache-2.0 | Fail-closed deterministic verification layer. `DiagnosticResult{status, admission}` where `status ∈ {VERIFIED, UNVERIFIABLE, BLOCKED}` and `admission ∈ {ADMIT, BLOCKED}`; `VERIFIED` carries a `proof_ref` (SHA-256 commitment). Engines: SymPy, Z3, SQLGlot, Python AST. Also ships a FastAPI server, Docker image, and TS/Go/Rust SDKs. Version 7.2.2. | library **and** framework | **High** (concept) | **Borrow**, do not adopt the package |
| `https://github.com/LesterALeong/llm-evalgate` | Python ≥3.9 | *no LICENSE file* (pyproject declares MIT) | CI eval gates + calibrated LLM-as-judge + bootstrap confidence intervals + a statistical regression gate (Cohen's kappa, power helpers). Only runtime dep is `textstat`; the judge is an optional extra. | library / dev-tool | **High** | **Borrow pattern**; license unresolved |
| `https://github.com/hadihonarvar/lynx` | Python ≥3.11 | Apache-2.0 | `lynx-agent` — stateless policy kernel for agent tool calls: five verdicts (`allow / deny / dry_run / approve_required / transform`), budgets, kill-switch, repetition gate, durable resume, tamper-evident audit events. "A library, not a server." | library | Low | Borrow concepts only; reject runtime |
| `https://github.com/Runewardd/runeward` | **Go 1.26** | Apache-2.0 | Agent governance harness: OPA policy, human approvals, Docker/k8s isolated execution, signed audit trail, MCP. Deps include OPA, k8s client-go, MCP Go SDK. | runtime framework | Near-zero | **Reject** (wrong language/infra) |
| `https://github.com/Polycentric-Labs/evidentia` | Python ≥3.12 | Apache-2.0 | OSCAL / GRC "compliance-as-code" monorepo (uv workspace, many packages): gap analysis, evidence collection, OSCAL emit. Large tree; `litellm` is a hard dep. | architectural reference | Low | **Reject runtime** |
| `https://github.com/agruai/ai-book-writer` | Python + TS | MIT | Full-stack book-writing app: 5 CrewAI agents (Concept Generator, Outliner, Writer, Editor, **Continuity Checker**), SSE streaming, Redis cache, budget controls. README references `cheesejaguar/book.ai`. | application | Low–Medium | Borrow the cross-artifact "continuity" idea; reject the app |
| `https://github.com/01-ai/langcrew` | Python ≥3.10 | MIT | LangGraph-based multi-agent framework ("OAK Framework", part of Open AgentKit), with a React UI library. | framework | Negative | **Reject** (LLM-agent framework; contradicts ADR-008) |
| `https://github.com/thehaurus/CourseGenAI` | Python | **No license** | Zero-shot matching of YouTube videos to a syllabus with `BART-large-mnli` (transformers). | application | Low | **Reject** (no license; off-core) |
| `https://github.com/tobyilee/book-writer` | Markdown | MIT (code) / CC BY-NC-SA (content) | A Claude Code prompt/style "harness" for writing books — not a library. | prompt reference | Low | **Reject** |
| `https://github.com/zain-ul-abdain/laravel-webhook-ledger` | **PHP ≥8.2** | MIT | Exactly-once webhook processing for Laravel: signature verification, atomic deduplication, durable event log. | library (other language) | Off-domain | **Reject** |
| `https://github.com/Alpha-Park/genpark-agentic-webhook-signature-verifier-skill` | Python (stdlib only) | MIT | An MCP skill that verifies webhook signatures. | skill | Off-domain | **Reject** |
| `https://github.com/RestDB/webhook-verify` | **TypeScript** | MIT | Multi-provider webhook signature verification (Stripe, GitHub, Shopify, Slack, …). | library (other language) | Off-domain | **Reject** |
| `https://github.com/arifos/amanai` | — | — | **Unverifiable.** Clone returned `repository not found`; direct fetch returns HTTP 404; a web search found no matching repository. | — | Unknown | **Record as unresolved** |

**Portfolio shape.** Only two candidates (QWED, llm-evalgate) are on-topic for the
target's verification focus. Three (`lynx`, `runeward`, `laravel-webhook-ledger`)
share a *recurring theme* — signed / tamper-evident evidence and durable event logs —
which the factory already partly has (`content_hash`, run-event log). The rest are
whole applications, other-language libraries, or off-domain webhook utilities.

---

## 3. Gap analysis (what the factory actually lacks)

1. **Semantic (not merely referential) consistency.** The factory proves IDs resolve
   and prerequisites are acyclic, but nothing asserts that a practice question is
   answerable from its lesson, or that an answer's content matches the question's
   intent. (llm-evalgate's judge path addresses this class; it is LLM-based and
   therefore out of scope for the deterministic core.)
2. **General math/science correctness beyond arithmetic.** `numerics.py` handles pure
   arithmetic assignments only; symbolic identities, units, and logic are explicitly
   "not checkable". QWED's SymPy/Z3 engines cover that space — at a heavy dependency
   cost.
3. **Statistically honest regression gating.** The factory has a benchmark *test*
   (`tests/test_benchmark_beginner_definition.py`) but no product/CI gate with a
   confidence interval and noise floor on quality metrics. llm-evalgate's bootstrap-CI
   regression gate is exactly that pattern, and it is pure-Python/offline.
4. **A single verifiable verification record.** The factory has `content_hash`, but no
   single record with an explicit verified/unverifiable/admitted decision plus a hash
   commitment. QWED's `DiagnosticResult{status, admission, proof_ref}` and lynx's
   tamper-evident audit are the reference patterns.

**Not gaps (out of scope for this target).** Webhook idempotency/signature handling,
agent tool-call governance, multi-agent orchestration, video-to-syllabus matching, and
GRC/OSCAL compliance emission are all unrelated to what the factory does.

---

## 4. Minimal integration design (proposed, not implemented)

Constraint: stay inside the existing **schema → validator → gate** flow. No new
require-path dependency, no new pipeline stage, no behaviour change to the
deterministic default.

- **G1 — Symbolic consistency seam (borrow QWED, offline).** New
  `src/lpf/validators/symbolic.py` exposing
  `check_symbolic_equivalence(lhs, rhs) -> Result[..., ValidationError]`. Ship it behind
  an **optional** extra (`lpf[symbolic]` → `sympy`) and keep the default install free of
  it. Register a new gate `SYMBOLIC_CONSISTENCY` in `orchestration/gates.py`, emit it
  from `qa_stage.py`, and give it exactly one owner in `revision.py` (repairable
  content). **Contract**: reuse `Result`/`ValidationError`; on a defect record
  `{"kind": "symbolic_mismatch", "location", "lhs", "rhs"}`.
- **G2 — Fail-closed verification record (borrow QWED's status/admission split).**
  Extend the existing `domain/quality.py` `VerificationResult`/`QualityGate` with
  `status ∈ {VERIFIED, UNVERIFIABLE, BLOCKED}`, `admission ∈ {ADMIT, DENY}`, and an
  optional `proof_ref` computed as the existing
  `identity.compute_content_hash(...)` over the gate evidence. **No new type** — a
  schema field plus the existing hash helper. Invariant: `UNVERIFIABLE` never yields
  `ADMIT`.
- **G3 — Statistical regression gate (borrow llm-evalgate, offline).** A test/CI helper
  (e.g. `tools/` or a benchmark module, not a pipeline stage) implementing bootstrap
  confidence intervals + Cohen's kappa + a power check over a labelled fixture, so a
  quality drop only fails CI when it clears the noise floor. **Contract**:
  `regression_decision(baseline, candidate, alpha, power) -> {regressed, ci, p}`.
  *Deferred*: do not vendor llm-evalgate until its missing `LICENSE` file is resolved;
  the pattern itself is freely reimplementable.

Explicitly **not** adopted: any LLM-as-judge (breaks offline determinism), the QWED
FastAPI server, agent frameworks, and every Go / PHP / TypeScript component.

---

## 5. Risks, compatibility, and license questions

| Area | Risk | Note |
|---|---|---|
| QWED dependency surface | **High** | `fastapi`, `uvicorn`, `openai`, `anthropic`, **`z3-solver`**, `pandas`, `numpy`, `scipy`, `sqlglot`, `sqlmodel`, `bcrypt`, `passlib`, `pyjwt`, `cryptography`, `networkx`. Vendoring it would multiply the factory's dependency and CVE surface. Only the narrow `sympy` engine is worth borrowing, and only as an optional extra. |
| QWED API stability | Medium | Version **7.2.2**, released hours before inspection; module path `qwed_new.core`; `z3-solver` pinned to `5.1.0.0`. Fast-moving major line → do not bind to it. |
| llm-evalgate license | **High / unresolved** | `pyproject.toml` declares `license = {text = "MIT"}` and an MIT classifier, but **no `LICENSE` file exists** in the repository (verified). Do not vendor until clarified; the bootstrap-CI technique is reimplementable without the code. |
| Missing licenses elsewhere | Medium | `coursegenai` has **no license at all**; `book-writer` bundles content under **CC BY-NC-SA 4.0** (non-commercial). |
| Determinism / offline invariant | **High if violated** | Any LLM-judge or live-model dependency breaks ADR-008 and the deterministic 97%-covered suite. Borrowed ideas must stay offline and optional. |
| Runtime compatibility | Low / **blocking** | `runeward` (Go), `laravel-webhook-ledger` (PHP ≥8.2 / `illuminate`), and `webhook-verify` (TypeScript) cannot integrate with a Python package at all. |
| `amanai` | **Unsupported** | 404 on direct fetch; no matching repository found. Cannot be assessed or adopted. |
| Supply-chain (general) | Medium | QWED and llm-evalgate are young and fast-releasing; pinning or vendoring either commits the factory to someone else's release cadence. |

---

## 6. Proof-of-concept plan (tests + acceptance criteria)

Scope the PoC to **G1 + G2** (highest value, lowest risk). G3 stays a test-only add-on
and is deferred pending the license question.

**G1 — symbolic verifier**
- New `src/lpf/validators/symbolic.py`, import-guarded, behind `lpf[symbolic]`.
- Tests in `tests/test_validators_symbolic.py` (skipped via `pytest.importorskip` when
  the extra is absent): algebraic identity passes, genuine mismatch fails, non-symbolic
  text is *not checkable* (never fails), unparseable/malicious input is rejected without
  execution.
- One `qa_stage` test proving the `SYMBOLIC_CONSISTENCY` gate is emitted with the extra
  installed, plus one end-to-end failing-run test.

**G2 — fail-closed verification record**
- Add `status` / `admission` / `proof_ref` to `domain/quality.py`; assert
  `proof_ref == compute_content_hash(evidence)` and that `UNVERIFIABLE ⇒ not ADMIT`.
- Extend `tests/test_quality_contract.py`.

**Acceptance criteria for the PoC**
1. Default install and all existing tests are unchanged; no new mandatory dependency.
2. Total coverage holds at ≥97% (the pytest gate enforces it).
3. `ruff` lint + format clean.
4. Fail-closed verified: no unverifiable claim can be admitted.
5. The `symbolic` extra installs cleanly and its absence degrades gracefully
   (skip, never guess).
6. A mutation harness kills the new validators' failure paths.

**Out of scope**: any change to pipeline stages, research providers, packaging, or the
deterministic default output.

---

## 7. Recommendation

**Borrow patterns only — zero new mandatory dependencies.**

1. **QWED → borrow.** Adopt the fail-closed `status`/`admission` split and the
   `proof_ref` hash commitment into `domain/quality.py` (G2), and add a symbolic
   verifier behind an **optional `sympy` extra** (G1). **Do not** depend on the `qwed`
   package.
2. **llm-evalgate → borrow.** Adopt the bootstrap-CI / Cohen's-kappa statistical
   regression gate as a test/CI helper (G3). **Do not** vendor it until the missing
   `LICENSE` is clarified, and **do not** adopt the judge path.
3. **Reject as runtime:** `runeward`, `langcrew`, `ai-book-writer`, `evidentia`,
   `coursegenai`, `book-writer`, `laravel-webhook-ledger`,
   `genpark-agentic-webhook-signature-verifier-skill`, `webhook-verify`. Reasons:
   wrong language, whole-application scope, off-domain, or contradiction of the
   deterministic architecture.
4. **lynx:** borrow the tamper-evident / five-verdict framing only if G2 proves
   insufficient on its own.
5. **Unresolved, to revisit:** `amanai` (404 / cannot be assessed), the llm-evalgate
   license file, and QWED's long-term API stability.

The natural home for the G1+G2 work is the task drafted in Appendix A.

---

## Appendix A — Draft task (not yet added to `tasks.md`)

Held here rather than appended to `tasks.md` because the open **v0.9.0** milestone is
themed *"Real Prose End to End"* (a live writer), whereas G1+G2 are *verification*
capabilities. Either widen v0.9.0's motivation or place this in its own "Verification
Hardening" milestone before promoting it to the backlog.

```markdown
- [ ] **TASK-018**: Optional Symbolic Consistency Gate + Fail-Closed Verification Record (portfolio-research borrow PoC)
  - **Objective**: Two borrow-only hardening items from the repository integration research
    (`docs/research/repository-integration-research.md`), with **zero new mandatory
    dependencies** and no change to the offline default. (1) Add an *optional* symbolic
    consistency validator — behind a new `lpf[symbolic]` extra — that checks algebraic
    / scientific equalities the arithmetic-only `validators/numerics.py` deliberately
    reports as "not checkable", and wire it as a new `symbolic_consistency` gate.
    (2) Make the verification contract fail-closed: give the verification record a
    `status ∈ {VERIFIED, UNVERIFIABLE, BLOCKED}` and an `admission ∈ {ADMIT, DENY}`
    with a `proof_ref` content-hash commitment, so a claim the factory cannot check is
    never admitted (the QWED `DiagnosticResult` pattern, reimplemented locally).
  - **Acceptance Criteria**:
    - Default install (no `symbolic` extra) is unchanged: the new validator is absent
      from `qa_stage`'s gate set and the full suite passes with no new dependency.
    - With `pip install -e ".[symbolic]"`, `check_symbolic_equivalence(lhs, rhs)` (in a
      new `src/lpf/validators/symbolic.py`) verifies algebraic identities
      (e.g. `(a+b)**2 == a**2 + 2*a*b + b**2`), rejects true mismatches, and follows the
      existing "skip, never guess" rule: anything outside a conservative whitelist is
      reported *not checkable*, never executed and never failed.
    - New gate `SYMBOLIC_CONSISTENCY` is declared in `orchestration/gates.py`, emitted
      by `qa_stage.py`, and owned by exactly one revision set; the catalog cross-check
      test (`test_revision_loop.py`) still proves `ALL_GATES` == the union of the
      ownership sets, and a run with the extra installed emits the new gate.
    - The verification record (`domain/quality.py`) gains `status`, `admission`, and
      `proof_ref`; `UNVERIFIABLE` never yields `ADMIT` (fail-closed); `proof_ref` equals
      `identity.compute_content_hash(...)` over the gate's evidence and is byte-stable
      across two identical runs.
    - A new `tests/test_validators_symbolic.py` covers identity/mismatch/not-checkable/
      unparseable cases, gated by `pytest.importorskip("sympy")` so the default run is
      unaffected; `tests/test_quality_contract.py` covers the status/admission/proof_ref
      invariants.
    - Full pytest suite passes with total coverage ≥97% (`--cov-fail-under=97`); ruff
      lint + format clean; a mutation harness kills the new failure paths.
  - **Non-goals**: no dependency on the `qwed` package or the `llm-evalgate` package; no
    LLM-as-judge; no change to pipeline stages, research providers, packaging, or the
    deterministic default output; no statistical regression gate (deferred — needs the
    llm-evalgate license file clarified first).
  - **Provenance**: repository integration research (this project's portfolio search).
    Research disposition: QWED → borrow (concepts only); llm-evalgate → borrow pattern
    only, license unresolved; all other candidates rejected (see research report).
```

---

## Appendix B — Evidence trail and unresolved questions

**How each candidate was assessed.** Cloned to `%TEMP%\opencode\candidates\<name>`
(shallow, `--depth 1`) and read directly: `LICENSE` (first lines), the primary manifest
(`pyproject.toml` / `go.mod` / `package.json` / `composer.json`), the README head, and
the core modules for the on-topic candidates (QWED engines, llm-evalgate gates). The
tree's file-extension profile and last-commit date were recorded per repository.

**Unresolved / unsupported claims.**
- `amanai` (`https://github.com/arifos/amanai`) — clone: "repository not found"; fetch:
  HTTP 404; no matching repository found by search. **Not assessed.**
- llm-evalgate — declared MIT in `pyproject.toml` but **no `LICENSE` file present**.
  License status is unresolved pending author confirmation.
- QWED — assessed at version 7.2.2; being a fast-moving line, API details may drift.
- No candidate was executed or installed; all behavioural claims are from source
  reading, not runtime trials.
