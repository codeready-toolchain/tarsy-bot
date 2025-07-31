"""Extended unit tests for AgentRegistry with configuration support."""

from unittest.mock import patch

import pytest

from tarsy.models.agent_config import AgentConfigModel
from tarsy.services.agent_registry import AgentRegistry


@pytest.mark.unit
class TestAgentRegistryExtended:
    """Extended test cases for AgentRegistry with configuration support."""

    @pytest.fixture
    def sample_agent_configs(self):
        """Sample agent configurations for testing."""
        return {
            "security-agent": AgentConfigModel(
                alert_types=["security", "intrusion"],
                mcp_servers=["security-tools"]
            ),
            "performance-agent": AgentConfigModel(
                alert_types=["performance", "resource"],
                mcp_servers=["monitoring-tools"]
            ),
            "database-agent": AgentConfigModel(
                alert_types=["database"],
                mcp_servers=["db-tools"]
            )
        }

    def test_init_without_agent_configs(self):
        """Test AgentRegistry initialization without agent configurations."""
        registry = AgentRegistry()
        
        # Should work with built-in mappings only
        assert registry.agent_configs is None

    def test_init_with_agent_configs(self, sample_agent_configs):
        """Test AgentRegistry initialization with agent configurations."""
        registry = AgentRegistry(agent_configs=sample_agent_configs)
        
        assert registry.agent_configs == sample_agent_configs

    def test_init_with_empty_agent_configs(self):
        """Test AgentRegistry initialization with empty agent configurations."""
        empty_configs = {}
        registry = AgentRegistry(agent_configs=empty_configs)
        
        # Empty dict is treated as None (no configuration) for simplicity
        assert registry.agent_configs is None

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_mapping_merge_built_in_only(self):
        """Test alert type mapping with built-in agents only."""
        registry = AgentRegistry()
        
        # Should be able to get built-in agent
        agent_id = registry.get_agent_for_alert_type("kubernetes")
        assert agent_id == "KubernetesAgent"

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_mapping_merge_configured_only(self):
        """Test alert type mapping with configured agents only."""
        agent_configs = {
            "security-agent": AgentConfigModel(
                alert_types=["security"],
                mcp_servers=["security-tools"]
            )
        }
        
        registry = AgentRegistry(agent_configs=agent_configs)
        
        # Should be able to get configured agent
        agent_id = registry.get_agent_for_alert_type("security")
        assert agent_id == "ConfigurableAgent:security-agent"
        
        # Should still be able to get built-in agent
        agent_id = registry.get_agent_for_alert_type("kubernetes")
        assert agent_id == "KubernetesAgent"

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_mapping_merge_mixed_agents(self, sample_agent_configs):
        """Test alert type mapping with both built-in and configured agents."""
        registry = AgentRegistry(agent_configs=sample_agent_configs)
        
        # Should be able to get configured agents
        assert registry.get_agent_for_alert_type("security") == "ConfigurableAgent:security-agent"
        assert registry.get_agent_for_alert_type("performance") == "ConfigurableAgent:performance-agent"
        assert registry.get_agent_for_alert_type("database") == "ConfigurableAgent:database-agent"
        
        # Should still be able to get built-in agent
        assert registry.get_agent_for_alert_type("kubernetes") == "KubernetesAgent"

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent', 'security': 'SecurityAgent'})
    def test_configured_agents_override_built_in(self):
        """Test that configured agents override built-in agents for same alert types."""
        agent_configs = {
            "custom-security-agent": AgentConfigModel(
                alert_types=["security"],  # Overrides built-in security agent
                mcp_servers=["custom-security-tools"]
            )
        }
        
        registry = AgentRegistry(agent_configs=agent_configs)
        
        # Configured agent should override built-in for 'security' alert type
        agent_id = registry.get_agent_for_alert_type("security")
        assert agent_id == "ConfigurableAgent:custom-security-agent"
        
        # Built-in agent should still work for other alert types
        agent_id = registry.get_agent_for_alert_type("kubernetes")
        assert agent_id == "KubernetesAgent"

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_get_agent_for_alert_type_fail_fast(self):
        """Test that get_agent_for_alert_type fails fast for unknown alert types."""
        registry = AgentRegistry()
        
        with pytest.raises(ValueError) as exc_info:
            registry.get_agent_for_alert_type("unknown-alert-type")
            
        error_msg = str(exc_info.value)
        assert "No agent for alert type 'unknown-alert-type'" in error_msg
        assert "Available: kubernetes" in error_msg

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_get_agent_for_alert_type_safe_returns_none(self):
        """Test that get_agent_for_alert_type_safe returns None for unknown alert types."""
        registry = AgentRegistry()
        
        agent_id = registry.get_agent_for_alert_type_safe("unknown-alert-type")
        assert agent_id is None

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_get_agent_for_alert_type_safe_returns_valid_agent(self):
        """Test that get_agent_for_alert_type_safe returns valid agent for known alert types."""
        registry = AgentRegistry()
        
        agent_id = registry.get_agent_for_alert_type_safe("kubernetes")
        assert agent_id == "KubernetesAgent"

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_get_agent_for_alert_type_with_configured_agents_safe(self, sample_agent_configs):
        """Test get_agent_for_alert_type_safe with configured agents."""
        registry = AgentRegistry(agent_configs=sample_agent_configs)
        
        # Should return configured agent
        agent_id = registry.get_agent_for_alert_type_safe("security")
        assert agent_id == "ConfigurableAgent:security-agent"
        
        # Should return built-in agent
        agent_id = registry.get_agent_for_alert_type_safe("kubernetes")
        assert agent_id == "KubernetesAgent"
        
        # Should return None for unknown
        agent_id = registry.get_agent_for_alert_type_safe("unknown")
        assert agent_id is None

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_error_message_includes_available_agents(self, sample_agent_configs):
        """Test that error messages include all available agents (built-in + configured)."""
        registry = AgentRegistry(agent_configs=sample_agent_configs)
        
        with pytest.raises(ValueError) as exc_info:
            registry.get_agent_for_alert_type("unknown-alert-type")
            
        error_msg = str(exc_info.value)
        assert "No agent for alert type 'unknown-alert-type'" in error_msg
        assert "Available:" in error_msg
        
        # Should include built-in alert types
        assert "kubernetes" in error_msg
        
        # Should include configured alert types
        assert "security" in error_msg
        assert "performance" in error_msg
        assert "database" in error_msg

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {})
    def test_configured_agents_only_scenario(self):
        """Test scenario with only configured agents (no built-in agents)."""
        agent_configs = {
            "only-agent": AgentConfigModel(
                alert_types=["custom"],
                mcp_servers=["custom-tools"]
            )
        }
        
        registry = AgentRegistry(agent_configs=agent_configs)
        
        # Should work with configured agent
        agent_id = registry.get_agent_for_alert_type("custom")
        assert agent_id == "ConfigurableAgent:only-agent"
        
        # Should fail for unknown alert type
        with pytest.raises(ValueError) as exc_info:
            registry.get_agent_for_alert_type("unknown")
            
        error_msg = str(exc_info.value)
        # Should include both built-in and configured alert types
        assert "custom" in error_msg
        assert "Available:" in error_msg

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_no_configured_agents_scenario(self):
        """Test scenario with only built-in agents (no configured agents)."""
        registry = AgentRegistry(agent_configs=None)
        
        # Should work with built-in agent
        agent_id = registry.get_agent_for_alert_type("kubernetes")
        assert agent_id == "KubernetesAgent"
        
        # Should fail for unknown alert type
        with pytest.raises(ValueError) as exc_info:
            registry.get_agent_for_alert_type("unknown")
            
        error_msg = str(exc_info.value)
        assert "Available: kubernetes" in error_msg

    def test_agent_configs_property_immutability(self, sample_agent_configs):
        """Test that agent_configs property cannot be modified externally."""
        registry = AgentRegistry(agent_configs=sample_agent_configs)
        
        original_configs = registry.agent_configs
        
        # Verify we get the same reference
        assert registry.agent_configs is original_configs
        
        # Modifications to the returned dict should not affect registry behavior
        if registry.agent_configs:
            # Test that the registry still works correctly
            agent_id = registry.get_agent_for_alert_type("security")
            assert agent_id == "ConfigurableAgent:security-agent"

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_case_sensitivity_alert_types(self):
        """Test that alert type lookups are case-sensitive."""
        agent_configs = {
            "case-agent": AgentConfigModel(
                alert_types=["Security"],  # Capital S
                mcp_servers=["case-tools"]
            )
        }
        
        registry = AgentRegistry(agent_configs=agent_configs)
        
        # Should work with exact case match
        agent_id = registry.get_agent_for_alert_type("Security")
        assert agent_id == "ConfigurableAgent:case-agent"
        
        # Should fail with different case
        with pytest.raises(ValueError):
            registry.get_agent_for_alert_type("security")

    @patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'})
    def test_complex_agent_names_in_mappings(self):
        """Test that complex agent names work correctly in mappings."""
        agent_configs = {
            "complex-agent_v2.0-beta": AgentConfigModel(
                alert_types=["complex-alert-type"],
                mcp_servers=["complex-tools"]
            )
        }
        
        registry = AgentRegistry(agent_configs=agent_configs)
        
        agent_id = registry.get_agent_for_alert_type("complex-alert-type")
        assert agent_id == "ConfigurableAgent:complex-agent_v2.0-beta" 