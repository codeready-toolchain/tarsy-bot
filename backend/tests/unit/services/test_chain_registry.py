"""
Unit tests for ChainRegistry - Chain definition loading and lookup system.

Tests chain loading from built-in and YAML configurations, validation logic,
chain lookup functionality, and error handling.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.config.agent_config import ConfigurationLoader
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.services.chain_registry import ChainRegistry
from tests.utils import ChainFactory


@pytest.mark.unit
class TestChainRegistryInitialization:
    """Test ChainRegistry initialization and configuration loading."""
    
    @pytest.mark.parametrize("scenario,config_loader_config,expected_builtin,expected_yaml,expected_mappings", [
        ("default_only", None, 1, 0, {'kubernetes': 'kubernetes-chain'}),
        ("with_custom_config", {
            'custom-chain': ChainFactory.create_custom_chain()
        }, 1, 1, {'kubernetes': 'kubernetes-chain', 'custom': 'custom-chain'}),
        ("config_error", Exception("Config error"), 1, 0, {'kubernetes': 'kubernetes-chain'}),
    ])
    def test_initialization_scenarios(self, scenario, config_loader_config, expected_builtin, expected_yaml, expected_mappings):
        """Test initialization for various configuration scenarios."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'kubernetes-chain': ChainFactory.create_kubernetes_chain(chain_id='kubernetes-chain')
            }
            
            config_loader = None
            if config_loader_config is not None and not isinstance(config_loader_config, Exception):
                config_loader = Mock(spec=ConfigurationLoader)
                config_loader.get_chain_configs.return_value = config_loader_config
                # Mock load_and_validate to return config with default_alert_type = None
                mock_config = Mock()
                mock_config.default_alert_type = None
                config_loader.load_and_validate.return_value = mock_config
            elif isinstance(config_loader_config, Exception):
                config_loader = Mock(spec=ConfigurationLoader)
                config_loader.get_chain_configs.side_effect = config_loader_config
                # Mock load_and_validate to return config with default_alert_type = None
                mock_config = Mock()
                mock_config.default_alert_type = None
                config_loader.load_and_validate.return_value = mock_config
            
            if config_loader:
                registry = ChainRegistry(config_loader)
            else:
                registry = ChainRegistry()
            
            assert len(registry.builtin_chains) == expected_builtin
            assert len(registry.yaml_chains) == expected_yaml
            assert len(registry.alert_type_mappings) == len(expected_mappings)
            
            for alert_type, chain_id in expected_mappings.items():
                assert registry.alert_type_mappings[alert_type] == chain_id


@pytest.mark.unit
class TestChainRegistryValidation:
    """Test ChainRegistry validation logic."""
    
    @pytest.mark.parametrize("scenario,builtin_chains,yaml_chains,should_raise,expected_error", [
        ("valid_unique_ids", {
            'builtin-chain': ChainFactory.create_custom_chain(chain_id='builtin-chain', alert_types=['builtin-alert', 'kubernetes'])
        }, {
            'yaml-chain': ChainFactory.create_custom_chain(chain_id='yaml-chain', alert_types=['yaml-alert'])
        }, False, None),
        
        # YAML chains CAN override built-in chains with the same chain_id (no error)
        ("duplicate_chain_ids_allowed", {
            'duplicate-chain': ChainFactory.create_custom_chain(chain_id='duplicate-chain', alert_types=['builtin-alert', 'kubernetes'])
        }, {
            'duplicate-chain': ChainFactory.create_custom_chain(chain_id='duplicate-chain', alert_types=['yaml-alert'])
        }, False, None),
        
        # Built-in vs built-in conflicts still raise errors
        ("alert_type_conflicts_builtin", {
            'chain1': ChainFactory.create_custom_chain(chain_id='chain1', alert_types=['kubernetes', 'shared-alert']),
            'chain2': ChainFactory.create_custom_chain(chain_id='chain2', alert_types=['shared-alert'])
        }, {}, True, "Alert type 'shared-alert' conflicts.*chain1.*chain2"),
        
        # YAML vs YAML conflicts still raise errors
        ("alert_type_conflicts_yaml_yaml", {
            'builtin-chain': ChainFactory.create_custom_chain(chain_id='builtin-chain', alert_types=['kubernetes'])
        }, {
            'yaml-chain1': ChainFactory.create_custom_chain(chain_id='yaml-chain1', alert_types=['yaml-alert']),
            'yaml-chain2': ChainFactory.create_custom_chain(chain_id='yaml-chain2', alert_types=['yaml-alert'])
        }, True, "Alert type 'yaml-alert' conflicts.*YAML.*YAML"),
        
        # YAML chains CAN override built-in alert types (no error)
        ("alert_type_override_builtin_yaml_allowed", {
            'builtin-chain': ChainFactory.create_custom_chain(chain_id='builtin-chain', alert_types=['kubernetes'])
        }, {
            'yaml-chain': ChainFactory.create_custom_chain(chain_id='yaml-chain', alert_types=['kubernetes'])
        }, False, None),
    ])
    def test_validation_scenarios(self, scenario, builtin_chains, yaml_chains, should_raise, expected_error):
        """Test validation for various conflict scenarios."""
        mock_config_loader = None
        if yaml_chains:
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = yaml_chains
            # Mock load_and_validate to return config with default_alert_type = None
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = builtin_chains
            
            if should_raise:
                with pytest.raises(ValueError, match=expected_error):
                    if mock_config_loader:
                        ChainRegistry(mock_config_loader)
                    else:
                        ChainRegistry()
            else:
                if mock_config_loader:
                    registry = ChainRegistry(mock_config_loader)
                else:
                    registry = ChainRegistry()
                
                # Verify successful initialization
                assert len(registry.builtin_chains) == len(builtin_chains)
                assert len(registry.yaml_chains) == len(yaml_chains)


