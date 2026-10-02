"""Tests for AgentContract and CrewContract schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.schemas.contract import AgentContract, CrewContract


def _make_agent(**overrides) -> AgentContract:
    data = {
        "agent_id": "01_product_strategist",
        "crew_id": "discovery",
        "role": "Product Strategist",
        "goal": "Define the product scope from a learner problem.",
        "input_schema": "lpf.schemas.discovery.ProductBrief",
        "output_schema": "lpf.schemas.discovery.ProductBrief",
    }
    data.update(overrides)
    return AgentContract(**data)


# ---------------------------------------------------------------------------
# Tests: AgentContract
# ---------------------------------------------------------------------------


class TestAgentContract:
    def test_construction_minimal(self) -> None:
        c = _make_agent()
        assert c.agent_id == "01_product_strategist"
        assert c.crew_id == "discovery"

    def test_defaults(self) -> None:
        c = _make_agent()
        assert c.backstory == ""
        assert c.allowed_tools == []
        assert c.denied_tools == []
        assert c.model_tier == "medium"
        assert c.model_name is None
        assert c.temperature == 0.0
        assert c.max_iterations == 4
        assert c.allow_delegation is False
        assert c.verification_required is True
        assert c.failure_policy == "fail"
        assert c.rules == []

    def test_frozen(self) -> None:
        c = _make_agent()
        with pytest.raises(ValidationError):
            c.agent_id = "changed"  # type: ignore[misc]

    def test_unknown_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            _make_agent(unknown_field="x")

    def test_allow_delegation_can_be_enabled(self) -> None:
        c = _make_agent(allow_delegation=True)
        assert c.allow_delegation is True

    def test_tools_and_rules(self) -> None:
        c = _make_agent(
            allowed_tools=["research.search_web"],
            denied_tools=["filesystem.write"],
            rules=["Never invent sources.", "Always cite URLs."],
        )
        assert "research.search_web" in c.allowed_tools
        assert "filesystem.write" in c.denied_tools
        assert len(c.rules) == 2

    def test_model_tier_values(self) -> None:
        for tier in ("cheap", "medium", "strong"):
            assert _make_agent(model_tier=tier).model_tier == tier

    def test_failure_policy_values(self) -> None:
        for policy in ("fail", "warn", "skip"):
            assert _make_agent(failure_policy=policy).failure_policy == policy

    def test_required_fields_present(self) -> None:
        with pytest.raises(ValidationError):
            AgentContract(agent_id="x", crew_id="y")  # type: ignore[call-arg]

    def test_json_roundtrip(self) -> None:
        c = _make_agent(rules=["Rule one"], allowed_tools=["a.b"])
        restored = AgentContract.model_validate_json(c.model_dump_json())
        assert restored == c


# ---------------------------------------------------------------------------
# Tests: CrewContract
# ---------------------------------------------------------------------------


class TestCrewContract:
    def test_construction(self) -> None:
        crew = CrewContract(
            crew_id="discovery",
            name="Discovery Crew",
            agent_contracts=[_make_agent()],
        )
        assert crew.crew_id == "discovery"
        assert len(crew.agent_contracts) == 1

    def test_defaults(self) -> None:
        crew = CrewContract(
            crew_id="discovery",
            name="Discovery Crew",
            agent_contracts=[_make_agent()],
        )
        assert crew.process == "sequential"
        assert crew.max_rpm is None
        assert crew.memory is False
        assert crew.cache is True
        assert crew.verbose is True

    def test_empty_agents_raises(self) -> None:
        with pytest.raises(ValidationError):
            CrewContract(crew_id="discovery", name="Discovery", agent_contracts=[])

    def test_frozen(self) -> None:
        crew = CrewContract(
            crew_id="discovery",
            name="Discovery Crew",
            agent_contracts=[_make_agent()],
        )
        with pytest.raises(ValidationError):
            crew.name = "Changed"  # type: ignore[misc]

    def test_unknown_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CrewContract(
                crew_id="discovery",
                name="Discovery Crew",
                agent_contracts=[_make_agent()],
                bogus=1,
            )

    def test_multiple_agents(self) -> None:
        crew = CrewContract(
            crew_id="discovery",
            name="Discovery Crew",
            agent_contracts=[
                _make_agent(agent_id="01_product_strategist"),
                _make_agent(agent_id="02_learner_researcher"),
                _make_agent(agent_id="03_market_analyst"),
            ],
        )
        assert len(crew.agent_contracts) == 3

    def test_agent_crew_id_consistency_is_not_enforced(self) -> None:
        """Contracts are validated independently; cross-field checks belong to a validator."""
        crew = CrewContract(
            crew_id="discovery",
            name="Discovery Crew",
            agent_contracts=[_make_agent(crew_id="research")],
        )
        assert crew.agent_contracts[0].crew_id == "research"

    def test_process_hierarchical(self) -> None:
        crew = CrewContract(
            crew_id="research",
            name="Research Crew",
            agent_contracts=[_make_agent(crew_id="research")],
            process="hierarchical",
        )
        assert crew.process == "hierarchical"

    def test_json_roundtrip(self) -> None:
        crew = CrewContract(
            crew_id="discovery",
            name="Discovery Crew",
            agent_contracts=[_make_agent(rules=["r1"])],
        )
        restored = CrewContract.model_validate_json(crew.model_dump_json())
        assert restored == crew
