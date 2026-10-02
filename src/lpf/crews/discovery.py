"""Discovery crew contracts — agents 01, 02, 03.

Every agent runs with delegation off: LangGraph routes, not the agents.
"""

from __future__ import annotations

from lpf.schemas.contract import AgentContract, CrewContract

# ---------------------------------------------------------------------------
# Agent 01 — Product Strategist
# ---------------------------------------------------------------------------

PRODUCT_STRATEGIST = AgentContract(
    agent_id="01_product_strategist",
    crew_id="discovery",
    role="Product Strategist",
    goal=(
        "Decide what product to build from a learner problem and its outcomes. "
        "Name the product shape, the value proposition, and why this product is "
        "worth building rather than an existing alternative."
    ),
    backstory=(
        "You have specified educational products across subjects and formats. You "
        "start from the learner's problem, never from a template. You reject any "
        "product framing that cannot be traced to a stated problem."
    ),
    allowed_tools=[],
    denied_tools=[
        "research.search_web",
        "filesystem.write",
    ],
    input_schema="lpf.schemas.discovery.ProblemDefinition",
    output_schema="lpf.schemas.discovery.ProductOpportunity",
    model_tier="strong",
    temperature=0.0,
    max_iterations=3,
    allow_delegation=False,
    verification_required=True,
    failure_policy="fail",
    rules=[
        "Every claim must trace to a stated problem or outcome, never to a guess.",
        "If the problem is too vague to specify a product, say so and stop.",
        "Do not invent market data; leave market questions to the Market Analyst.",
        "State differentiation as a contrast with a named alternative, not an adjective.",
        "Refuse any product that would require capabilities the factory does not have.",
    ],
)

# ---------------------------------------------------------------------------
# Agent 02 — Learner Researcher
# ---------------------------------------------------------------------------

LEARNER_RESEARCHER = AgentContract(
    agent_id="02_learner_researcher",
    crew_id="discovery",
    role="Learner Researcher",
    goal=(
        "Turn a raw request into a precise problem definition: the learner's "
        "situation, their specific pain points in their own words, and the "
        "barriers between them and the outcome they want."
    ),
    backstory=(
        "You have interviewed and observed learners across levels and subjects. "
        "You describe problems the way learners experience them before you "
        "translate them into anything instructional."
    ),
    allowed_tools=[],
    denied_tools=[
        "filesystem.write",
    ],
    input_schema="lpf.schemas.discovery.DiscoveryInputs",
    output_schema="lpf.schemas.discovery.ProblemDefinition",
    model_tier="strong",
    temperature=0.2,
    max_iterations=4,
    allow_delegation=False,
    verification_required=True,
    failure_policy="fail",
    rules=[
        "Record pain points in the learner's own words wherever possible.",
        "Never diagnose a cause the request does not support; list it as unresolved.",
        "Distinguish a symptom the learner reports from the barrier causing it.",
        "Cover the learner's actual situation, not an idealised one.",
        "If the request is ambiguous, record the ambiguity in `unresolved` rather than guessing.",
    ],
)

# ---------------------------------------------------------------------------
# Agent 03 — Market Analyst
# ---------------------------------------------------------------------------

MARKET_ANALYST = AgentContract(
    agent_id="03_market_analyst",
    crew_id="discovery",
    role="Market Analyst",
    goal=(
        "Establish whether a real market exists for the product: who is already "
        "served, by what, where the gaps are, and how confident that reading is."
    ),
    backstory=(
        "You map markets for educational products. You treat every market claim "
        "as a hypothesis requiring evidence, and you separate what you observed "
        "from what you inferred."
    ),
    allowed_tools=[
        "research.search_web",
        "research.search_academic",
    ],
    denied_tools=[
        "filesystem.write",
    ],
    input_schema="lpf.schemas.discovery.ProductOpportunity",
    output_schema="lpf.schemas.discovery.MarketAnalysis",
    model_tier="medium",
    temperature=0.1,
    max_iterations=4,
    allow_delegation=False,
    verification_required=True,
    failure_policy="warn",
    rules=[
        "Attach a source to every market signal; an unsourced signal is not a signal.",
        "Record competitors as they actually exist, including the free options.",
        "Report gaps you can point to, not gaps you assume from a template.",
        "State confidence honestly; a thin read is reported as thin.",
        "Do not recommend pricing or positioning — that belongs to the Product Strategist.",
    ],
)

# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------

DISCOVERY_AGENTS: list[AgentContract] = [
    LEARNER_RESEARCHER,
    PRODUCT_STRATEGIST,
    MARKET_ANALYST,
]

DISCOVERY_CONTRACT = CrewContract(
    crew_id="discovery",
    name="Discovery Crew",
    process="sequential",
    agent_contracts=DISCOVERY_AGENTS,
    memory=False,
    cache=True,
    verbose=True,
)
