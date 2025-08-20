"""
Unit tests for AgentRegistry - Maps alert types to agent classes.

Tests alert type to agent class mapping, registry initialization,
lookups, supported types, and edge case handling.
"""


from unittest.mock import patch

import pytest

from tarsy.services.agent_registry import (
    AgentRegistry,
    _extract_alert_type_mappings_from_chains,
)
from tests.utils import AgentFactory


@pytest.mark.unit
class TestAgentRegistryInitialization:
    """Test AgentRegistry initialization with different configurations."""
    
    @pytest.mark.parametrize("scenario,config,expected_behavior", [
        ("default_mappings", None, "default"),  # Default mappings
        ("custom_config", AgentFactory.create_custom_mappings(), "custom"),  # Custom configuration
        ("empty_config", {}, "default"),  # Empty config falls back to defaults
    ])
    def test_initialization_scenarios(self, scenario, config, expected_behavior):
        """Test initialization for various configuration scenarios."""
        registry = AgentRegistry(config=config)
        
        if expected_behavior == "default":
            # Should have default mappings
            assert isinstance(registry.static_mappings, dict)
            assert len(registry.static_mappings) >= 1
            assert "NamespaceTerminating" in registry.static_mappings
            assert registry.static_mappings["NamespaceTerminating"] == "KubernetesAgent"
        else:
            # Should use custom configuration
            assert registry.static_mappings == config
            assert "CustomAlert" in registry.static_mappings
            assert "AnotherAlert" in registry.static_mappings
            assert "NamespaceTerminating" not in registry.static_mappings
    
    def test_static_mappings_isolation(self):
        """Test that different registry instances have isolated mappings."""
        registry1 = AgentRegistry()
        registry2 = AgentRegistry()
        
        # Should be separate instances
        assert registry1.static_mappings is not registry2.static_mappings
        
        # But should have same content
        assert registry1.static_mappings == registry2.static_mappings
    
    def test_initialization_preserves_config_reference(self):
        """Test that registry uses the provided config directly (implementation behavior)."""
        external_config = {"TestAlert": "TestAgent"}
        registry = AgentRegistry(config=external_config)
        
        # Modify external config
        external_config["NewAlert"] = "NewAgent"
        
        # Registry IS affected because it uses direct reference
        assert "NewAlert" in registry.static_mappings
        assert len(registry.static_mappings) == 2


@pytest.mark.unit
class TestAgentLookup:
    """Test core agent lookup functionality."""
    
    @pytest.fixture
    def sample_registry(self):
        """Create a registry with known mappings for testing."""
        return AgentRegistry(config=AgentFactory.create_default_mappings())
    
    @pytest.mark.parametrize("alert_type,expected_agent,should_raise", [
        ("NamespaceTerminating", "KubernetesAgent", False),
        ("PodCrash", "KubernetesAgent", False),
        ("HighCPU", "MonitoringAgent", False),
        ("DiskFull", "SystemAgent", False),
        ("UnknownAlert", None, True),
        ("NonExistentAlert", None, True),
        ("RandomType", None, True),
    ])
    def test_get_agent_scenarios(self, sample_registry, alert_type, expected_agent, should_raise):
        """Test getting agent for various alert type scenarios."""
        if should_raise:
            with pytest.raises(ValueError, match=f"No agent for alert type '{alert_type}'"):
                sample_registry.get_agent_for_alert_type(alert_type)
        else:
            assert sample_registry.get_agent_for_alert_type(alert_type) == expected_agent
    
    @pytest.mark.parametrize("alert_type,should_raise", [
        ("NamespaceTerminating", False),  # Exact case should work
        ("namespaceterminating", True),  # Different case should fail
        ("NAMESPACETERMINATING", True),  # Different case should fail
        ("namespaceTerminating", True),  # Different case should fail
        (" NamespaceTerminating", True),  # Leading whitespace should fail
        ("NamespaceTerminating ", True),  # Trailing whitespace should fail
        (" NamespaceTerminating ", True),  # Both whitespace should fail
        ("", True),  # Empty string should fail
        (None, True),  # None should fail
    ])
    def test_get_agent_input_validation(self, sample_registry, alert_type, should_raise):
        """Test agent lookup with various input validation scenarios."""
        if should_raise:
            with pytest.raises(ValueError, match=f"No agent for alert type '{alert_type}'"):
                sample_registry.get_agent_for_alert_type(alert_type)
        else:
            assert sample_registry.get_agent_for_alert_type(alert_type) == "KubernetesAgent"
    
    def test_multiple_alert_types_same_agent(self, sample_registry):
        """Test multiple alert types mapping to same agent."""
        # Both should map to KubernetesAgent
        assert sample_registry.get_agent_for_alert_type("NamespaceTerminating") == "KubernetesAgent"
        assert sample_registry.get_agent_for_alert_type("PodCrash") == "KubernetesAgent"
        
        # Should be the same agent class name
        agent1 = sample_registry.get_agent_for_alert_type("NamespaceTerminating")
        agent2 = sample_registry.get_agent_for_alert_type("PodCrash")
        assert agent1 == agent2


