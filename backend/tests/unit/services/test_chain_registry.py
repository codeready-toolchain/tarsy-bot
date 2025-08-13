"""
Unit tests for ChainRegistry - Chain definition loading and lookup system.

Tests chain loading from built-in and YAML configurations, validation logic,
chain lookup functionality, and error handling.
"""

import pytest
from unittest.mock import Mock, patch

from tarsy.services.chain_registry import ChainRegistry
from tarsy.models.chains import ChainDefinitionModel, ChainStageModel
from tarsy.config.agent_config import ConfigurationLoader


@pytest.mark.unit
class TestChainRegistryInitialization:
    """Test ChainRegistry initialization and configuration loading."""
    
    def test_initialization_builtin_only(self):
        """Test initialization with only built-in chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'kubernetes-chain': {
                    'alert_types': ['kubernetes'],
                    'stages': [{'name': 'analysis', 'agent': 'KubernetesAgent'}],
                    'description': 'Kubernetes chain'
                }
            }
            
            registry = ChainRegistry()
            
            assert len(registry.builtin_chains) == 1
            assert 'kubernetes-chain' in registry.builtin_chains
            assert len(registry.yaml_chains) == 0
            assert len(registry.alert_type_mappings) == 1
            assert registry.alert_type_mappings['kubernetes'] == 'kubernetes-chain'
    
    def test_initialization_with_yaml_config(self):
        """Test initialization with YAML configuration loader."""
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = {
            'custom-chain': {
                'alert_types': ['custom'],
                'stages': [{'name': 'stage1', 'agent': 'CustomAgent'}],
                'description': 'Custom chain'
            }
        }
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'kubernetes-chain': {
                    'alert_types': ['kubernetes'], 
                    'stages': [{'name': 'analysis', 'agent': 'KubernetesAgent'}]
                }
            }
            
            registry = ChainRegistry(mock_config_loader)
            
            assert len(registry.builtin_chains) == 1
            assert len(registry.yaml_chains) == 1
            assert 'custom-chain' in registry.yaml_chains
            assert len(registry.alert_type_mappings) == 2
            assert registry.alert_type_mappings['custom'] == 'custom-chain'
    
    def test_initialization_yaml_config_failure(self):
        """Test initialization when YAML config loading fails."""
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.side_effect = Exception("Config error")
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'kubernetes-chain': {
                    'alert_types': ['kubernetes'],
                    'stages': [{'name': 'analysis', 'agent': 'KubernetesAgent'}]
                }
            }
            
            # Should not raise, just log warning and continue with built-in chains
            registry = ChainRegistry(mock_config_loader)
            
            assert len(registry.builtin_chains) == 1
            assert len(registry.yaml_chains) == 0


@pytest.mark.unit
class TestChainRegistryValidation:
    """Test ChainRegistry validation logic."""
    
    def test_chain_id_uniqueness_validation_pass(self):
        """Test validation passes when chain IDs are unique."""
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = {
            'yaml-chain': {
                'alert_types': ['yaml-alert'],
                'stages': [{'name': 'stage1', 'agent': 'YamlAgent'}]
            }
        }
        
        with patch('tarsy.config.builtin_config.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-chain': {
                    'alert_types': ['builtin-alert'],
                    'stages': [{'name': 'analysis', 'agent': 'BuiltinAgent'}]
                }
            }
            
            # Should not raise
            registry = ChainRegistry(mock_config_loader)
            assert len(registry.builtin_chains) == 1
            assert len(registry.yaml_chains) == 1
    
    def test_chain_id_uniqueness_validation_fail(self):
        """Test validation fails when chain IDs conflict."""
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = {
            'duplicate-chain': {
                'alert_types': ['yaml-alert'],
                'stages': [{'name': 'stage1', 'agent': 'YamlAgent'}]
            }
        }
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'duplicate-chain': {
                    'alert_types': ['builtin-alert'],
                    'stages': [{'name': 'analysis', 'agent': 'BuiltinAgent'}]
                }
            }
            
            with pytest.raises(ValueError, match="Chain ID conflicts detected.*duplicate-chain"):
                ChainRegistry(mock_config_loader)
    
    def test_alert_type_conflicts_builtin_vs_builtin(self):
        """Test validation fails when built-in chains have alert type conflicts."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'chain1': {
                    'alert_types': ['kubernetes', 'shared-alert'],
                    'stages': [{'name': 'stage1', 'agent': 'Agent1'}]
                },
                'chain2': {
                    'alert_types': ['shared-alert'],
                    'stages': [{'name': 'stage2', 'agent': 'Agent2'}]
                }
            }
            
            with pytest.raises(ValueError, match="Alert type 'shared-alert' conflicts.*chain1.*chain2"):
                ChainRegistry()
    
    def test_alert_type_conflicts_yaml_vs_builtin(self):
        """Test validation fails when YAML and built-in chains have alert type conflicts."""
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = {
            'yaml-chain': {
                'alert_types': ['kubernetes'],  # Conflicts with built-in
                'stages': [{'name': 'yaml-stage', 'agent': 'YamlAgent'}]
            }
        }
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'builtin-chain': {
                    'alert_types': ['kubernetes'],
                    'stages': [{'name': 'builtin-stage', 'agent': 'BuiltinAgent'}]
                }
            }
            
            with pytest.raises(ValueError, match="Alert type 'kubernetes' conflicts.*built-in.*YAML"):
                ChainRegistry(mock_config_loader)