@pytest.mark.unit
class TestChainRegistryLookup:
    """Test chain lookup functionality."""
    
    @pytest.fixture
    def sample_registry(self):
        """Create registry with sample chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'kubernetes-chain': ChainFactory.create_kubernetes_chain(),
                'single-stage-chain': ChainFactory.create_simple_chain(chain_id='single-stage-chain')
            }
            
            return ChainRegistry()
    
    @pytest.mark.parametrize("alert_type,expected_chain_id,expected_stages,should_raise", [
        ('kubernetes', 'kubernetes-chain', 2, False),
        ('simple', 'single-stage-chain', 1, False),
        ('unknown', None, None, True),
    ])
    def test_get_chain_for_alert_type_scenarios(self, sample_registry, alert_type, expected_chain_id, expected_stages, should_raise):
        """Test chain lookup by alert type for various scenarios."""
        if should_raise:
            with pytest.raises(ValueError, match=f"No chain found for alert type '{alert_type}'.*Available:"):
                sample_registry.get_chain_for_alert_type(alert_type)
        else:
            chain = sample_registry.get_chain_for_alert_type(alert_type)
            assert chain.chain_id == expected_chain_id
            assert len(chain.stages) == expected_stages
            
            # Verify specific chain properties
            if expected_chain_id == 'kubernetes-chain':
                assert 'kubernetes' in chain.alert_types
                assert chain.stages[0].name == 'data-collection'
                assert chain.stages[0].agent == 'KubernetesAgent'
                assert chain.stages[1].iteration_strategy == 'react'

    @pytest.mark.parametrize("chain_id,expected_result", [
        ('kubernetes-chain', True),  # Should find the chain
        ('single-stage-chain', True),  # Should find the chain
        ('unknown-chain', False),  # Should return None
    ])
    def test_get_chain_by_id_scenarios(self, sample_registry, chain_id, expected_result):
        """Test chain lookup by ID for various scenarios."""
        chain = sample_registry.get_chain_by_id(chain_id)
        
        if expected_result:
            assert chain is not None
            assert chain.chain_id == chain_id
            assert len(chain.stages) >= 1
        else:
            assert chain is None
    
    def test_list_available_alert_types(self, sample_registry):
        """Test listing available alert types."""
        alert_types = sample_registry.list_available_alert_types()
        
        assert alert_types == ['kubernetes', 'simple']  # Sorted
        assert len(alert_types) == 2
    
    def test_list_available_chains(self, sample_registry):
        """Test listing available chain IDs."""
        chains = sample_registry.list_available_chains()
        
        assert chains == ['kubernetes-chain', 'single-stage-chain']  # Sorted
        assert len(chains) == 2


@pytest.mark.unit
class TestChainRegistryErrorHandling:
    """Test error handling in chain loading."""
    
    @pytest.mark.parametrize("chain_type,valid_chains,invalid_chains,expected_valid_count", [
        ('builtin', {
            'valid-chain': ChainFactory.create_custom_chain(chain_id='valid-chain', alert_types=['valid', 'kubernetes'])
        }, {
            'invalid-chain': ChainFactory.create_invalid_chain(chain_id='invalid-chain')
        }, 1),
        ('yaml', {
            'valid-yaml-chain': ChainFactory.create_custom_chain(chain_id='valid-yaml-chain', alert_types=['valid-yaml', 'kubernetes'])
        }, {
            'invalid-yaml-chain': ChainFactory.create_invalid_chain(chain_id='invalid-yaml-chain')
        }, 1),
    ])
    def test_invalid_chain_skipping(self, chain_type, valid_chains, invalid_chains, expected_valid_count):
        """Test that invalid chains are skipped with logging."""
        mock_config_loader = None
        if chain_type == 'yaml':
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {**valid_chains, **invalid_chains}
            # Mock load_and_validate to return config with default_alert_type = None
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            if chain_type == 'builtin':
                mock_builtin.return_value = {**valid_chains, **invalid_chains}
            else:
                mock_builtin.return_value = {}
            
            if mock_config_loader:
                registry = ChainRegistry(mock_config_loader)
            else:
                registry = ChainRegistry()
            
            # Only valid chains should be loaded
            if chain_type == 'builtin':
                assert len(registry.builtin_chains) == expected_valid_count
                for chain_id in valid_chains:
                    assert chain_id in registry.builtin_chains
                for chain_id in invalid_chains:
                    assert chain_id not in registry.builtin_chains
            else:
                assert len(registry.yaml_chains) == expected_valid_count
                for chain_id in valid_chains:
                    assert chain_id in registry.yaml_chains
                for chain_id in invalid_chains:
                    assert chain_id not in registry.yaml_chains
            
            # Verify alert type mappings
            for chain_id, chain_config in valid_chains.items():
                for alert_type in chain_config['alert_types']:
                    assert registry.alert_type_mappings[alert_type] == chain_id


@pytest.mark.unit 
class TestChainRegistryIntegration:
    """Test ChainRegistry integration with real configurations."""
    
    def test_with_real_builtin_config(self):
        """Test registry works with actual built-in configuration."""
        # This tests the real builtin_config without mocking
        registry = ChainRegistry()
        
        # Should have at least the kubernetes chain from builtin_config
        assert len(registry.builtin_chains) >= 1
        assert 'kubernetes-agent-chain' in registry.builtin_chains
        assert 'kubernetes' in registry.alert_type_mappings
        
        # Test chain lookup
        k8s_chain = registry.get_chain_for_alert_type('kubernetes')
        assert k8s_chain.chain_id == 'kubernetes-agent-chain'
        assert len(k8s_chain.stages) >= 1
        assert k8s_chain.stages[0].agent == 'KubernetesAgent'
    
    def test_chain_definition_models_creation(self):
        """Test that ChainConfigModel objects are created correctly."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            test_chain = ChainFactory.create_kubernetes_chain(
                chain_id='test-chain',
                alert_types=['test1', 'test2', 'kubernetes'],
                description='Test chain description'
            )
            mock_builtin.return_value = {'test-chain': test_chain}
            
            registry = ChainRegistry()
            chain = registry.get_chain_for_alert_type('test1')
            
            # Verify ChainConfigModel structure
            assert isinstance(chain, ChainConfigModel)
            assert chain.chain_id == 'test-chain'
            assert chain.alert_types == ['test1', 'test2', 'kubernetes']
            assert chain.description == 'Test chain description'
            
            # Verify ChainStageConfigModel structure
            assert len(chain.stages) == 2
            assert isinstance(chain.stages[0], ChainStageConfigModel)
            assert chain.stages[0].name == 'data-collection'
            assert chain.stages[0].agent == 'KubernetesAgent'
            assert chain.stages[0].iteration_strategy == 'react'
            
            assert chain.stages[1].name == 'analysis'
            assert chain.stages[1].agent == 'KubernetesAgent'
            assert chain.stages[1].iteration_strategy == 'react'