@pytest.mark.unit
class TestSupportedAlertTypes:
    """Test supported alert types functionality."""
    
    @pytest.fixture
    def sample_registry(self):
        """Create a registry with known mappings for testing."""
        return AgentRegistry(config=AgentFactory.create_default_mappings())
    
    def test_get_supported_alert_types_returns_all_keys(self, sample_registry):
        """Test that get_supported_alert_types returns all registered types."""
        supported_types = sample_registry.get_supported_alert_types()
        
        expected_types = ["NamespaceTerminating", "PodCrash", "HighCPU", "DiskFull"]
        assert set(supported_types) == set(expected_types)
        assert len(supported_types) == 4
    
    def test_get_supported_alert_types_returns_list(self, sample_registry):
        """Test that get_supported_alert_types returns a list."""
        supported_types = sample_registry.get_supported_alert_types()
        assert isinstance(supported_types, list)
    
    def test_get_supported_alert_types_truly_empty_registry(self):
        """Test get_supported_alert_types with truly empty registry."""
        # Create registry with defaults first, then clear it
        registry = AgentRegistry()
        registry.static_mappings.clear()  # Make it truly empty
        supported_types = registry.get_supported_alert_types()
        
        assert isinstance(supported_types, list)
        assert len(supported_types) == 0
        assert supported_types == []
    
    def test_get_supported_alert_types_immutable(self, sample_registry):
        """Test that modifying returned list doesn't affect registry."""
        supported_types = sample_registry.get_supported_alert_types()
        original_length = len(supported_types)
        
        # Modify the returned list
        supported_types.append("NewAlertType")
        
        # Registry should not be affected
        new_supported_types = sample_registry.get_supported_alert_types()
        assert len(new_supported_types) == original_length
        assert "NewAlertType" not in new_supported_types
    
    def test_get_supported_alert_types_order_consistency(self, sample_registry):
        """Test that supported types order is consistent."""
        types1 = sample_registry.get_supported_alert_types()
        types2 = sample_registry.get_supported_alert_types()
        
        # Should return same elements (though order may vary)
        assert set(types1) == set(types2)


