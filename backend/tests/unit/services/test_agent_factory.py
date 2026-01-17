"""
Unit tests for AgentFactory - Agent creation with dependency injection.

Tests agent class registration, instantiation, dependency injection,
error handling, and validation of created agent instances.
"""

from unittest import mock
from unittest.mock import Mock, patch

import pytest

from tarsy.integrations.llm.manager import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.agent_execution_config import AgentExecutionConfig
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tests.utils import AgentServiceFactory


@pytest.mark.unit
class TestAgentFactoryInitialization:
    """Test AgentFactory initialization and registration."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies."""
        return AgentServiceFactory.create_mock_dependencies()
    
    def test_initialization_success(self, mock_dependencies):
        """Test successful AgentFactory initialization."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        assert factory.llm_manager == mock_dependencies['llm_manager']
        # mcp_client is no longer stored in factory - provided per agent creation
        assert factory.mcp_registry == mock_dependencies['mcp_registry']
        assert factory.agent_configs is None  # Default value
        assert isinstance(factory.static_agent_classes, dict)
        assert len(factory.static_agent_classes) >= 1  # At least KubernetesAgent
    
    def test_initialization_with_agent_configs(self, mock_dependencies):
        """Test initialization with agent configs."""
        mock_agent_configs = AgentServiceFactory.create_agent_configs()
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry'],
            agent_configs=mock_agent_configs
        )
        
        assert factory.agent_configs == mock_agent_configs
        assert factory.llm_manager == mock_dependencies['llm_manager']
        # mcp_client is no longer stored in factory - provided per agent creation
        assert factory.mcp_registry == mock_dependencies['mcp_registry']
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_agent_registration(self, mock_kubernetes_agent, mock_dependencies):
        """Test that agents are properly registered during initialization."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        # Verify KubernetesAgent is registered
        assert "KubernetesAgent" in factory.static_agent_classes
        assert factory.static_agent_classes["KubernetesAgent"] == mock_kubernetes_agent
    
    def test_agent_registry_immutable(self, mock_dependencies):
        """Test that agent registry is properly isolated between instances."""
        factory1 = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        factory2 = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        # Each factory should have its own registry instance
        assert factory1.static_agent_classes is not factory2.static_agent_classes
        # But they should have the same content
        assert factory1.static_agent_classes.keys() == factory2.static_agent_classes.keys()