@pytest.mark.unit
class TestChainRegistryLookup:
    """Test chain lookup functionality."""
    
    @pytest.fixture
    def sample_registry(self):
        """Create registry with sample chains."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'kubernetes-chain': {
                    'alert_types': ['kubernetes', 'NamespaceTerminating'],
                    'stages': [
                        {'name': 'data-collection', 'agent': 'KubernetesAgent'},
                        {'name': 'analysis', 'agent': 'KubernetesAgent', 'iteration_strategy': 'react'}
                    ],
                    'description': 'Kubernetes troubleshooting chain'
                },
                'single-stage-chain': {
                    'alert_types': ['simple'],
                    'stages': [{'name': 'analysis', 'agent': 'SimpleAgent'}]
                }
            }
            
            return ChainRegistry()
    
    def test_get_chain_for_alert_type_success(self, sample_registry):
        """Test successful chain lookup by alert type."""
        chain = sample_registry.get_chain_for_alert_type('kubernetes')
        
        assert chain.chain_id == 'kubernetes-chain'
        assert 'kubernetes' in chain.alert_types
        assert len(chain.stages) == 2
        assert chain.stages[0].name == 'data-collection'
        assert chain.stages[0].agent == 'KubernetesAgent'
        assert chain.stages[1].iteration_strategy == 'react'
    
    def test_get_chain_for_alert_type_multiple_mappings(self, sample_registry):
        """Test that different alert types can map to same chain."""
        chain1 = sample_registry.get_chain_for_alert_type('kubernetes')
        chain2 = sample_registry.get_chain_for_alert_type('NamespaceTerminating')
        
        assert chain1.chain_id == chain2.chain_id == 'kubernetes-chain'
    
    def test_get_chain_for_alert_type_not_found(self, sample_registry):
        """Test error when no chain found for alert type."""
        with pytest.raises(ValueError, match="No chain found for alert type 'unknown'.*Available:"):
            sample_registry.get_chain_for_alert_type('unknown')
    
    def test_get_chain_by_id_success(self, sample_registry):
        """Test successful chain lookup by ID."""
        chain = sample_registry.get_chain_by_id('kubernetes-chain')
        
        assert chain is not None
        assert chain.chain_id == 'kubernetes-chain'
        assert len(chain.stages) == 2
    
    def test_get_chain_by_id_not_found(self, sample_registry):
        """Test chain lookup by ID returns None for unknown ID."""
        chain = sample_registry.get_chain_by_id('unknown-chain')
        
        assert chain is None
    
    def test_list_available_alert_types(self, sample_registry):
        """Test listing available alert types."""
        alert_types = sample_registry.list_available_alert_types()
        
        assert alert_types == ['NamespaceTerminating', 'kubernetes', 'simple']  # Sorted
        assert len(alert_types) == 3
    
    def test_list_available_chains(self, sample_registry):
        """Test listing available chain IDs."""
        chains = sample_registry.list_available_chains()
        
        assert chains == ['kubernetes-chain', 'single-stage-chain']  # Sorted
        assert len(chains) == 2


@pytest.mark.unit
class TestChainRegistryErrorHandling:
    """Test error handling in chain loading."""
    
    def test_invalid_builtin_chain_skipped(self):
        """Test that invalid built-in chains are skipped with logging."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'valid-chain': {
                    'alert_types': ['valid'],
                    'stages': [{'name': 'stage1', 'agent': 'ValidAgent'}]
                },
                'invalid-chain': {
                    'alert_types': ['invalid'],
                    'stages': [{'invalid': 'missing required fields'}]  # Missing 'name' and 'agent'
                }
            }
            
            registry = ChainRegistry()
            
            # Only valid chain should be loaded
            assert len(registry.builtin_chains) == 1
            assert 'valid-chain' in registry.builtin_chains
            assert 'invalid-chain' not in registry.builtin_chains
            assert registry.alert_type_mappings['valid'] == 'valid-chain'
    
    def test_invalid_yaml_chain_skipped(self):
        """Test that invalid YAML chains are skipped with logging."""
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = {
            'valid-yaml-chain': {
                'alert_types': ['valid-yaml'],
                'stages': [{'name': 'yaml-stage', 'agent': 'YamlAgent'}]
            },
            'invalid-yaml-chain': {
                'alert_types': ['invalid-yaml'],
                'stages': [{'missing': 'required fields'}]  # Missing 'name' and 'agent'
            }
        }
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            
            registry = ChainRegistry(mock_config_loader)
            
            # Only valid YAML chain should be loaded
            assert len(registry.yaml_chains) == 1
            assert 'valid-yaml-chain' in registry.yaml_chains
            assert 'invalid-yaml-chain' not in registry.yaml_chains
            assert registry.alert_type_mappings['valid-yaml'] == 'valid-yaml-chain'


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
        """Test that ChainDefinitionModel objects are created correctly."""
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {
                'test-chain': {
                    'alert_types': ['test1', 'test2'],
                    'stages': [
                        {'name': 'stage1', 'agent': 'Agent1'},
                        {'name': 'stage2', 'agent': 'Agent2', 'iteration_strategy': 'react'}
                    ],
                    'description': 'Test chain description'
                }
            }
            
            registry = ChainRegistry()
            chain = registry.get_chain_for_alert_type('test1')
            
            # Verify ChainDefinitionModel structure
            assert isinstance(chain, ChainDefinitionModel)
            assert chain.chain_id == 'test-chain'
            assert chain.alert_types == ['test1', 'test2']
            assert chain.description == 'Test chain description'
            
            # Verify ChainStageModel structure
            assert len(chain.stages) == 2
            assert isinstance(chain.stages[0], ChainStageModel)
            assert chain.stages[0].name == 'stage1'
            assert chain.stages[0].agent == 'Agent1'
            assert chain.stages[0].iteration_strategy is None
            
            assert chain.stages[1].name == 'stage2'
            assert chain.stages[1].agent == 'Agent2'
            assert chain.stages[1].iteration_strategy == 'react'