@pytest.mark.unit
class TestChainRegistryDefaultAlertType:
    """Test ChainRegistry default alert type functionality."""
    
    def test_default_alert_type_from_config(self):
        """Test that default alert type is loaded from configuration."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'test-chain': ChainFactory.create_custom_chain(
                    chain_id='test-chain',
                    alert_types=['custom-alert', 'kubernetes']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {}
            
            # Mock load_and_validate to return config with default_alert_type
            mock_config = Mock()
            mock_config.default_alert_type = 'custom-alert'
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            assert registry.get_default_alert_type() == 'custom-alert'
    
    def test_default_alert_type_fallback_to_constant(self):
        """Test that default alert type falls back to DEFAULT_ALERT_TYPE constant."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'test-chain': ChainFactory.create_custom_chain(
                    chain_id='test-chain',
                    alert_types=['kubernetes', 'other-alert']
                )
            }
            
            # No config loader provided
            registry = ChainRegistry()
            
            # Should default to 'kubernetes' (DEFAULT_ALERT_TYPE constant)
            assert registry.get_default_alert_type() == 'kubernetes'
    
    def test_default_alert_type_fallback_when_config_empty(self):
        """Test that default alert type falls back when config doesn't specify one."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'test-chain': ChainFactory.create_custom_chain(
                    chain_id='test-chain',
                    alert_types=['kubernetes', 'other-alert']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {}
            
            # Mock load_and_validate to return config without default_alert_type
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            # Should default to 'kubernetes' (DEFAULT_ALERT_TYPE constant)
            assert registry.get_default_alert_type() == 'kubernetes'
    
    def test_validation_error_when_default_not_available(self):
        """Test that validation fails when default alert type is not in any chain."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'test-chain': ChainFactory.create_custom_chain(
                    chain_id='test-chain',
                    alert_types=['alert1', 'alert2']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {}
            
            # Mock load_and_validate to return config with non-existent default
            mock_config = Mock()
            mock_config.default_alert_type = 'non-existent-alert'
            mock_config_loader.load_and_validate.return_value = mock_config
            
            with pytest.raises(ValueError, match="Default alert type 'non-existent-alert' is not available in any chain definition"):
                ChainRegistry(mock_config_loader)
    
    def test_validation_passes_when_default_exists_in_builtin(self):
        """Test that validation passes when default alert type exists in built-in chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'test-chain': ChainFactory.create_custom_chain(
                    chain_id='test-chain',
                    alert_types=['kubernetes', 'alert2']
                )
            }
            
            # Use default constant (kubernetes) which is in the chain
            registry = ChainRegistry()
            
            assert registry.get_default_alert_type() == 'kubernetes'
    
    def test_validation_passes_when_default_exists_in_yaml(self):
        """Test that validation passes when default alert type exists in YAML chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'yaml-chain': ChainFactory.create_custom_chain(
                    chain_id='yaml-chain',
                    alert_types=['yaml-alert', 'other-alert']
                )
            }
            
            # Mock load_and_validate to return config with yaml-alert as default
            mock_config = Mock()
            mock_config.default_alert_type = 'yaml-alert'
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            assert registry.get_default_alert_type() == 'yaml-alert'