@pytest.mark.unit
class TestAgentCreation:
    """Test agent creation and dependency injection."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies."""
        return AgentServiceFactory.create_mock_dependencies()
    
    @pytest.fixture
    def agent_factory(self, mock_dependencies):
        """Create AgentFactory with mocked dependencies."""
        return AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
    
    def test_create_kubernetes_agent_success(self, mock_dependencies):
        """Test successful creation of KubernetesAgent."""
        with patch('tarsy.agents.kubernetes_agent.KubernetesAgent') as mock_kubernetes_agent:
            mock_agent_instance = Mock()
            mock_kubernetes_agent.return_value = mock_agent_instance
            
            # Create factory after mocking
            agent_factory = AgentFactory(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_registry=mock_dependencies['mcp_registry']
            )
            
            agent = agent_factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
            
            # Verify agent class was called with correct dependencies
            mock_kubernetes_agent.assert_called_with(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_client=mock_dependencies['mcp_client'],
                mcp_registry=mock_dependencies['mcp_registry'],
                iteration_strategy=mock.ANY  # Accept any IterationStrategy enum value
            )
            
            # Verify correct instance returned
            assert agent == mock_agent_instance
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_create_agent_with_default_strategy(self, mock_kubernetes_agent, mock_dependencies):
        """Test agent creation with default iteration strategy."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        mock_agent_instance = Mock()
        mock_kubernetes_agent.return_value = mock_agent_instance
        
        agent = factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
        
        # Verify agent class was called with default iteration strategy
        from tarsy.models.constants import IterationStrategy
        mock_kubernetes_agent.assert_called_once_with(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_client=mock_dependencies['mcp_client'],
            mcp_registry=mock_dependencies['mcp_registry'],
            iteration_strategy=IterationStrategy.REACT  # Default strategy
        )
        
        assert agent == mock_agent_instance
    
    def test_create_unknown_agent_failure(self, agent_factory, mock_dependencies):
        """Test failure when trying to create unknown agent."""
        with pytest.raises(ValueError, match="Unknown agent 'UnknownAgent'"):
            agent_factory.create_agent("UnknownAgent", mock_dependencies['mcp_client'])
    
    def test_create_agent_case_sensitive(self, agent_factory, mock_dependencies):
        """Test that agent creation is case sensitive."""
        with pytest.raises(ValueError, match="Unknown agent 'kubernetesagent'"):
            agent_factory.create_agent("kubernetesagent", mock_dependencies['mcp_client'])
        
        with pytest.raises(ValueError, match="Unknown agent 'KUBERNETESAGENT'"):
            agent_factory.create_agent("KUBERNETESAGENT", mock_dependencies['mcp_client'])
    
    def test_create_agent_with_initialization_error(self, mock_dependencies):
        """Test handling of agent initialization errors."""
        with patch('tarsy.agents.kubernetes_agent.KubernetesAgent') as mock_kubernetes_agent:
            mock_kubernetes_agent.side_effect = Exception("Agent initialization failed")
            
            # Create factory after mocking
            agent_factory = AgentFactory(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_registry=mock_dependencies['mcp_registry']
            )
            
            with pytest.raises(Exception, match="Agent initialization failed"):
                agent_factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
    
    def test_multiple_agent_creation(self, mock_dependencies):
        """Test creating multiple agent instances."""
        with patch('tarsy.agents.kubernetes_agent.KubernetesAgent') as mock_kubernetes_agent:
            mock_agent1, mock_agent2 = AgentServiceFactory.create_mock_agent_instance(), AgentServiceFactory.create_mock_agent_instance()
            mock_kubernetes_agent.side_effect = [mock_agent1, mock_agent2]
            
            # Create factory after mocking
            agent_factory = AgentFactory(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_registry=mock_dependencies['mcp_registry']
            )
            
            agent1 = agent_factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
            agent2 = agent_factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
            
            # Each call should create a new instance
            assert agent1 == mock_agent1
            assert agent2 == mock_agent2
            assert agent1 is not agent2
            
            # Both should have been called with same dependencies
            assert mock_kubernetes_agent.call_count == 2
            for call in mock_kubernetes_agent.call_args_list:
                assert call[1]['llm_manager'] == mock_dependencies['llm_manager']
                assert call[1]['mcp_client'] == mock_dependencies['mcp_client']
                assert call[1]['mcp_registry'] == mock_dependencies['mcp_registry']
                # iteration_strategy should be present in all calls
                assert 'iteration_strategy' in call[1]


@pytest.mark.unit
class TestAgentFactoryRegistry:
    """Test agent registry functionality."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies."""
        return {
            'llm_manager': Mock(spec=LLMManager),
            'mcp_client': Mock(spec=MCPClient),
            'mcp_registry': Mock(spec=MCPServerRegistry)
        }
    
    def test_default_agent_registry(self, mock_dependencies):
        """Test that default agents are registered."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        # Verify default agents are present
        assert "KubernetesAgent" in factory.static_agent_classes
        
        # Verify the registry is a dictionary
        assert isinstance(factory.static_agent_classes, dict)
        
        # Verify all values are classes (not instances)
        for agent_name, agent_class in factory.static_agent_classes.items():
            assert callable(agent_class), f"{agent_name} should be a callable class"
    
    def test_agent_registry_contents(self, mock_dependencies):
        """Test the contents of the agent registry."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        # Should contain at least KubernetesAgent
        assert len(factory.static_agent_classes) >= 1
        
        # All agent names should be strings
        for agent_name in factory.static_agent_classes.keys():
            assert isinstance(agent_name, str)
            assert len(agent_name) > 0
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_registry_registration_called_once(self, mock_kubernetes_agent, mock_dependencies):
        """Test that agent registration happens during initialization."""
        # Import should be called during _register_available_agents
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        # The class should be in the registry
        assert factory.static_agent_classes["KubernetesAgent"] == mock_kubernetes_agent


