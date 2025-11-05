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
        
        ("duplicate_chain_ids", {
            'duplicate-chain': ChainFactory.create_custom_chain(chain_id='duplicate-chain', alert_types=['builtin-alert'])
        }, {
            'duplicate-chain': ChainFactory.create_custom_chain(chain_id='duplicate-chain', alert_types=['yaml-alert'])
        }, True, "Chain ID conflicts detected.*duplicate-chain"),
        
        ("alert_type_conflicts_builtin", {
            'chain1': ChainFactory.create_custom_chain(chain_id='chain1', alert_types=['kubernetes', 'shared-alert']),
            'chain2': ChainFactory.create_custom_chain(chain_id='chain2', alert_types=['shared-alert'])
        }, {}, True, "Alert type 'shared-alert' conflicts.*chain1.*chain2"),
        
        ("alert_type_conflicts_builtin_yaml", {
            'builtin-chain': ChainFactory.create_custom_chain(chain_id='builtin-chain', alert_types=['kubernetes'])
        }, {
            'yaml-chain': ChainFactory.create_custom_chain(chain_id='yaml-chain', alert_types=['kubernetes'])
        }, True, "Alert type 'kubernetes' conflicts.*built-in.*YAML"),
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
