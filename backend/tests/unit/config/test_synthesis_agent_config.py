"""Unit tests for SynthesisAgent configuration."""

import pytest

from tarsy.agents.synthesis_agent import SynthesisAgent
from tarsy.config.builtin_config import BUILTIN_AGENTS
from tarsy.models.constants import IterationStrategy


@pytest.mark.unit
class TestSynthesisAgentConfiguration:
    """Test cases for SynthesisAgent configuration in builtin_config."""

    def test_synthesis_agent_in_builtin_agents(self) -> None:
        """Test that SynthesisAgent is registered in BUILTIN_AGENTS."""
        assert "SynthesisAgent" in BUILTIN_AGENTS
        
        config = BUILTIN_AGENTS["SynthesisAgent"]
        assert config["import"] == "tarsy.agents.synthesis_agent.SynthesisAgent"
        assert config["iteration_strategy"] == "react"
        assert "description" in config

    def test_synthesis_agent_description(self) -> None:
        """Test that SynthesisAgent has a meaningful description."""
        config = BUILTIN_AGENTS["SynthesisAgent"]
        description = config["description"]
        
        assert "synthesizes" in description.lower() or "synthesis" in description.lower()
        assert "parallel" in description.lower()

    def test_synthesis_agent_iteration_strategy(self) -> None:
        """Test that SynthesisAgent uses REACT iteration strategy."""
        config = BUILTIN_AGENTS["SynthesisAgent"]
        
        assert config["iteration_strategy"] == "react"

    def test_synthesis_agent_instantiation(
        self, isolated_test_settings, patch_settings_for_tests
    ) -> None:
        """Test that SynthesisAgent can be instantiated with required dependencies."""
        from unittest.mock import Mock
        
        from tarsy.models.agent_config import IterationStrategy
        
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        agent = SynthesisAgent(
            llm_manager=llm_manager,
            mcp_client=mcp_client,
            mcp_registry=mcp_registry,
            iteration_strategy=IterationStrategy.REACT
        )
        
        assert agent is not None
        assert isinstance(agent, SynthesisAgent)

    def test_synthesis_agent_no_mcp_servers(
        self, isolated_test_settings, patch_settings_for_tests
    ) -> None:
        """Test that SynthesisAgent requires no MCP servers."""
        from unittest.mock import Mock
        
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        agent = SynthesisAgent(
            llm_manager=llm_manager,
            mcp_client=mcp_client,
            mcp_registry=mcp_registry
        )
        
        mcp_servers = agent.mcp_servers()
        
        assert mcp_servers == []

    def test_synthesis_agent_custom_instructions(
        self, isolated_test_settings, patch_settings_for_tests
    ) -> None:
        """Test that SynthesisAgent has custom instructions for synthesis."""
        from unittest.mock import Mock
        
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        agent = SynthesisAgent(
            llm_manager=llm_manager,
            mcp_client=mcp_client,
            mcp_registry=mcp_registry
        )
        
        instructions = agent.custom_instructions()
        
        assert instructions
        assert "investigations" in instructions.lower() or "synthesizing" in instructions.lower()
        assert "quality" in instructions.lower() or "evaluate" in instructions.lower()

    def test_synthesis_agent_instructions_content(
        self, isolated_test_settings, patch_settings_for_tests
    ) -> None:
        """Test that SynthesisAgent instructions contain key concepts."""
        from unittest.mock import Mock
        
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        agent = SynthesisAgent(
            llm_manager=llm_manager,
            mcp_client=mcp_client,
            mcp_registry=mcp_registry
        )
        
        instructions = agent.custom_instructions().lower()
        
        key_concepts = [
            "evaluate",
            "evidence",
            "quality",
            "analysis",
            "root cause"
        ]
        
        found_concepts = [concept for concept in key_concepts if concept in instructions]
        
        assert len(found_concepts) >= 3, f"Instructions should contain at least 3 key concepts, found: {found_concepts}"

    def test_synthesis_agent_default_iteration_strategy(
        self, isolated_test_settings, patch_settings_for_tests
    ) -> None:
        """Test that SynthesisAgent defaults to REACT strategy."""
        from unittest.mock import Mock
        
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        agent = SynthesisAgent(
            llm_manager=llm_manager,
            mcp_client=mcp_client,
            mcp_registry=mcp_registry
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT

    def test_synthesis_agent_custom_iteration_strategy(
        self, isolated_test_settings, patch_settings_for_tests
    ) -> None:
        """Test that SynthesisAgent can use custom iteration strategy."""
        from unittest.mock import Mock
        
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        agent = SynthesisAgent(
            llm_manager=llm_manager,
            mcp_client=mcp_client,
            mcp_registry=mcp_registry,
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT_STAGE