@pytest.mark.unit 
class TestDependencyInjection:
    """Test dependency injection into agent instances."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies with specific characteristics."""
        llm_manager = Mock(spec=LLMManager)
        llm_manager.name = "test_llm_manager"
        
        mcp_client = Mock(spec=MCPClient)
        mcp_client.name = "test_mcp_client"
        
        mcp_registry = Mock(spec=MCPServerRegistry)
        mcp_registry.name = "test_mcp_registry"
        
        return {
            'llm_manager': llm_manager,
            'mcp_client': mcp_client,
            'mcp_registry': mcp_registry
        }
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_dependency_injection_all_parameters(self, mock_kubernetes_agent, mock_dependencies):
        """Test that all dependencies are correctly injected."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
        
        # Verify all dependencies were passed correctly
        from tarsy.models.constants import IterationStrategy
        mock_kubernetes_agent.assert_called_once_with(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_client=mock_dependencies['mcp_client'],
            mcp_registry=mock_dependencies['mcp_registry'],
            iteration_strategy=IterationStrategy.REACT
        )
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_dependency_injection_parameter_order(self, mock_kubernetes_agent, mock_dependencies):
        """Test that parameters are passed in correct order."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
        
        # Get the call arguments
        call_args = mock_kubernetes_agent.call_args
        
        # Verify keyword arguments are correct
        from tarsy.models.constants import IterationStrategy
        assert call_args[1]['llm_manager'] == mock_dependencies['llm_manager']
        assert call_args[1]['mcp_client'] == mock_dependencies['mcp_client']
        assert call_args[1]['mcp_registry'] == mock_dependencies['mcp_registry']
        assert call_args[1]['iteration_strategy'] == IterationStrategy.REACT
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_dependency_injection_with_agent_configs(self, mock_kubernetes_agent, mock_dependencies):
        """Test dependency injection with agent configs."""
        mock_configs = {'test-agent': Mock()}
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry'],
            agent_configs=mock_configs
        )
        
        factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
        
        # Verify factory stores agent configs
        assert factory.agent_configs == mock_configs
        
        # Verify agent is still created with correct parameters
        call_args = mock_kubernetes_agent.call_args
        from tarsy.models.constants import IterationStrategy
        assert call_args[1]['iteration_strategy'] == IterationStrategy.REACT
    
    def test_mcp_registry_requirement(self, mock_dependencies):
        """Test that mcp_registry is required parameter."""
        # This should work fine
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        assert factory.mcp_registry == mock_dependencies['mcp_registry']


