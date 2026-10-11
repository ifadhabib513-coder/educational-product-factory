# ADR-005: Discovery Stage — Schemas, Contracts, and Validation

**Status:** Accepted
**Date:** 2026-10-02

## Context

The factory cannot generate content until it knows *what* problem it is solving and *who* it is solving it for. The Discovery stage establishes both before any curriculum or content work begins.

Three failure modes drove the design:

1. **Drift.** Artifacts produced by separate stages silently referencing different problems, invalidating everything downstream.
2. **Dangling references.** A brief pointing at artifacts that do not exist passes every structural check but fails at consumption.
3. **Unsourced market claims.** A market read that is really a guess gets treated as an input to product decisions.

## Decisions

### 1. Execution order is driven by data dependency, not agent numbering

The agents are numbered `01_product_strategist`, `02_learner_researcher`, `03_market_analyst`, but the crew executes them in the order **Learner Researcher → Product Strategist → Market Analyst**.

The numbering reflects the planning documents, where the strategist appears first as the conceptual entry point. The Product Strategist's own rule — *"every claim must trace to a stated problem"* — makes this impossible: it cannot reason from a bare request. `PRODUCT_STRATEGIST.input_schema` is therefore `ProblemDefinition`, not `DiscoveryInputs`.

The crew's `agent_contracts` list encodes the real execution order. A test asserts the ordering so the two lists cannot drift apart silently.

### 2. Five enums, all subject-agnostic

- **ProblemUrgency** (4): low, medium, high, critical
- **ProblemScope** (3): narrow, focused, broad
- **PainPointCategory** (7): understanding, retention, application, motivation, structure, assessment, confidence
- **MarketSegment** (6): self_learner, school, university, professional, parent, corporate
- **FeasibilityLevel** (4): high, medium, low, blocked

None name a discipline. `PainPointCategory` is the important one: it lets a learner problem be described in instructional terms before any subject vocabulary exists.

### 3. Pain points keep the learner's own words

`PainPoint.learner_voice` is optional but *recorded* when available. Framing a problem in the learner's language is what keeps downstream content at their reading level. The Learner Researcher's contract rule states this directly.

`ProblemBarrier` is separate from `PainPoint` because a symptom the learner reports and the barrier causing it are different claims. Conflating them produces products that address the wrong thing.

### 4. `ProductOpportunity` carries `implied_outcomes`, not `outcome_ids`

The obvious design — `ProductOpportunity.outcome_ids` referencing a not-yet-created `OutcomeDefinition` — creates a dangling reference, because the strategist produces the opportunity *before* the outcomes are formalised.

`implied_outcomes: list[LearningObjective]` embeds the outcome statements the strategist's reasoning implies. `OutcomeDefinition` then formalises those into an assessment-bearing artifact at the curriculum stage, and `check_outcome_references` verifies every formalised outcome traces back to an implied one. An outcome nobody implied is scope the strategist never agreed to.

### 5. `DiscoveryBrief` is reference-only

The brief carries IDs and a summary, never copied bodies. If it embedded the problem statement, the two would drift and there would be no way to tell which the Research crew read.

`check_discovery_brief` resolves all four references against the artifacts actually in hand.

### 6. Unresolved ambiguity is a field, not a guess

`ProblemDefinition.unresolved` and `ProductOpportunity.open_questions` exist so agents record what the request did not settle. The Learner Researcher's contract requires this over assumption. A product built on a silently-guessed premise is worse than one built on a stated uncertainty, because the guess is invisible downstream.

### 7. Tool permissions encode epistemic discipline

| Agent | Allowed | Denied |
|---|---|---|
| 02 Learner Researcher | *(none)* | — |
| 01 Product Strategist | *(none)* | `research.search_web` |
| 03 Market Analyst | `research.search_web`, `research.search_academic` | — |

All three deny `filesystem.write`; artifacts are committed by the orchestrator, never by an agent.

The Strategist is denied web search deliberately. Strategic framing is a reasoning task over the stated problem; letting it search invites fitting the product to whatever it happens to find. The Market Analyst searches, because its whole job is establishing that a market exists — and it is the one agent whose contract requires a source on every signal.

### 8. Failure policy differentiates the agents

- Learner Researcher: `fail` — a misframed problem corrupts everything.
- Product Strategist: `fail` — same reasoning.
- Market Analyst: `warn` — a thin market read is a finding to report, not a reason to halt.

### 9. Feasibility is gated, not assumed

`check_feasibility(actionable, opportunity)` takes an explicit `actionable` flag so a BLOCKED product is an error only when it was supposed to be buildable. Discovering that a product cannot be built is a legitimate result; the caller distinguishes the two cases.

### 10. `DiscoveryInputs` is not an artifact

It carries caller intent, which is legitimately partial and vague. Inheriting `ArtifactBase` would give it an id and a `content_hash` computed over input the factory did not generate — a hash that implies provenance it does not have.

## Consequences

- `check_discovery_chain` catches the common bug where a stage runs against a stale problem.
- `check_outcome_references` enforces traceability from curriculum back to strategy.
- Execution order lives in the crew contract, so LangGraph reads it from one place.
- Five `LearningObjective` values inside an opportunity are persisted redundantly with the later `OutcomeDefinition`. This is intentional: the strategist's reasoning is preserved as written, and the formalisation is a separate, checkable artifact.

## Alternatives Rejected

**Embed the problem statement in `DiscoveryBrief` for convenience.** Rejected — creates two sources of truth for the same text.

**Let the Product Strategist also do the web research.** Rejected — it removes the boundary between "what should we build" and "does anyone want it", and invites the product to fit the available search results.

**Number the agents in execution order.** Rejected — the numbers appear throughout the planning documents and roadmap; renumbering would break those references for no functional gain. The mismatch is resolved by documenting execution order in the contract instead.

## Amendment — 2026-10-11 (TASK-016)

The `check_discovery_brief`/`check_outcome_references`/`check_feasibility`/
`check_discovery_chain` functions (formerly `lpf/discovery/validation.py`) and the
`lpf/crews/discovery` contract scaffolding were **never wired to a shipped path** and
have been removed: `lpf/orchestration/discovery_stage.py` is the single deterministic
implementation, and pydantic construction enforces every artifact shape at the point
of creation. The traceability *intent* above still holds — it is simply inlined into
the stage rather than deferred to a separate, unrun validator. See the whole-codebase
audit (`docs/audits/codebase-gaps-and-bugs.md`, §5).