@pytest.mark.unit
class TestDefaultMappings:
    """Test default mapping configuration."""
    
    def test_default_mappings_contain_kubernetes_agent(self):
        """Test that default mappings include KubernetesAgent."""
        registry = AgentRegistry()
        
        # Should have NamespaceTerminating -> KubernetesAgent
        assert "NamespaceTerminating" in registry.static_mappings
        assert registry.static_mappings["NamespaceTerminating"] == "KubernetesAgent"
    
    def test_default_mappings_structure(self):
        """Test the structure of default mappings."""
        registry = AgentRegistry()
        
        # All keys should be strings
        for alert_type in registry.static_mappings.keys():
            assert isinstance(alert_type, str)
            assert len(alert_type) > 0
        
        # All values should be strings
        for agent_class in registry.static_mappings.values():
            assert isinstance(agent_class, str)
            assert len(agent_class) > 0
    
    def test_default_mappings_not_empty(self):
        """Test that default mappings are not empty."""
        registry = AgentRegistry()
        
        assert len(registry.static_mappings) > 0
        assert registry.static_mappings  # Truthy check
    
    def test_access_to_default_mappings_class_constant(self):
        """Test that _DEFAULT_MAPPINGS class constant exists and is accessible."""
        # Should be able to access the class constant
        assert hasattr(AgentRegistry, '_DEFAULT_MAPPINGS')
        assert isinstance(AgentRegistry._DEFAULT_MAPPINGS, dict)
        assert "NamespaceTerminating" in AgentRegistry._DEFAULT_MAPPINGS


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    @pytest.mark.parametrize("config_type,config,test_cases", [
        ("special_chars", {
            "Alert-With-Dashes": "DashAgent",
            "Alert_With_Underscores": "UnderscoreAgent",
            "Alert.With.Dots": "DotAgent",
            "Alert/With/Slashes": "SlashAgent",
            "Alert With Spaces": "SpaceAgent"
        }, [
            ("Alert-With-Dashes", "DashAgent"),
            ("Alert_With_Underscores", "UnderscoreAgent"),
            ("Alert.With.Dots", "DotAgent"),
            ("Alert/With/Slashes", "SlashAgent"),
            ("Alert With Spaces", "SpaceAgent")
        ]),
        ("numeric", {
            "Alert123": "NumericAgent",
            "123Alert": "LeadingNumericAgent",
            "Alert-2024": "YearAgent"
        }, [
            ("Alert123", "NumericAgent"),
            ("123Alert", "LeadingNumericAgent"),
            ("Alert-2024", "YearAgent")
        ]),
        ("unicode", {
            "AlertWithÜnicode": "UnicodeAgent",
            "Alert🚨Emergency": "EmojiAgent"
        }, [
            ("AlertWithÜnicode", "UnicodeAgent"),
            ("Alert🚨Emergency", "EmojiAgent")
        ]),
    ])
    def test_registry_edge_cases(self, config_type, config, test_cases):
        """Test registry with various edge case configurations."""
        registry = AgentRegistry(config=config)
        
        for alert_type, expected_agent in test_cases:
            assert registry.get_agent_for_alert_type(alert_type) == expected_agent
    
    def test_registry_with_very_long_names(self):
        """Test registry with very long alert type and agent names."""
        long_alert_type = "VeryLongAlertTypeName" * 10  # 200+ characters
        long_agent_name = "VeryLongAgentClassName" * 10  # 200+ characters
        
        long_config = {long_alert_type: long_agent_name}
        registry = AgentRegistry(config=long_config)
        
        assert registry.get_agent_for_alert_type(long_alert_type) == long_agent_name
    
    def test_registry_with_empty_string_keys_or_values(self):
        """Test registry behavior with empty string keys or values."""
        empty_config = {
            "": "EmptyKeyAgent",
            "EmptyValueAlert": ""
        }
        
        registry = AgentRegistry(config=empty_config)
        
        # Should handle empty strings
        assert registry.get_agent_for_alert_type("") == "EmptyKeyAgent"
        assert registry.get_agent_for_alert_type("EmptyValueAlert") == ""
    
    @pytest.mark.parametrize("invalid_input,expected_exception", [
        (123, ValueError),  # Hashable non-string
        (True, ValueError),  # Hashable non-string
        (False, ValueError),  # Hashable non-string
        ([], TypeError),  # Unhashable input
        ({}, TypeError),  # Unhashable input
    ])
    def test_get_agent_with_non_string_input(self, invalid_input, expected_exception):
        """Test get_agent_for_alert_type with non-string inputs."""
        registry = AgentRegistry()
        
        with pytest.raises(expected_exception):
            registry.get_agent_for_alert_type(invalid_input)


