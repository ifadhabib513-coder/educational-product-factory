# Version History

Subject-agnostic Educational Product Factory — from a problem statement to a
verified, audience-appropriate learning product.

## How to Read This Document

Each version follows the same structure:

- **Introduction** — What is this version
- **Goal** — What problem it solves
- **Features & Benefits** — What it provides
- **Gaps It Covers** — What was missing before this version
- **Gaps Still Remaining** — What this version does NOT solve
- **Next Version** — How the next version addresses those gaps

Versions are ordered oldest to newest. Each version states its own gaps rather
than implying the work is finished, so the final entry is the honest measure of
where the project stands.

---

## v0.6.0 — Deterministic Offline Pipeline (Mock End-to-End)

### Introduction
The stages had never run together. Discovery, specification, research, syllabus,
content, assessment, QA, and packaging each worked in isolation, and a
per-module test suite cannot catch a disagreement *between* modules. This version
wires them into one offline pipeline and, in doing so, found three real
integration defects on the very first run.

### Goal
Prove the whole spine runs end to end and that two runs with the same inputs
produce byte-identical output — the only demonstration that matters for a factory
whose central claim is reproducibility.

### Features & Benefits
- **A linear stage machine.** `created → discovery → specification → research →
  syllabus → content → assessment → qa → packaging → complete`, with `failed`
  reachable from every non-terminal stage. Illegal transitions raise
  `ILLEGAL_TRANSITION`, making out-of-order and silently-skipped stages impossible
  by construction.
- **A deterministic `RunContext`.** Artifact ids become
  `<run_id>-<kind>-<n>` (numbered per kind) and timestamps advance one second per
  call from a fixed epoch, so ids and `created_at` ordering are stable across
  runs. `uuid4` and `datetime.now()` are never used directly.
- **An event log as audit trail.** Every stage start and completion, plus
  run start, completion, and failure, is written to `run_log.json`.
- **The model isolated behind `ModelProvider`.** A deterministic mock supplies
  lesson prose — the one place a model is genuinely required. Every decision that
  has to be *right* is made by deterministic code.
- **The real research engine, offline.** Only the search provider is swapped; the
  genuine dedupe, filter, rank, claim, conflict, and evidence-map logic runs end
  to end.
- **QA gates that delegate to the real validators**, plus curriculum-coverage and
  evidence gates. A `failed` verdict aborts the run before packaging.
- **Working packaging.** `lpf generate` now writes `manifest.json`,
  `run_log.json`, `product.md`, and one JSON file per artifact under
  `projects/<run_id>/`.
- **Three production defects fixed at the source:**
  - `ResearchPipeline` generated a fresh `uuid4` `claim_id` per claim and ignored
    the `run_id` it already accepted. It now uses it.
  - `QualityGate.checked_at` defaulted to `datetime.now()`.
  - Packaging ran *before* the run reached `complete`, so the manifest recorded
    the run as still `packaging` and the run log omitted `run_completed`.

### Gaps It Covers
- No end-to-end path: the stages existed but had never been composed.
- A `lpf generate` command that printed `Not yet implemented`.
- No proof of reproducibility — the project's core claim was untested.
- Three latent defects that only an integration run could reveal.

### Gaps Still Remaining
- The stage machine is linear: no retry, no repair, no revision loop. The
  Revision crew will require cycles.
- Mock content is canned placeholder prose. It proves the wiring, not the
  pedagogy.
- The mock's canned sentences share bucket words, so the conflict detector
  reports eight spurious conflicts.
- Only the mock provider is wired; live providers are not selectable yet.
- Package output is Markdown and JSON only — no HTML, PDF, or ZIP bundle.
- Four of the ten planned hard gates (factual, numerical/symbolic, linguistic,
  rendering) are not implemented.
- The exact-title definitional signal from v0.5.0 remains outstanding.

### Next Version
v0.7.0 adds the exact-title definitional signal and moves toward real content
generation behind the live-provider layer, so the pipeline stops shipping canned
prose.

---

## v0.5.0 — Intent-Conditioned Ranking and Audience Fit

