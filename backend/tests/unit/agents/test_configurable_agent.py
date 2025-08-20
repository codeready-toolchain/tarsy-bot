"""Unit tests for ConfigurableAgent."""

from unittest.mock import Mock

import pytest

from tarsy.agents.configurable_agent import ConfigurableAgent
from tarsy.models.agent_config import AgentConfigModel
from tarsy.models.constants import IterationStrategy


@pytest.mark.unit
class TestConfigurableAgent:
    """Test cases for ConfigurableAgent."""

    @pytest.fixture
    def mock_config(self):
        """Mock agent configuration for testing."""
        return AgentConfigModel(
            alert_types=["security", "intrusion"],
            mcp_servers=["security-tools", "vulnerability-scanner"],
            custom_instructions="Focus on threat detection and response."
        )

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for testing."""
        mock = Mock()
        mock.analyze = Mock()
        return mock

    @pytest.fixture
    def mock_mcp_client(self):
        """Mock MCP client for testing."""
        mock = Mock()
        mock.execute_tool = Mock()
        return mock

    @pytest.fixture
    def mock_mcp_registry(self):
        """Mock MCP server registry for testing."""
        mock = Mock()
        mock.get_server_config = Mock()
        return mock

    @pytest.fixture
    def agent(self, mock_config, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """ConfigurableAgent instance for testing."""
        return ConfigurableAgent(
            agent_name="test-security-agent",
            config=mock_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )

    def test_init_success(self, mock_config, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test successful ConfigurableAgent initialization."""
        agent = ConfigurableAgent(
            agent_name="test-agent",
            config=mock_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.agent_name == "test-agent"
        assert agent.config == mock_config
        assert agent.llm_client == mock_llm_client
        assert agent.mcp_client == mock_mcp_client
        assert agent.mcp_registry == mock_mcp_registry

    def test_init_with_none_config_fails(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that initialization fails with None config."""
        with pytest.raises(ValueError) as exc_info:
            ConfigurableAgent(
                agent_name="test-agent",
                config=None,
                llm_client=mock_llm_client,
                mcp_client=mock_mcp_client,
                mcp_registry=mock_mcp_registry
            )
            
        assert "Agent configuration is required and cannot be None" in str(exc_info.value)

    def test_init_with_none_llm_client_fails(self, mock_config, mock_mcp_client, mock_mcp_registry):
        """Test that initialization fails with None LLM client."""
        with pytest.raises(ValueError) as exc_info:
            ConfigurableAgent(
                agent_name="test-agent",
                config=mock_config,
                llm_client=None,
                mcp_client=mock_mcp_client,
                mcp_registry=mock_mcp_registry
            )
            
        assert "LLM client is required and cannot be None" in str(exc_info.value)

    def test_init_with_none_mcp_client_fails(self, mock_config, mock_llm_client, mock_mcp_registry):
        """Test that initialization fails with None MCP client."""
        with pytest.raises(ValueError) as exc_info:
            ConfigurableAgent(
                agent_name="test-agent",
                config=mock_config,
                llm_client=mock_llm_client,
                mcp_client=None,
                mcp_registry=mock_mcp_registry
            )
            
        assert "MCP client is required and cannot be None" in str(exc_info.value)

    def test_init_with_none_mcp_registry_fails(self, mock_config, mock_llm_client, mock_mcp_client):
        """Test that initialization fails with None MCP registry."""
        with pytest.raises(ValueError) as exc_info:
            ConfigurableAgent(
                agent_name="test-agent",
                config=mock_config,
                llm_client=mock_llm_client,
                mcp_client=mock_mcp_client,
                mcp_registry=None
            )
            
        assert "MCP registry is required and cannot be None" in str(exc_info.value)

    def test_mcp_servers_property(self, agent):
        """Test mcp_servers property returns configured servers."""
        servers = agent.mcp_servers()
        
        assert servers == ["security-tools", "vulnerability-scanner"]

    def test_custom_instructions_property_with_instructions(self, agent):
        """Test custom_instructions property when instructions are provided."""
        instructions = agent.custom_instructions()
        
        assert instructions == "Focus on threat detection and response."

    def test_custom_instructions_property_without_instructions(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test custom_instructions property when no instructions are provided."""
        config_without_instructions = AgentConfigModel(
            alert_types=["security"],
            mcp_servers=["security-tools"]
            # No custom_instructions field
        )
        
        agent = ConfigurableAgent(
            agent_name="test-agent",
            config=config_without_instructions,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        instructions = agent.custom_instructions()
        assert instructions == ""  # Default empty string, not None

    def test_generate_agent_name_from_agent_name(self, agent):
        """Test _generate_agent_name uses provided agent_name."""
        name = agent._generate_agent_name()
        
        assert name == "ConfigurableAgent(test-security-agent)"

    def test_generate_agent_name_with_different_name(self, mock_config, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test _generate_agent_name with different agent name."""
        agent = ConfigurableAgent(
            agent_name="performance-monitoring-agent",
            config=mock_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        name = agent._generate_agent_name()
        
        assert name == "ConfigurableAgent(performance-monitoring-agent)"

    def test_get_supported_alert_types(self, agent):
        """Test get_supported_alert_types returns configured alert types."""
        alert_types = agent.get_supported_alert_types()
        
        assert alert_types == ["security", "intrusion"]

    def test_get_supported_alert_types_single_type(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test get_supported_alert_types with single alert type."""
        config_single_type = AgentConfigModel(
            alert_types=["database"],
            mcp_servers=["db-tools"]
        )
        
        agent = ConfigurableAgent(
            agent_name="db-agent",
            config=config_single_type,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        alert_types = agent.get_supported_alert_types()
        
        assert alert_types == ["database"]

    def test_get_supported_alert_types_multiple_types(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test get_supported_alert_types with multiple alert types."""
        config_multiple_types = AgentConfigModel(
            alert_types=["performance", "monitoring", "infrastructure"],
            mcp_servers=["perf-tools", "infra-tools"]
        )
        
        agent = ConfigurableAgent(
            agent_name="multi-agent",
            config=config_multiple_types,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        alert_types = agent.get_supported_alert_types()
        
        assert alert_types == ["performance", "monitoring", "infrastructure"]

    def test_inheritance_from_base_agent(self, agent):
        """Test that ConfigurableAgent inherits from BaseAgent properly."""
        # Check that required BaseAgent methods exist
        assert hasattr(agent, 'mcp_servers')
        assert hasattr(agent, 'custom_instructions')
        assert hasattr(agent, 'process_alert')  # Main processing method
        
        # Check that agent has a proper name
        assert agent._generate_agent_name() == "ConfigurableAgent(test-security-agent)"

    def test_mcp_servers_consistency(self, agent):
        """Test that mcp_servers method returns consistent results."""
        # Call multiple times to ensure consistency
        servers1 = agent.mcp_servers()
        servers2 = agent.mcp_servers()
        servers3 = agent.mcp_servers()
        
        assert servers1 == servers2 == servers3
        assert servers1 == ["security-tools", "vulnerability-scanner"]

    def test_custom_instructions_consistency(self, agent):
        """Test that custom_instructions method returns consistent results."""
        # Call multiple times to ensure consistency
        instructions1 = agent.custom_instructions()
        instructions2 = agent.custom_instructions()
        instructions3 = agent.custom_instructions()
        
        assert instructions1 == instructions2 == instructions3
        assert instructions1 == "Focus on threat detection and response."

    def test_empty_mcp_servers_list(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with minimum required MCP servers (one server)."""
        config_min_servers = AgentConfigModel(
            alert_types=["test"],
            mcp_servers=["single-server"]  # Minimum one server required by Pydantic model
        )
        
        agent = ConfigurableAgent(
            agent_name="min-agent",
            config=config_min_servers,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        servers = agent.mcp_servers()
        assert servers == ["single-server"]

    def test_long_agent_name(self, mock_config, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with very long agent name."""
        long_name = "very-long-agent-name-for-comprehensive-security-monitoring-and-threat-detection-system"
        
        agent = ConfigurableAgent(
            agent_name=long_name,
            config=mock_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.agent_name == long_name
        assert agent._generate_agent_name() == f"ConfigurableAgent({long_name})"

    def test_agent_configuration_immutability(self, agent):
        """Test that agent configuration cannot be modified externally."""
        original_alert_types = agent.config.alert_types.copy()
        original_mcp_servers = agent.config.mcp_servers.copy()
        
        # Try to modify the configuration (should not affect agent behavior)
        returned_servers = agent.mcp_servers()
        returned_types = agent.get_supported_alert_types()
        
        # Agent should return the same data consistently
        assert agent.mcp_servers() == original_mcp_servers
        assert agent.get_supported_alert_types() == original_alert_types
        
        # Return values should match configuration
        assert returned_servers == original_mcp_servers
        assert returned_types == original_alert_types

    def test_special_characters_in_agent_name(self, mock_config, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with special characters in agent name."""
        special_name = "security-agent_v2.0-beta"
        
        agent = ConfigurableAgent(
            agent_name=special_name,
            config=mock_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.agent_name == special_name
        assert agent._generate_agent_name() == f"ConfigurableAgent({special_name})"

    def test_unicode_characters_in_custom_instructions(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with unicode characters in custom instructions."""
        config_with_unicode = AgentConfigModel(
            alert_types=["security"],
            mcp_servers=["security-tools"],
            custom_instructions="Analysez les menaces de sécurité 🔒 and respond appropriately"
        )
        
        agent = ConfigurableAgent(
            agent_name="unicode-agent",
            config=config_with_unicode,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        instructions = agent.custom_instructions()
        assert instructions == "Analysez les menaces de sécurité 🔒 and respond appropriately"


@pytest.mark.unit
class TestConfigurableAgentIterationStrategies:
    """Test iteration strategy support in ConfigurableAgent."""
    
    @pytest.fixture
    def mock_llm_client(self):
        return Mock()
    
    @pytest.fixture
    def mock_mcp_client(self):
        return Mock()
    
    @pytest.fixture
    def mock_mcp_registry(self):
        return Mock()
    
    def test_default_iteration_strategy_react(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that ConfigurableAgent defaults to REACT iteration strategy."""
        config = AgentConfigModel(
            alert_types=["security"],
            mcp_servers=["security-tools"]
            # No iteration_strategy specified - should default to REACT
        )
        
        agent = ConfigurableAgent(
            agent_name="test-agent",
            config=config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT
    
    def test_explicit_react_iteration_strategy(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with explicit REACT iteration strategy."""
        config = AgentConfigModel(
            alert_types=["security"],
            mcp_servers=["security-tools"],
            iteration_strategy=IterationStrategy.REACT
        )
        
        agent = ConfigurableAgent(
            agent_name="test-agent",
            config=config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT
    
    def test_react_stage_iteration_strategy(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with REACT_STAGE iteration strategy."""
        config = AgentConfigModel(
            alert_types=["performance"],
            mcp_servers=["monitoring-tools"],
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        agent = ConfigurableAgent(
            agent_name="performance-agent",
            config=config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT_STAGE
    
    def test_string_iteration_strategy_react(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with string-based REACT iteration strategy."""
        config = AgentConfigModel(
            alert_types=["security"],
            mcp_servers=["security-tools"],
            iteration_strategy="react"
        )
        
        agent = ConfigurableAgent(
            agent_name="test-agent",
            config=config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT
    
    def test_string_iteration_strategy_react_stage(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test ConfigurableAgent with string-based REACT_STAGE iteration strategy."""
        config = AgentConfigModel(
            alert_types=["performance"],
            mcp_servers=["monitoring-tools"],
            iteration_strategy="react-stage"
        )
        
        agent = ConfigurableAgent(
            agent_name="perf-agent",
            config=config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT_STAGE
    
    def test_iteration_strategy_affects_controller_type(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that different iteration strategies create different controller types."""
        from tarsy.agents.iteration_controllers.react_controller import (
            SimpleReActController,
        )
        from tarsy.agents.iteration_controllers.react_stage_controller import (
            ReactStageController,
        )
        
        # Create agent with REACT_STAGE strategy
        react_stage_config = AgentConfigModel(
            alert_types=["performance"],
            mcp_servers=["monitoring-tools"],
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        react_stage_agent = ConfigurableAgent(
            agent_name="react-stage-agent",
            config=react_stage_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Create agent with REACT strategy
        react_config = AgentConfigModel(
            alert_types=["security"],
            mcp_servers=["security-tools"],
            iteration_strategy=IterationStrategy.REACT
        )
        
        react_agent = ConfigurableAgent(
            agent_name="react-agent",
            config=react_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Verify different controller types
        assert isinstance(react_stage_agent._iteration_controller, ReactStageController)
        assert isinstance(react_agent._iteration_controller, SimpleReActController)
        
        # Verify strategies are correct
        assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE
        assert react_agent.iteration_strategy == IterationStrategy.REACT
    
    def test_config_property_includes_iteration_strategy(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that agent config property reflects the iteration strategy."""
        config = AgentConfigModel(
            alert_types=["security"],
            mcp_servers=["security-tools"],
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        agent = ConfigurableAgent(
            agent_name="test-agent",
            config=config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.config.iteration_strategy == IterationStrategy.REACT_STAGE 