@pytest.mark.unit
class TestRegistryLogging:
    """Test logging functionality in AgentRegistry."""
    
    def test_initialization_logging(self, caplog):
        """Test that initialization logs correct information."""
        with caplog.at_level("INFO"):
            registry = AgentRegistry()
        
        # Should log number of mappings
        log_messages = [record.message for record in caplog.records]
        registry_logs = [msg for msg in log_messages if "Initialized Agent Registry with" in msg]
        assert len(registry_logs) > 0
        
        # Should mention the number of mappings
        registry_log = registry_logs[0]
        assert "mappings" in registry_log
        assert str(len(registry.static_mappings)) in registry_log
    
    def test_initialization_logging_with_custom_config(self, caplog):
        """Test logging with custom configuration."""
        custom_config = {"Alert1": "Agent1", "Alert2": "Agent2"}
        
        with caplog.at_level("INFO"):
            registry = AgentRegistry(config=custom_config)
        
        # Should log correct count
        log_messages = [record.message for record in caplog.records]
        registry_logs = [msg for msg in log_messages if "Initialized Agent Registry with" in msg]
        assert len(registry_logs) > 0
        
        registry_log = registry_logs[0]
        assert "2 total mappings" in registry_log
    
    def test_initialization_logging_with_empty_config(self, caplog):
        """Test logging with empty configuration (falls back to defaults)."""
        with caplog.at_level("INFO"):
            registry = AgentRegistry(config={})
        
        # Should log default mappings count (since empty dict falls back to defaults)
        log_messages = [record.message for record in caplog.records]
        registry_logs = [msg for msg in log_messages if "Initialized Agent Registry with" in msg]
        assert len(registry_logs) > 0
        
        registry_log = registry_logs[0]
        assert str(len(registry.static_mappings)) + " total mappings" in registry_log


@pytest.mark.unit
class TestDuplicateDetectionInChainMappings:
    """Test duplicate detection functionality in chain-based mappings."""
    
    @pytest.fixture
    def mock_chain_definitions_with_duplicates(self):
        """Mock chain definitions that contain duplicate alert type mappings."""
        return {
            "chain1": {
                "alert_types": ["AlertA", "AlertB"],
                "stages": [{"agent": "AgentX"}]
            },
            "chain2": {
                "alert_types": ["AlertB", "AlertC"],  # AlertB is duplicate
                "stages": [{"agent": "AgentY"}]  # Different agent
            },
            "chain3": {
                "alert_types": ["AlertC"],  # AlertC is duplicate
                "stages": [{"agent": "AgentY"}]  # Same agent as chain2
            }
        }
    
    @pytest.fixture
    def mock_chain_definitions_no_duplicates(self):
        """Mock chain definitions without any duplicates."""
        return {
            "chain1": {
                "alert_types": ["AlertA", "AlertB"],
                "stages": [{"agent": "AgentX"}]
            },
            "chain2": {
                "alert_types": ["AlertC", "AlertD"],
                "stages": [{"agent": "AgentY"}]
            }
        }
    
    @patch("tarsy.services.agent_registry.BUILTIN_CHAIN_DEFINITIONS")
    def test_extract_mappings_with_duplicate_conflicts(self, mock_chain_defs, mock_chain_definitions_with_duplicates, caplog):
        """Test that duplicate mappings with different agents are detected and logged."""
        mock_chain_defs.items.return_value = mock_chain_definitions_with_duplicates.items()
        
        with caplog.at_level("WARNING"):
            mappings = _extract_alert_type_mappings_from_chains()
        
        # Should have first-wins behavior
        assert mappings["AlertA"] == "AgentX"
        assert mappings["AlertB"] == "AgentX"  # First definition wins
        assert mappings["AlertC"] == "AgentY"  # First definition wins
        
        # Check warning logs
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_logs) >= 1
        
        # Should warn about AlertB conflict
        alertb_warnings = [log for log in warning_logs if "AlertB" in log.message]
        assert len(alertb_warnings) == 1
        
        warning_msg = alertb_warnings[0].message
        assert "Alert type 'AlertB' mapping conflict detected!" in warning_msg
        assert "Existing agent: 'AgentX'" in warning_msg
        assert "New agent: 'AgentY'" in warning_msg
        assert "from chain 'chain2'" in warning_msg
        assert "Keeping existing mapping" in warning_msg
    
    @patch("tarsy.services.agent_registry.BUILTIN_CHAIN_DEFINITIONS")
    def test_extract_mappings_with_consistent_duplicates(self, mock_chain_defs, mock_chain_definitions_with_duplicates, caplog):
        """Test that duplicate mappings with same agent are logged as debug."""
        mock_chain_defs.items.return_value = mock_chain_definitions_with_duplicates.items()
        
        with caplog.at_level("DEBUG"):
            mappings = _extract_alert_type_mappings_from_chains()
        
        # Check debug logs for consistent duplicates (AlertC appears in both chain2 and chain3 with same agent)
        debug_logs = [record for record in caplog.records if record.levelname == "DEBUG"]
        alertc_debug_logs = [log for log in debug_logs if "AlertC" in log.message and "duplicate but consistent" in log.message]
        assert len(alertc_debug_logs) == 1
        
        debug_msg = alertc_debug_logs[0].message
        assert "already mapped to same agent 'AgentY'" in debug_msg
        assert "from chain 'chain3'" in debug_msg
    
    @patch("tarsy.services.agent_registry.BUILTIN_CHAIN_DEFINITIONS")
    def test_extract_mappings_without_duplicates_no_warnings(self, mock_chain_defs, mock_chain_definitions_no_duplicates, caplog):
        """Test that no warnings are logged when there are no duplicates."""
        mock_chain_defs.items.return_value = mock_chain_definitions_no_duplicates.items()
        
        with caplog.at_level("WARNING"):
            mappings = _extract_alert_type_mappings_from_chains()
        
        # Should map all alerts correctly
        assert mappings["AlertA"] == "AgentX"
        assert mappings["AlertB"] == "AgentX"
        assert mappings["AlertC"] == "AgentY"
        assert mappings["AlertD"] == "AgentY"
        
        # No warnings should be logged
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_logs) == 0
    
    @patch("tarsy.services.agent_registry.BUILTIN_CHAIN_DEFINITIONS")
    def test_extract_mappings_handles_edge_cases(self, mock_chain_defs, caplog):
        """Test edge cases in chain definitions."""
        edge_case_chains = {
            "empty_alert_types": {
                "alert_types": [],
                "stages": [{"agent": "AgentX"}]
            },
            "no_stages": {
                "alert_types": ["AlertA"],
                "stages": []
            },
            "no_agent_in_stage": {
                "alert_types": ["AlertB"],
                "stages": [{}]
            },
            "missing_agent_key": {
                "alert_types": ["AlertC"],
                "stages": [{"other_key": "value"}]
            }
        }
        mock_chain_defs.items.return_value = edge_case_chains.items()
        
        with caplog.at_level("DEBUG"):
            mappings = _extract_alert_type_mappings_from_chains()
        
        # Should result in empty mappings due to edge cases
        assert len(mappings) == 0