### Introduction
The research engine could retrieve relevant sources, but ranked them by raw
authority. For a beginner's definitional question it returned specialist
preprints over encyclopedias. This version makes ranking a function of *what the
learner is asking* and *who they are*.

### Goal
Make "the best source" a function of intent and audience, so an introductory
question surfaces introductory sources and a literature request surfaces papers —
without emptying the evidence map in the process.

### Features & Benefits
- **Seven deterministic query intents** (definitional, explanatory, procedural,
  academic literature, evidence synthesis, current, general), each with its own
  weight profile.
- **Authority as a fit, not a rank.** An encyclopedia scores `1.00` for
  definitional and `0.30` for academic literature; a preprint is the mirror
  image. This is what lets one pipeline serve both question types.
- **Definition-cue detection**, because token overlap rated both candidate
  sources `1.0` and could not separate *defining* a topic from *mentioning* it.
- **Audience fit** threaded from the existing `LearnerProfile.level` instead of
  being re-inferred per question.
- **Clarity and specialist-density proxies**, using notation markers rather than
  any field's jargon, so one weight set works across subjects.
- **Corpus-relative freshness** — identical provider responses always produce
  identical scores, preserving reproducibility.
- **Ranking score separated from confidence.** Confidence stays comparable across
  intents, which keeps the evidence threshold meaningful on every run.
- **Standing benchmark:** *Beginner Definition Retrieval* fails if a specialist
  source outranks an introductory one.

### Gaps It Covers
- Specialist arXiv papers outranking encyclopedias for "What is X?" questions.
- A single global weight dial, which could only favour beginners or academics,
  never both.
- Silent EvidenceMap collapse when weights skewed academic.

### Gaps Still Remaining
- A narrow page whose title exactly matches the query can still outrank the
  canonical definitional article (observed live: `Basic Linear Algebra
  Subprograms` beat `Linear algebra`). An exact-title signal would fix it.
- Density detection keys on notation, so a specialist paper written in plain
  prose is mis-scored.
- Intent classification is rule-based and does not handle multi-intent questions
  such as "What is X, and where did research on it stand in 2026?"
- Confidence is not yet surfaced per-intent in reports, so a reader cannot tell
  *why* a claim was marked unsupported.

### Next Version
v0.6.0 wired the stages into a deterministic end-to-end pipeline (the exact-title
definitional signal remains outstanding and is carried to v0.7.0).

---

## v0.4.1 — Live Provider Verification and Derived Relevance

### Introduction
A hardening release following live internet testing of the research pipeline.
It fixed one genuine provider bug and one genuine logic bug, both of which had
passed a green test suite.

### Goal
Verify the pipeline against real services, and ensure providers that report no
relevance score are not silently penalised.

### Features & Benefits
- **Live verification against arXiv and Wikimedia** with real network calls.
- **Derived relevance scoring** for providers that report none. Previously only
  Tavily supplied a relevance score; arXiv, Wikimedia, and SearXNG left it at
  `0.0`, so every such result was filtered out downstream.
- **Wikimedia User-Agent compliance** via `LPF_RESEARCH_CONTACT`, fixing HTTP
  `403` responses caused by a contact-less User-Agent.
- **Mutation-verified tests.** Every fix was re-checked by deliberately breaking
  the source and confirming named tests failed — after finding earlier tests that
  passed while proving nothing.

### Gaps It Covers
- A pipeline that returned sources but treated most of them as irrelevant.
- Wikimedia blocking all requests for want of a compliant User-Agent.
- Test suites that gave false confidence by not failing on real regressions.

### Gaps Still Remaining
- Tavily cannot be live-tested without an API key; its adapter is mock-tested
  only.
- Public SearXNG instances do not serve reliable JSON APIs (HTML responses,
  `429`, `403`, DNS failures); self-hosting is still required.
- Publication dates are populated only by arXiv and Tavily; Wikipedia and
  SearXNG dates are discarded, so freshness is neutral for them.
- The default Wikimedia contact URL is a placeholder and must be replaced before
  deployment.

### Next Version
v0.5.0 uses the corrected relevance signal as the basis for intent- and
audience-conditioned ranking.

---

## v0.4.0 — Research Engine: Providers, Pipeline, Evidence Map