@pytest.mark.unit
class TestChainRegistryOverrides:
    """Test ChainRegistry override behavior - YAML chains can override built-in chains."""
    
    def test_yaml_chain_overrides_builtin_alert_type(self):
        """Test that YAML chain properly overrides built-in chain for same alert type."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-kubernetes': ChainFactory.create_kubernetes_chain(
                    chain_id='builtin-kubernetes',
                    alert_types=['kubernetes']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'yaml-kubernetes': ChainFactory.create_custom_chain(
                    chain_id='yaml-kubernetes',
                    alert_types=['kubernetes'],
                    stages=[{'name': 'custom-stage', 'agent': 'CustomAgent'}]
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            # YAML chain should override the built-in for 'kubernetes' alert type
            chain = registry.get_chain_for_alert_type('kubernetes')
            assert chain.chain_id == 'yaml-kubernetes'
            assert chain.stages[0].agent == 'CustomAgent'
    
    def test_yaml_chain_overrides_builtin_chain_id(self):
        """Test that YAML chain with same chain_id as built-in takes precedence."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'shared-chain': ChainFactory.create_kubernetes_chain(
                    chain_id='shared-chain',
                    alert_types=['builtin-alert', 'kubernetes']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'shared-chain': ChainFactory.create_custom_chain(
                    chain_id='shared-chain',
                    alert_types=['yaml-alert', 'builtin-alert', 'kubernetes'],
                    stages=[{'name': 'yaml-stage', 'agent': 'YAMLAgent'}]
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            # Get chain by ID - YAML should take precedence
            chain = registry.get_chain_by_id('shared-chain')
            assert chain.stages[0].agent == 'YAMLAgent'
            
            # Alert type 'builtin-alert' should now use YAML chain (override)
            chain_for_alert = registry.get_chain_for_alert_type('builtin-alert')
            assert chain_for_alert.stages[0].agent == 'YAMLAgent'
    
    def test_overridden_chain_ids_tracked(self):
        """Test that overridden chain_ids are tracked in the registry."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'chain-to-override': ChainFactory.create_kubernetes_chain(
                    chain_id='chain-to-override',
                    alert_types=['kubernetes']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'chain-to-override': ChainFactory.create_custom_chain(
                    chain_id='chain-to-override',
                    alert_types=['custom-alert', 'kubernetes']
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            # Check that the override is tracked
            assert 'chain-to-override' in registry.overridden_chain_ids
    
    def test_multiple_alert_type_overrides(self):
        """Test that YAML chain can override multiple alert types from built-in."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-chain': ChainFactory.create_kubernetes_chain(
                    chain_id='builtin-chain',
                    alert_types=['alert1', 'alert2', 'kubernetes']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'yaml-chain': ChainFactory.create_custom_chain(
                    chain_id='yaml-chain',
                    alert_types=['alert1', 'alert2'],  # Override both
                    stages=[{'name': 'yaml-stage', 'agent': 'YAMLAgent'}]
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            # Both alert types should use YAML chain
            assert registry.get_chain_for_alert_type('alert1').chain_id == 'yaml-chain'
            assert registry.get_chain_for_alert_type('alert2').chain_id == 'yaml-chain'
            # 'kubernetes' should still use built-in
            assert registry.get_chain_for_alert_type('kubernetes').chain_id == 'builtin-chain'
    
    def test_override_does_not_affect_non_conflicting_chains(self):
        """Test that override only affects conflicting alert types, not others."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-chain': ChainFactory.create_kubernetes_chain(
                    chain_id='builtin-chain',
                    alert_types=['kubernetes', 'builtin-only']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'yaml-chain': ChainFactory.create_custom_chain(
                    chain_id='yaml-chain',
                    alert_types=['kubernetes', 'yaml-only']  # Only 'kubernetes' conflicts
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            # 'kubernetes' overridden by YAML
            assert registry.get_chain_for_alert_type('kubernetes').chain_id == 'yaml-chain'
            # 'builtin-only' still uses built-in
            assert registry.get_chain_for_alert_type('builtin-only').chain_id == 'builtin-chain'
            # 'yaml-only' uses YAML
            assert registry.get_chain_for_alert_type('yaml-only').chain_id == 'yaml-chain'
    
    def test_list_available_chains_includes_both_sources(self):
        """Test that list_available_chains includes chains from both sources."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-chain': ChainFactory.create_kubernetes_chain(
                    chain_id='builtin-chain',
                    alert_types=['kubernetes']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'yaml-chain': ChainFactory.create_custom_chain(
                    chain_id='yaml-chain',
                    alert_types=['custom']
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            chains = registry.list_available_chains()
            assert 'builtin-chain' in chains
            assert 'yaml-chain' in chains
    
    def test_list_available_alert_types_includes_overridden(self):
        """Test that list_available_alert_types includes both overridden and new alert types."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-chain': ChainFactory.create_kubernetes_chain(
                    chain_id='builtin-chain',
                    alert_types=['kubernetes', 'builtin-only']
                )
            }
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'yaml-chain': ChainFactory.create_custom_chain(
                    chain_id='yaml-chain',
                    alert_types=['kubernetes', 'yaml-only']  # Override 'kubernetes'
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            
            alert_types = registry.list_available_alert_types()
            # All alert types should be available
            assert 'kubernetes' in alert_types
            assert 'builtin-only' in alert_types
            assert 'yaml-only' in alert_types


@pytest.mark.unit
class TestChainRegistryLLMProviderPropagation:
    """Test that llm_provider fields are properly propagated when loading chains."""
    
    def test_yaml_chain_stage_level_llm_provider_preserved(self):
        """Test that stage-level llm_provider is preserved when loading YAML chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'multi-model-chain': ChainFactory.create_multi_model_chain(
                    chain_id='multi-model-chain',
                    alert_types=['multi-model', 'kubernetes']
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            chain = registry.get_chain_for_alert_type('multi-model')
            
            # Verify stage-level llm_provider is preserved
            assert chain.stages[0].llm_provider == 'gemini-flash'
            assert chain.stages[1].llm_provider == 'gemini-pro'
    
    def test_yaml_chain_level_llm_provider_preserved(self):
        """Test that chain-level llm_provider is preserved when loading YAML chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'chain-with-provider': ChainFactory.create_custom_chain(
                    chain_id='chain-with-provider',
                    alert_types=['test-alert', 'kubernetes'],
                    llm_provider='google-default'
                )
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            chain = registry.get_chain_for_alert_type('test-alert')
            
            # Verify chain-level llm_provider is preserved
            assert chain.llm_provider == 'google-default'
    
    def test_builtin_chain_stage_level_llm_provider_preserved(self):
        """Test that stage-level llm_provider is preserved when loading builtin chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-multi-model': ChainFactory.create_multi_model_chain(
                    chain_id='builtin-multi-model',
                    alert_types=['kubernetes']
                )
            }
            
            registry = ChainRegistry()
            chain = registry.get_chain_for_alert_type('kubernetes')
            
            # Verify stage-level llm_provider is preserved
            assert chain.stages[0].llm_provider == 'gemini-flash'
            assert chain.stages[1].llm_provider == 'gemini-pro'
    
    def test_builtin_chain_level_llm_provider_preserved(self):
        """Test that chain-level llm_provider is preserved when loading builtin chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-with-provider': ChainFactory.create_custom_chain(
                    chain_id='builtin-with-provider',
                    alert_types=['kubernetes'],
                    llm_provider='anthropic-default'
                )
            }
            
            registry = ChainRegistry()
            chain = registry.get_chain_for_alert_type('kubernetes')
            
            # Verify chain-level llm_provider is preserved
            assert chain.llm_provider == 'anthropic-default'
    
    def test_stage_without_llm_provider_has_none(self):
        """Test that stages without llm_provider have None value."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'no-provider-chain': ChainFactory.create_kubernetes_chain(
                    chain_id='no-provider-chain',
                    alert_types=['kubernetes']
                )
            }
            
            registry = ChainRegistry()
            chain = registry.get_chain_for_alert_type('kubernetes')
            
            # Verify stages without llm_provider have None
            assert chain.stages[0].llm_provider is None
            assert chain.stages[1].llm_provider is None
            assert chain.llm_provider is None
    
    @pytest.mark.parametrize("stage_providers,chain_provider,expected_stage_providers,expected_chain_provider", [
        # Both stage and chain level providers
        (["gemini-flash", "gemini-pro"], "google-default", ["gemini-flash", "gemini-pro"], "google-default"),
        # Only stage-level providers
        (["gemini-flash", "gemini-pro"], None, ["gemini-flash", "gemini-pro"], None),
        # Only chain-level provider
        ([None, None], "google-default", [None, None], "google-default"),
        # No providers at any level
        ([None, None], None, [None, None], None),
        # Mixed - some stages have provider, some don't
        (["gemini-flash", None], "fallback-provider", ["gemini-flash", None], "fallback-provider"),
    ])
    def test_llm_provider_combinations(
        self,
        stage_providers,
        chain_provider,
        expected_stage_providers,
        expected_chain_provider
    ):
        """Test various combinations of stage-level and chain-level llm_provider."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            
            # Build stages with specified providers
            stages = [
                {
                    "name": f"stage-{i}",
                    "agent": "TestAgent",
                    "llm_provider": provider
                }
                for i, provider in enumerate(stage_providers)
            ]
            
            mock_config_loader = Mock(spec=ConfigurationLoader)
            mock_config_loader.get_chain_configs.return_value = {
                'test-chain': {
                    "chain_id": "test-chain",
                    "alert_types": ["test-alert", "kubernetes"],
                    "stages": stages,
                    "description": "Test chain",
                    "llm_provider": chain_provider
                }
            }
            mock_config = Mock()
            mock_config.default_alert_type = None
            mock_config_loader.load_and_validate.return_value = mock_config
            
            registry = ChainRegistry(mock_config_loader)
            chain = registry.get_chain_for_alert_type('test-alert')
            
            # Verify all providers are correctly preserved
            for i, expected_provider in enumerate(expected_stage_providers):
                assert chain.stages[i].llm_provider == expected_provider
            
            assert chain.llm_provider == expected_chain_provider
