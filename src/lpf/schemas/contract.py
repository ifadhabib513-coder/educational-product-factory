"""Agent contract — machine-readable specification for every agent."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentContract(BaseModel):
    """Contract defining an agent's capabilities, inputs, outputs, and permissions.

    Every one of the 25 agents is configured from this contract.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    agent_id: str
    crew_id: str
    role: str
    goal: str
    backstory: str = ""

    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)

    input_schema: str
    output_schema: str

    model_tier: str = "medium"  # cheap | medium | strong
    model_name: str | None = None
    temperature: float = 0.0

    max_iterations: int = 4
    allow_delegation: bool = False

    verification_required: bool = True
    failure_policy: str = "fail"  # fail | warn | skip

    rules: list[str] = Field(default_factory=list)


class CrewContract(BaseModel):
    """Contract defining a crew's composition and execution model."""

    model_config = {"frozen": True, "extra": "forbid"}

    crew_id: str
    name: str
    process: str = "sequential"  # sequential | hierarchical
    agent_contracts: list[AgentContract] = Field(min_length=1)
    max_rpm: int | None = None
    memory: bool = False
    cache: bool = True
    verbose: bool = True