@pytest.mark.unit
class TestDuplicateDetectionInConfiguredAgents:
    """Test duplicate detection in configured agent mappings."""
    
    @pytest.fixture
    def mock_agent_configs_with_duplicates(self):
        """Mock agent configurations with overlapping alert types."""
        from types import SimpleNamespace
        
        agent1 = SimpleNamespace()
        agent1.alert_types = ["AlertA", "AlertB"]
        
        agent2 = SimpleNamespace()
        agent2.alert_types = ["AlertB", "AlertC"]  # AlertB is duplicate
        
        agent3 = SimpleNamespace()
        agent3.alert_types = ["AlertC"]  # AlertC is duplicate
        
        return {
            "security-agent": agent1,
            "monitoring-agent": agent2,
            "backup-agent": agent3
        }
    
    def test_configured_mappings_duplicate_detection(self, mock_agent_configs_with_duplicates, caplog):
        """Test duplicate detection in configured agent mappings."""
        registry = AgentRegistry()
        
        with caplog.at_level("WARNING"):
            configured_mappings = registry._create_configured_mappings(mock_agent_configs_with_duplicates)
        
        # Should use first-wins behavior (without ConfigurableAgent prefix)
        assert configured_mappings["AlertA"] == "security-agent"
        assert configured_mappings["AlertB"] == "security-agent"  # First wins
        assert configured_mappings["AlertC"] == "monitoring-agent"  # First wins
        
        # Check warning logs
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_logs) >= 1
        
        # Should warn about AlertB conflict
        alertb_warnings = [log for log in warning_logs if "AlertB" in log.message]
        assert len(alertb_warnings) == 1
        
        warning_msg = alertb_warnings[0].message
        assert "Alert type 'AlertB' mapping conflict detected!" in warning_msg
        assert "Existing agent: 'security-agent'" in warning_msg
        assert "New agent: 'monitoring-agent'" in warning_msg
    
    def test_configured_mappings_shows_conflicts(self, caplog):
        """Test that configured agent mappings properly detect and log conflicts."""
        from types import SimpleNamespace
        
        agent1 = SimpleNamespace()
        agent1.alert_types = ["AlertA", "AlertB"]
        
        agent2 = SimpleNamespace()
        agent2.alert_types = ["AlertB", "AlertC"]  # AlertB conflicts with agent1
        
        agent_configs = {
            "security-agent": agent1,
            "monitoring-agent": agent2  # Different agent name, so conflict expected for AlertB
        }
        
        registry = AgentRegistry()
        
        with caplog.at_level("WARNING"):
            configured_mappings = registry._create_configured_mappings(agent_configs)
        
        # Should show conflict warning for AlertB
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        alertb_warnings = [log for log in warning_logs if "AlertB" in log.message and "conflict detected" in log.message]
        assert len(alertb_warnings) == 1
        
        # Final mapping should use first-wins behavior (without ConfigurableAgent prefix)
        assert configured_mappings["AlertA"] == "security-agent"
        assert configured_mappings["AlertB"] == "security-agent"  # First wins
        assert configured_mappings["AlertC"] == "monitoring-agent"