@pytest.mark.unit
class TestAgentFactoryLogging:
    """Test logging functionality in AgentFactory."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies."""
        return {
            'llm_manager': Mock(spec=LLMManager),
            'mcp_client': Mock(spec=MCPClient),
            'mcp_registry': Mock(spec=MCPServerRegistry)
        }
    
    def test_initialization_logging(self, mock_dependencies, caplog):
        """Test that initialization logs correct information."""
        with caplog.at_level("INFO"):
            factory = AgentFactory(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_registry=mock_dependencies['mcp_registry']
            )
        
        # Should log number of registered agent classes
        log_messages = [record.message for record in caplog.records]
        agent_count_logs = [msg for msg in log_messages if "Initialized Agent Factory with" in msg]
        assert len(agent_count_logs) > 0
        
        # Should mention the number of agent classes
        factory_log = agent_count_logs[0]
        assert "agent classes" in factory_log
        assert str(len(factory.static_agent_classes)) in factory_log
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_agent_creation_logging(self, mock_kubernetes_agent, mock_dependencies, caplog):
        """Test that agent creation logs correct information."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        mock_agent_instance = Mock()
        mock_kubernetes_agent.return_value = mock_agent_instance
        
        with caplog.at_level("INFO"):
            factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
        
        # Should log agent creation
        log_messages = [record.message for record in caplog.records]
        creation_logs = [msg for msg in log_messages if "Created traditional agent instance" in msg]
        assert len(creation_logs) > 0
        
        creation_log = creation_logs[0]
        assert "KubernetesAgent" in creation_log


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies."""
        return {
            'llm_manager': Mock(spec=LLMManager),
            'mcp_client': Mock(spec=MCPClient),
            'mcp_registry': Mock(spec=MCPServerRegistry)
        }
    
    def test_empty_agent_name(self, mock_dependencies):
        """Test creation with empty agent name."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        with pytest.raises(ValueError, match="Unknown agent ''"):
            factory.create_agent("", mock_dependencies['mcp_client'])
    
    def test_none_agent_name(self, mock_dependencies):
        """Test creation with None agent name."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        with pytest.raises((ValueError, TypeError, AttributeError)):
            factory.create_agent(None, mock_dependencies['mcp_client'])
    
    def test_whitespace_agent_name(self, mock_dependencies):
        """Test creation with whitespace-only agent name."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        with pytest.raises(ValueError, match="Unknown agent '   '"):
            factory.create_agent("   ", mock_dependencies['mcp_client'])
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_agent_import_failure_handling(self, mock_kubernetes_agent, mock_dependencies):
        """Test that import failures are handled appropriately."""
        # This test verifies that if KubernetesAgent import fails,
        # the factory fails fast during initialization
        
        # Since we're patching the import, it should work fine
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        # Should have successfully registered the mocked agent
        assert "KubernetesAgent" in factory.static_agent_classes


@pytest.mark.unit
class TestAgentFactoryIterationStrategies:
    """Test AgentFactory with iteration strategy support."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies."""
        return {
            'llm_manager': Mock(spec=LLMManager),
            'mcp_client': Mock(spec=MCPClient),
            'mcp_registry': Mock(spec=MCPServerRegistry)
        }
    
    @pytest.fixture
    def sample_agent_configs(self):
        """Sample agent configurations with different iteration strategies."""
        from tarsy.models.agent_config import AgentConfigModel
        from tarsy.models.constants import IterationStrategy
        
        return {
            'react-stage-agent': AgentConfigModel(
                mcp_servers=['monitoring-server'],
                iteration_strategy=IterationStrategy.REACT_STAGE,
                custom_instructions='Use react stage processing'
            ),
            'react-agent': AgentConfigModel(
                mcp_servers=['security-server'],
                iteration_strategy=IterationStrategy.REACT,
                custom_instructions='Use ReAct reasoning'
            )
        }
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_create_kubernetes_agent_with_react_stage_strategy(self, mock_kubernetes_agent, mock_dependencies):
        """Test creating KubernetesAgent with REACT_STAGE iteration strategy."""
        from tarsy.models.constants import IterationStrategy
        
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        mock_agent_instance = Mock()
        mock_agent_instance.iteration_strategy = IterationStrategy.REACT_STAGE
        mock_kubernetes_agent.return_value = mock_agent_instance
        
        # Create agent - should use default REACT strategy
        agent = factory.create_agent("KubernetesAgent", mock_dependencies['mcp_client'])
        
        # Verify factory called agent with REACT strategy (default)
        mock_kubernetes_agent.assert_called_with(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_client=mock_dependencies['mcp_client'],
            mcp_registry=mock_dependencies['mcp_registry'],
            iteration_strategy=IterationStrategy.REACT  # Default
        )
        
        assert agent == mock_agent_instance
    
    def test_create_configurable_agent_with_react_stage_strategy(self, mock_dependencies, sample_agent_configs):
        """Test creating ConfigurableAgent with REACT_STAGE iteration strategy."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry'],
            agent_configs=sample_agent_configs
        )
        
        # Mock MCP registry to return server config
        mock_server_config = Mock()
        mock_server_config.server_id = 'monitoring-server'
        mock_dependencies['mcp_registry'].get_server_config.return_value = mock_server_config
        mock_dependencies['mcp_registry'].get_server_configs.return_value = [mock_server_config]
        
        agent = factory.create_agent("react-stage-agent", mock_dependencies['mcp_client'])
        
        from tarsy.agents.configurable_agent import ConfigurableAgent
        from tarsy.models.constants import IterationStrategy
        
        assert isinstance(agent, ConfigurableAgent)
        assert agent.iteration_strategy == IterationStrategy.REACT_STAGE
        assert agent.agent_name == "react-stage-agent"
    
    def test_create_configurable_agent_with_react_strategy(self, mock_dependencies, sample_agent_configs):
        """Test creating ConfigurableAgent with REACT iteration strategy."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry'],
            agent_configs=sample_agent_configs
        )
        
        # Mock MCP registry
        mock_server_config = Mock()
        mock_server_config.server_id = 'security-server'
        mock_dependencies['mcp_registry'].get_server_config.return_value = mock_server_config
        mock_dependencies['mcp_registry'].get_server_configs.return_value = [mock_server_config]
        
        agent = factory.create_agent("react-agent", mock_dependencies['mcp_client'])
        
        from tarsy.agents.configurable_agent import ConfigurableAgent
        from tarsy.models.constants import IterationStrategy
        
        assert isinstance(agent, ConfigurableAgent)
        assert agent.iteration_strategy == IterationStrategy.REACT
        assert agent.agent_name == "react-agent"
    
    def test_multiple_configurable_agents_different_strategies(self, mock_dependencies, sample_agent_configs):
        """Test creating multiple configurable agents with different strategies."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry'],
            agent_configs=sample_agent_configs
        )
        
        # Mock MCP registry for both servers
        def mock_get_server_config(server_id):
            config = Mock()
            config.server_id = server_id
            return config
        
        def mock_get_server_configs(server_ids):
            return [mock_get_server_config(sid) for sid in server_ids]
        
        mock_dependencies['mcp_registry'].get_server_config.side_effect = mock_get_server_config
        mock_dependencies['mcp_registry'].get_server_configs.side_effect = mock_get_server_configs
        
        # Create both agents
        react_stage_agent = factory.create_agent("react-stage-agent", mock_dependencies['mcp_client'])
        react_agent = factory.create_agent("react-agent", mock_dependencies['mcp_client'])
        
        from tarsy.models.constants import IterationStrategy
        
        # Verify different strategies
        assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE
        assert react_agent.iteration_strategy == IterationStrategy.REACT
        
        # Verify different configurations
        assert react_stage_agent.agent_name == "react-stage-agent"
        assert react_agent.agent_name == "react-agent"
        
        # Verify iteration strategies are correctly configured
        assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE
        assert react_agent.iteration_strategy == IterationStrategy.REACT
    
    def test_agent_factory_logging_includes_iteration_strategy(self, mock_dependencies, caplog):
        """Test that agent factory logging includes iteration strategy information."""
        from tarsy.models.agent_config import AgentConfigModel
        from tarsy.models.constants import IterationStrategy
        
        agent_configs = {
        'test-agent': AgentConfigModel(
            mcp_servers=['test-server'],
                iteration_strategy=IterationStrategy.REACT_STAGE
            )
        }
        
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry'],
            agent_configs=agent_configs
        )
        
        # Mock MCP registry
        mock_dependencies['mcp_registry'].get_server_config.return_value = Mock()
        mock_dependencies['mcp_registry'].get_server_configs.return_value = [Mock()]
        
        with caplog.at_level("INFO"):
            agent = factory.create_agent("test-agent", mock_dependencies['mcp_client'])
            
            from tarsy.agents.configurable_agent import ConfigurableAgent
            assert isinstance(agent, ConfigurableAgent)
            assert agent.agent_name == "test-agent"
        # Should log successful creation with strategy info
        log_messages = [record.message for record in caplog.records]
        creation_logs = [
            msg for msg in log_messages
            if "Created configured agent instance" in msg and "test-agent" in msg
        ]
        assert creation_logs, "Expected configured-agent creation log not found"


@pytest.mark.unit
class TestAgentFactoryErrorHandling:
    """Test error handling scenarios in agent creation."""
    
    @pytest.fixture
    def factory_with_mocks(self):
        """Create factory with all mocked dependencies."""
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        # Mock successful agent config loading
        agent_configs = {
            "test-agent": Mock(mcp_servers=["test-server"])
        }
        
        return {
            'factory': AgentFactory(llm_manager, mcp_registry, agent_configs),
            'mcp_client': mcp_client
        }
    
    def test_create_agent_unknown_agent(self, factory_with_mocks):
        """Test error when requesting unknown agent."""
        with pytest.raises(ValueError, match="Unknown agent 'nonexistent-agent'"):
            factory_with_mocks['factory'].create_agent("nonexistent-agent", factory_with_mocks['mcp_client'])
    
    def test_create_agent_missing_dependencies_llm(self):
        """Test error when LLM manager is missing."""
        factory = AgentFactory(
            llm_manager=None,  # Missing
            mcp_registry=Mock()
        )
        
        with pytest.raises(ValueError, match="Missing dependencies.*LLM manager is not initialized"):
            factory.create_agent("KubernetesAgent", Mock())
    
    def test_create_agent_missing_dependencies_mcp_registry(self):
        """Test error when MCP registry is missing."""
        factory = AgentFactory(
            llm_manager=Mock(),
            mcp_registry=None  # Missing
        )
        
        with pytest.raises(ValueError, match="Missing dependencies.*MCP registry is not initialized"):
            factory.create_agent("KubernetesAgent", Mock())
    
    def test_create_agent_multiple_missing_dependencies(self):
        """Test error message includes all missing dependencies."""
        factory = AgentFactory(
            llm_manager=None,
            mcp_registry=Mock()
        )
        
        with pytest.raises(ValueError) as exc_info:
            factory.create_agent("KubernetesAgent", Mock())
        
        error_message = str(exc_info.value)
        assert "LLM manager is not initialized" in error_message
    
    def test_create_configured_agent_missing_in_config(self, factory_with_mocks):
        """Test error when configured agent is not in agent_configs."""
        with pytest.raises(ValueError, match="Unknown configured agent 'missing-agent'"):
            factory_with_mocks['factory']._create_configured_agent("missing-agent", factory_with_mocks['mcp_client'])
    
    def test_create_configured_agent_mcp_server_validation_error(self):
        """Test error when configured agent references invalid MCP server."""
        llm_manager = Mock()
        mcp_client = Mock()
        
        # Mock MCP registry that raises error for unknown server
        mcp_registry = Mock()
        mcp_registry.get_server_config.side_effect = ValueError("Server 'invalid-server' not found")
        
        agent_config = Mock()
        agent_config.mcp_servers = ["invalid-server"]
        agent_configs = {"test-agent": agent_config}
        
        factory = AgentFactory(llm_manager, mcp_registry, agent_configs)
        
        with pytest.raises(ValueError) as exc_info:
            factory._create_configured_agent("test-agent", mcp_client)
        
        error_message = str(exc_info.value)
        assert "Dependency issues for configured agent 'test-agent'" in error_message
        assert "Server 'invalid-server' not found" in error_message
    
    def test_create_traditional_agent_constructor_error(self, factory_with_mocks):
        """Test handling of constructor errors in traditional agents."""
        # Mock agent class that raises TypeError in constructor
        mock_agent_class = Mock()
        mock_agent_class.side_effect = TypeError("Invalid constructor arguments")
        
        factory_with_mocks['factory'].static_agent_classes["ErrorAgent"] = mock_agent_class
        
        with pytest.raises(ValueError, match="Constructor error for 'ErrorAgent': Invalid constructor arguments"):
            factory_with_mocks['factory']._create_traditional_agent("ErrorAgent", factory_with_mocks['mcp_client'])
    
    def test_create_configured_agent_constructor_error(self):
        """Test handling of constructor errors in configured agents."""
        llm_manager = Mock()
        mcp_client = Mock() 
        mcp_registry = Mock()
        mcp_registry.get_server_config.return_value = Mock()  # Valid server config
        
        agent_config = Mock()
        agent_config.mcp_servers = ["test-server"]
        agent_configs = {"test-agent": agent_config}
        
        factory = AgentFactory(llm_manager, mcp_registry, agent_configs)
        
        # Mock ConfigurableAgent to raise TypeError
        with patch('tarsy.agents.configurable_agent.ConfigurableAgent') as mock_configurable:
            mock_configurable.side_effect = TypeError("Missing required argument")
            
            with pytest.raises(ValueError, match="Constructor error for configured agent 'test-agent': Missing required argument"):
                factory._create_configured_agent("test-agent", mcp_client)
    
    def test_create_traditional_agent_generic_error(self, factory_with_mocks):
        """Test handling of generic errors in traditional agent creation."""
        mock_agent_class = Mock()
        mock_agent_class.side_effect = Exception("Unexpected error during creation")
        
        factory_with_mocks['factory'].static_agent_classes["FailingAgent"] = mock_agent_class
        
        with pytest.raises(ValueError, match="Failed to create 'FailingAgent': Unexpected error during creation"):
            factory_with_mocks['factory']._create_traditional_agent("FailingAgent", factory_with_mocks['mcp_client'])
    
    def test_create_configured_agent_generic_error(self):
        """Test handling of generic errors in configured agent creation."""
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        mcp_registry.get_server_config.return_value = Mock()
        
        agent_config = Mock()
        agent_config.mcp_servers = ["test-server"]
        agent_configs = {"test-agent": agent_config}
        
        factory = AgentFactory(llm_manager, mcp_registry, agent_configs)
        
        with patch('tarsy.agents.configurable_agent.ConfigurableAgent') as mock_configurable:
            mock_configurable.side_effect = Exception("Unexpected configuration error")
            
            with pytest.raises(ValueError, match="Failed to create configured agent 'test-agent': Unexpected configuration error"):
                factory._create_configured_agent("test-agent", mcp_client)
    
    def test_load_builtin_agent_classes_import_error(self):
        """Test handling of import errors during agent class loading."""
        with patch('tarsy.config.builtin_config.get_builtin_agent_import_mapping') as mock_mapping, \
             patch('importlib.import_module') as mock_import:
            mock_mapping.return_value = {
                "NonExistentAgent": "nonexistent.module.NonExistentAgent"
            }
            mock_import.side_effect = ImportError("No module named 'nonexistent'")
            
            with pytest.raises(ValueError, match="Built-in agent '.*' could not be loaded"):
                AgentFactory(Mock(), Mock())
    
    def test_load_builtin_agent_classes_attribute_error(self):
        """Test handling of attribute errors during agent class loading.""" 
        with patch('tarsy.services.agent_factory.get_builtin_agent_import_mapping') as mock_mapping:
            # Use a real module path that will import successfully but has no such attribute
            mock_mapping.return_value = {
                "MissingClassAgent": "tarsy.utils.logger.NonExistentClass"
            }
            
            with pytest.raises(ValueError, match="Built-in agent '.*' could not be loaded"):
                AgentFactory(Mock(), Mock())
    
    def test_legacy_format_handling_success(self):
        """Test successful legacy format handling."""
        llm_manager = Mock()
        mcp_client = Mock()
        mcp_registry = Mock()
        
        agent_config = Mock()
        agent_config.mcp_servers = ["test-server"]
        mcp_registry.get_server_config.return_value = Mock()
        agent_configs = {"legacy-agent": agent_config}
        
        factory = AgentFactory(llm_manager, mcp_registry, agent_configs)
        
        with patch('tarsy.agents.configurable_agent.ConfigurableAgent') as mock_configurable:
            mock_agent = Mock()
            mock_configurable.return_value = mock_agent
            
            # Test legacy format
            result = factory.create_agent("legacy-agent", mcp_client)
            
            assert result == mock_agent
            mock_configurable.assert_called_once()
    
    def test_legacy_format_unknown_agent(self, factory_with_mocks):
        """Test legacy format with unknown agent."""
        with pytest.raises(ValueError, match="Unknown agent 'unknown-legacy'"):
            factory_with_mocks['factory'].create_agent("unknown-legacy", factory_with_mocks['mcp_client'])


@pytest.mark.unit
class TestAgentFactoryValidation:
    """Test validation scenarios in agent factory."""
    
    def test_validate_dependencies_all_present(self):
        """Test validation passes when all dependencies are present."""
        llm_manager = Mock()
        mcp_registry = Mock()
        
        agent_configs = {"test-agent": Mock(mcp_servers=["test-server"])}
        factory = AgentFactory(llm_manager, mcp_registry, agent_configs)
        mcp_registry.get_server_config.return_value = Mock()  # Mock valid server config
        
        # Should not raise any errors
        factory._validate_dependencies_for_traditional_agent("TestAgent")
        factory._validate_dependencies_for_configured_agent("test-agent")
    
    def test_configured_agent_validation_with_valid_servers(self):
        """Test configured agent validation with valid MCP servers."""
        llm_manager = Mock()
        mcp_registry = Mock()
        mcp_registry.get_server_config.return_value = Mock()  # Valid config
        
        agent_config = Mock()
        agent_config.mcp_servers = ["valid-server", "another-server"]
        agent_configs = {"test-agent": agent_config}
        
        factory = AgentFactory(llm_manager, mcp_registry, agent_configs)
        
        # Should validate all servers without errors
        factory._validate_dependencies_for_configured_agent("test-agent")
        
        # Verify all servers were checked
        assert mcp_registry.get_server_config.call_count == 2
        mcp_registry.get_server_config.assert_any_call("valid-server")
        mcp_registry.get_server_config.assert_any_call("another-server")


@pytest.mark.unit
class TestAgentFactoryLLMProvider:
    """Test AgentFactory LLM provider override functionality."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AgentFactory dependencies."""
        return {
            'llm_manager': Mock(spec=LLMManager),
            'mcp_client': Mock(spec=MCPClient),
            'mcp_registry': Mock(spec=MCPServerRegistry)
        }
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_get_agent_without_provider(self, mock_kubernetes_agent, mock_dependencies):
        """Test get_agent_with_config without LLM provider uses default."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        mock_agent_instance = Mock()
        mock_agent_instance.set_llm_provider = Mock()
        mock_kubernetes_agent.return_value = mock_agent_instance
        
        agent = factory.get_agent_with_config(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_dependencies['mcp_client'],
            execution_config=AgentExecutionConfig()
        )
        
        # Should not call set_llm_provider when no provider is specified
        mock_agent_instance.set_llm_provider.assert_not_called()
        assert agent == mock_agent_instance
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_get_agent_with_provider(self, mock_kubernetes_agent, mock_dependencies):
        """Test get_agent_with_config with LLM provider override."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        mock_agent_instance = Mock()
        mock_agent_instance.set_llm_provider = Mock()
        mock_kubernetes_agent.return_value = mock_agent_instance
        
        agent = factory.get_agent_with_config(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_dependencies['mcp_client'],
            execution_config=AgentExecutionConfig(llm_provider="google-default")
        )
        
        # Should call set_llm_provider with the specified provider
        mock_agent_instance.set_llm_provider.assert_called_once_with("google-default")
        assert agent == mock_agent_instance
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_get_agent_with_provider_and_strategy(self, mock_kubernetes_agent, mock_dependencies):
        """Test get_agent_with_config with both LLM provider and iteration strategy overrides."""
        from tarsy.models.constants import IterationStrategy
        
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        mock_agent_instance = Mock()
        mock_agent_instance.set_llm_provider = Mock()
        mock_agent_instance.set_iteration_strategy = Mock()
        mock_kubernetes_agent.return_value = mock_agent_instance
        
        agent = factory.get_agent_with_config(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_dependencies['mcp_client'],
            execution_config=AgentExecutionConfig(
                iteration_strategy="react-stage",
                llm_provider="openai-default"
            )
        )
        
        # Both should be called
        mock_agent_instance.set_iteration_strategy.assert_called_once_with(IterationStrategy.REACT_STAGE)
        mock_agent_instance.set_llm_provider.assert_called_once_with("openai-default")
        assert agent == mock_agent_instance
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_get_agent_with_none_provider(self, mock_kubernetes_agent, mock_dependencies):
        """Test get_agent_with_config with explicit None provider (uses global default)."""
        factory = AgentFactory(
            llm_manager=mock_dependencies['llm_manager'],
            mcp_registry=mock_dependencies['mcp_registry']
        )
        
        mock_agent_instance = Mock()
        mock_agent_instance.set_llm_provider = Mock()
        mock_kubernetes_agent.return_value = mock_agent_instance
        
        agent = factory.get_agent_with_config(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_dependencies['mcp_client'],
            execution_config=AgentExecutionConfig(llm_provider=None)
        )
        
        # Should not call set_llm_provider when None is explicitly passed
        mock_agent_instance.set_llm_provider.assert_not_called()
        assert agent == mock_agent_instance
    
    def test_get_agent_provider_logging(self, mock_dependencies, caplog):
        """Test that provider override is logged."""
        with patch('tarsy.agents.kubernetes_agent.KubernetesAgent') as mock_kubernetes_agent:
            factory = AgentFactory(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_registry=mock_dependencies['mcp_registry']
            )
            
            mock_agent_instance = Mock()
            mock_agent_instance.set_llm_provider = Mock()
            mock_kubernetes_agent.return_value = mock_agent_instance
            
            with caplog.at_level("DEBUG"):
                factory.get_agent_with_config(
                    agent_identifier="KubernetesAgent",
                    mcp_client=mock_dependencies['mcp_client'],
                    execution_config=AgentExecutionConfig(llm_provider="gemini-flash")
                )
            
            # Should log the provider override
            log_messages = [record.message for record in caplog.records]
            provider_logs = [msg for msg in log_messages if "gemini-flash" in msg and "LLM provider" in msg]
            assert len(provider_logs) > 0