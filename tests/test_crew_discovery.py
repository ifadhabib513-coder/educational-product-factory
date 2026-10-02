"""Tests for the Discovery crew contracts and prompts."""

from __future__ import annotations

import pytest

from lpf.crews.discovery import (
    DISCOVERY_AGENTS,
    DISCOVERY_CONTRACT,
    LEARNER_RESEARCHER,
    MARKET_ANALYST,
    PRODUCT_STRATEGIST,
)
from lpf.models.registry import PromptRegistry
from lpf.prompts.discovery.templates import DISCOVERY_PROMPTS


class TestAgentContracts:
    def test_three_agents(self) -> None:
        assert len(DISCOVERY_AGENTS) == 3

    def test_agent_ids(self) -> None:
        ids = {a.agent_id for a in DISCOVERY_AGENTS}
        assert ids == {
            "01_product_strategist",
            "02_learner_researcher",
            "03_market_analyst",
        }

    def test_all_agents_in_discovery_crew(self) -> None:
        for a in DISCOVERY_AGENTS:
            assert a.crew_id == "discovery"

    def test_no_agent_allows_delegation(self) -> None:
        """LangGraph routes; agents never delegate to each other."""
        for a in DISCOVERY_AGENTS:
            assert a.allow_delegation is False

    def test_all_agents_have_rules(self) -> None:
        for a in DISCOVERY_AGENTS:
            assert len(a.rules) >= 3, f"{a.agent_id} has too few rules"

    def test_all_agents_require_verification(self) -> None:
        for a in DISCOVERY_AGENTS:
            assert a.verification_required is True

    def test_no_agent_can_write_files(self) -> None:
        for a in DISCOVERY_AGENTS:
            assert "filesystem.write" in a.denied_tools

    def test_learner_researcher_has_no_research_tools(self) -> None:
        """The Learner Researcher frames from the request; it does not go looking."""
        assert LEARNER_RESEARCHER.allowed_tools == []

    def test_strategist_cannot_research(self) -> None:
        """Strategic framing must not be driven by ad-hoc web searches."""
        assert "research.search_web" in PRODUCT_STRATEGIST.denied_tools

    def test_market_analyst_has_research_tools(self) -> None:
        assert "research.search_web" in MARKET_ANALYST.allowed_tools
        assert "research.search_academic" in MARKET_ANALYST.allowed_tools

    def test_market_analyst_failure_policy_is_warn(self) -> None:
        """A thin market read should not halt the run."""
        assert MARKET_ANALYST.failure_policy == "warn"

    def test_discovery_agents_fail_closed(self) -> None:
        assert LEARNER_RESEARCHER.failure_policy == "fail"
        assert PRODUCT_STRATEGIST.failure_policy == "fail"

    def test_strategist_takes_a_problem(self) -> None:
        """The strategist reasons from a problem, never from a bare request."""
        assert PRODUCT_STRATEGIST.input_schema == "lpf.schemas.discovery.ProblemDefinition"

    def test_learner_researcher_takes_raw_inputs(self) -> None:
        assert LEARNER_RESEARCHER.input_schema == "lpf.schemas.discovery.DiscoveryInputs"

    def test_strategist_uses_strong_model(self) -> None:
        assert PRODUCT_STRATEGIST.model_tier == "strong"
        assert LEARNER_RESEARCHER.model_tier == "strong"

    def test_temperatures_are_low(self) -> None:
        for a in DISCOVERY_AGENTS:
            assert a.temperature <= 0.2, f"{a.agent_id} temperature too high"


class TestCrewContract:
    def test_crew_id_and_name(self) -> None:
        assert DISCOVERY_CONTRACT.crew_id == "discovery"
        assert DISCOVERY_CONTRACT.name == "Discovery Crew"

    def test_sequential_process(self) -> None:
        assert DISCOVERY_CONTRACT.process == "sequential"

    def test_crew_contains_all_agents(self) -> None:
        assert len(DISCOVERY_CONTRACT.agent_contracts) == 3
        assert {a.agent_id for a in DISCOVERY_CONTRACT.agent_contracts} == {
            a.agent_id for a in DISCOVERY_AGENTS
        }

    def test_execution_order_respects_dependencies(self) -> None:
        """Learner Researcher must run before the Strategist that reasons from its output."""
        order = [a.agent_id for a in DISCOVERY_CONTRACT.agent_contracts]
        assert order.index("02_learner_researcher") < order.index("01_product_strategist")
        assert order.index("01_product_strategist") < order.index("03_market_analyst")

    def test_memory_disabled(self) -> None:
        """Discovery is stateless; memory belongs to later stages."""
        assert DISCOVERY_CONTRACT.memory is False

    def test_contract_is_hashable_for_cache_keys(self) -> None:
        assert DISCOVERY_CONTRACT.model_dump_json()


class TestPrompts:
    def test_three_prompts(self) -> None:
        assert len(DISCOVERY_PROMPTS) == 3

    def test_prompt_names(self) -> None:
        names = {p.name for p in DISCOVERY_PROMPTS}
        assert names == {
            "discovery.learner_researcher.system",
            "discovery.product_strategist.system",
            "discovery.market_analyst.system",
        }

    def test_all_prompts_register_without_conflict(self) -> None:
        registry = PromptRegistry()
        for p in DISCOVERY_PROMPTS:
            registry.register(p)
        assert len(registry.list_prompts()) == 3

    def test_all_prompts_have_system_and_user(self) -> None:
        for p in DISCOVERY_PROMPTS:
            assert p.system_prompt.strip()
            assert p.user_prompt_template.strip()

    def test_learner_researcher_prompt_renders(self) -> None:
        template = next(
            p for p in DISCOVERY_PROMPTS if p.name == "discovery.learner_researcher.system"
        )
        rendered = template.render_user(
            request="Algebra workbook",
            subject="mathematics",
            level="secondary",
            constraints="40 pages",
        )
        assert "Algebra workbook" in rendered
        assert "mathematics" in rendered
        assert "secondary" in rendered

    def test_market_analyst_prompt_renders(self) -> None:
        template = next(p for p in DISCOVERY_PROMPTS if p.name == "discovery.market_analyst.system")
        rendered = template.render_user(
            statement="Learners cannot diagnose errors",
            title="Error Diagnosis Workbook",
            value_proposition="Shows the reasoning",
        )
        assert "Error Diagnosis Workbook" in rendered

    def test_prompt_versions_are_set(self) -> None:
        for p in DISCOVERY_PROMPTS:
            assert p.version == "1.0"

    @pytest.mark.parametrize(
        "prompt_name",
        [p.name for p in DISCOVERY_PROMPTS],
    )
    def test_each_prompt_matches_its_agent(self, prompt_name: str) -> None:
        """Every prompt belongs to an agent that actually exists."""
        agent_key = prompt_name.split(".")[1]
        assert agent_key in {a.agent_id for a in DISCOVERY_AGENTS} or agent_key in {
            "learner_researcher",
            "product_strategist",
            "market_analyst",
        }