### Introduction
The research stage moved from contracts to working code: HTTP transport with
retries, four real providers, deterministic authority classification, a
deduplicating pipeline, and a conflict-aware evidence map.

### Goal
Turn "ask a model to find sources" into a deterministic, reproducible,
model-free research stage.

### Features & Benefits
- **Deterministic authority classification** across seven tiers — the model is
  never the verification authority.
- **HTTP transport** with exponential backoff, rate limiting, and typed errors.
- **Four providers:** SearXNG, Tavily, arXiv, Wikimedia — each degrading
  gracefully so one failure cannot empty a run.
- **Deduplication** that keeps the best-ranked copy of a repeated source.
- **Conflict detection** across sources, and an EvidenceMap of supported and
  unsupported claims.
- **Context-separated unit tests** — no network access in the suite.

### Gaps It Covers
- Provider interfaces with no implementations.
- Ranking with no reproducible authority signal.
- No structured evidence trail from source to claim.

### Gaps Still Remaining
- Providers reporting no relevance score were treated as irrelevant.
- Authority-only ranking suited no question type well.
- No live-provider verification.

### Next Version
v0.4.1 verifies the engine live and fixes the relevance gap.

---

## v0.3.0 — Discovery Stage

### Introduction
The first stage of the factory proper: turning a raw problem statement into a
structured, validated learner and topic definition that later stages consume.

### Goal
Establish who the learner is and what they need, before generating anything.

### Features & Benefits
- **Discovery orchestration** with typed stage outputs.
- **Learner profiling**, including the level signal later reused for audience fit.
- **Validation** rejecting incomplete or contradictory discovery output.

### Gaps It Covers
- Generating content for an undefined audience.
- No validated handoff between stages.

### Gaps Still Remaining
- No syllabus construction from the discovery output.
- No rendering of a learner-facing product.
- Stage contracts only — the full multi-agent workflow was not yet wired.

### Next Version
v0.4.0 built the research engine the syllabus stage depends on.

---

## v0.2.0 — Infrastructure and Service Contracts

### Introduction
Reusable infrastructure beneath the stages: model access, prompt management,
repositories, tool definitions, and the research service layer.

### Goal
Stop re-inventing model access, storage, and service wiring per stage.

### Features & Benefits
- **Model provider and router**, with a mock provider so tests never call a real
  API.
- **Prompt management** separated from code.
- **Repository and database layer** for artifacts.
- **Tool definitions** and agent contracts.
- **Typed `Result` model** so failures are values, not exceptions.

### Gaps It Covers
- Scattered ad-hoc API calls.
- No consistent error representation.
- Untestable code depending on live model calls.

### Gaps Still Remaining
- Database migrations were never generated.
- The CLI remained a skeleton.
- No working end-to-end product path.

### Next Version
v0.3.0 used this infrastructure for the first real stage.

---

## v0.1.0 — Foundation

### Introduction
The project skeleton: configuration, the `Result` type, a domain-model
convention, a CLI entry point, and continuous integration.

### Goal
Establish conventions before writing stage logic.

### Features & Benefits
- **Typed configuration** loaded from environment variables, all optional.
- **`Result` model** for explicit success and failure.
- **Pydantic domain schemas** with validation.
- **CLI skeleton** and a **test/lint CI pipeline**.

### Gaps It Covers
- No agreed conventions for errors, config, or validation.

### Gaps Still Remaining
- No stages implemented.
- No research capability.
- No tests beyond scaffolding.

### Next Version
v0.2.0 built the shared infrastructure.

---

## Current Status

**v0.6.0 is complete and verified.** The stages from Discovery through Packaging
run as one offline pipeline and produce byte-identical output across runs. The
research stage retrieves, scores, ranks, and builds evidence maps for the right
audience; `lpf generate` now writes a real product.

**The product does not yet exist end to end.** A product is generated, but its
content is canned mock prose, its provider layer has no live implementation wired
in, its stage machine does not loop (no self-correction or revision), and its
output is Markdown/JSON rather than a rendered book. What exists so far is the
spine — reproducible, auditable, and wired — plus the part of the factory most
likely to be got quietly wrong, how sources are chosen, built deliberately and
verified against live services.