@pytest.mark.unit
class TestRegistryDuplicateDetectionIntegration:
    """Test duplicate detection across different mapping sources."""
    
    def test_configured_agents_override_behavior(self, caplog):
        """Test interaction between default mappings and configured agents."""
        # Create configured agents with overlapping alert types
        from types import SimpleNamespace
        agent_config = SimpleNamespace()
        # Use an alert type that might overlap with built-in mappings
        agent_config.alert_types = ["NamespaceTerminating", "CustomAlert"]  
        
        agent_configs = {
            "custom-agent": agent_config
        }
        
        with caplog.at_level("INFO"):
            registry = AgentRegistry(agent_configs=agent_configs)
        
        # The registry should contain both default mappings and configured agent mappings
        # Configured agents should override default mappings via .update() call
        assert "NamespaceTerminating" in registry.static_mappings
        assert "CustomAlert" in registry.static_mappings
        assert registry.static_mappings["NamespaceTerminating"] == "custom-agent"  # Override happens (without prefix)
        assert registry.static_mappings["CustomAlert"] == "custom-agent"
        
        # The registry should show appropriate logging
        info_logs = [record for record in caplog.records if record.levelname == "INFO"]
        configured_agent_logs = [log for log in info_logs if "configured agent mappings" in log.message]
        assert len(configured_agent_logs) >= 1
    
    def test_first_wins_behavior_consistency(self, caplog):
        """Test that first-wins behavior is consistent across all mapping sources."""
        from types import SimpleNamespace
        
        # Mock multiple agent configs with same alert type
        agent1 = SimpleNamespace()
        agent1.alert_types = ["DuplicateAlert"]
        
        agent2 = SimpleNamespace() 
        agent2.alert_types = ["DuplicateAlert"]
        
        agent3 = SimpleNamespace()
        agent3.alert_types = ["DuplicateAlert"]
        
        agent_configs = {
            "first-agent": agent1,
            "second-agent": agent2,
            "third-agent": agent3
        }
        
        registry = AgentRegistry(agent_configs=agent_configs)
        
        with caplog.at_level("WARNING"):
            configured_mappings = registry._create_configured_mappings(agent_configs)
        
        # Should consistently use first agent encountered (without ConfigurableAgent prefix)
        assert configured_mappings["DuplicateAlert"] == "first-agent"
        
        # Should have logged warnings for the conflicts
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        duplicate_warnings = [log for log in warning_logs if "DuplicateAlert" in log.message]
        assert len(duplicate_warnings) >= 2  # At least 2 conflicts should be detected 