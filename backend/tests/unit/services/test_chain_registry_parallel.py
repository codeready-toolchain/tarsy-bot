"""
Unit tests for ChainRegistry parallel stage support.

Tests ChainRegistry functionality specific to parallel agent stages including
multi-agent parallelism, replica parallelism, and failure policy configuration.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.config.agent_config import ConfigurationLoader
from tarsy.models.agent_config import ParallelAgentConfig
from tarsy.models.constants import FailurePolicy
from tarsy.services.chain_registry import ChainRegistry


@pytest.mark.unit
class TestChainRegistryParallelStages:
    """Test ChainRegistry with parallel stage configurations."""
    
    def test_loading_yaml_chain_with_agents_list(self) -> None:
        """Test loading YAML chain with multi-agent parallel stage."""
        # ChainRegistry expects raw dictionary data, not ChainConfigModel objects
        yaml_chains = {
            'parallel-chain': {
                'chain_id': 'parallel-chain',
                'alert_types': ['parallel-test'],
                'stages': [
                    {
                        'name': 'investigation',
                        'agent': None,
                        'agents': [
                            {'name': 'Agent1', 'llm_provider': 'openai'},
                            {'name': 'Agent2', 'llm_provider': 'anthropic'}
                        ]
                    }
                ]
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'parallel-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('parallel-test')
        assert chain is not None
        assert chain.chain_id == 'parallel-chain'
        assert len(chain.stages) == 1
        assert chain.stages[0].agents is not None
        assert len(chain.stages[0].agents) == 2
        assert chain.stages[0].agents[0].name == 'Agent1'
        assert chain.stages[0].agents[0].llm_provider == 'openai'
        assert chain.stages[0].agents[1].name == 'Agent2'
        assert chain.stages[0].agents[1].llm_provider == 'anthropic'
    
    def test_loading_yaml_chain_with_replicas(self) -> None:
        """Test loading YAML chain with replica parallelism."""
        yaml_chains = {
            'replica-chain': {
                'chain_id': 'replica-chain',
                'alert_types': ['replica-test'],
                'stages': [
                    {
                        'name': 'analysis',
                        'agent': 'TestAgent',
                        'replicas': 3,
                        'llm_provider': 'openai'
                    }
                ]
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'replica-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('replica-test')
        assert chain is not None
        assert chain.chain_id == 'replica-chain'
        assert len(chain.stages) == 1
        assert chain.stages[0].agent == 'TestAgent'
        assert chain.stages[0].replicas == 3
        assert chain.stages[0].llm_provider == 'openai'
    
    def test_parallel_agent_config_parsing_from_yaml(self) -> None:
        """Test that ParallelAgentConfig is correctly parsed from YAML."""
        yaml_chains = {
            'config-test-chain': {
                'chain_id': 'config-test-chain',
                'alert_types': ['config-test'],
                'stages': [
                    {
                        'name': 'comparison',
                        'agent': None,
                        'agents': [
                            {
                                'name': 'TestAgent',
                                'llm_provider': 'openai',
                                'iteration_strategy': 'react'
                            },
                            {
                                'name': 'TestAgent',
                                'llm_provider': 'anthropic',
                                'iteration_strategy': 'react-stage'
                            },
                            {
                                'name': 'TestAgent',
                                'llm_provider': 'gemini',
                                'iteration_strategy': 'native-thinking'
                            }
                        ]
                    }
                ]
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'config-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('config-test')
        assert chain is not None
        assert len(chain.stages[0].agents) == 3
        
        for i, agent in enumerate(chain.stages[0].agents):
            assert isinstance(agent, ParallelAgentConfig)
            assert agent.name == 'TestAgent'
        
        assert chain.stages[0].agents[0].llm_provider == 'openai'
        assert chain.stages[0].agents[0].iteration_strategy == 'react'
        assert chain.stages[0].agents[1].llm_provider == 'anthropic'
        assert chain.stages[0].agents[1].iteration_strategy == 'react-stage'
        assert chain.stages[0].agents[2].llm_provider == 'gemini'
        assert chain.stages[0].agents[2].iteration_strategy == 'native-thinking'
    
    def test_stage_level_failure_policy_propagation(self) -> None:
        """Test that failure_policy is correctly propagated from YAML."""
        yaml_chains = {
            'policy-chain': {
                'chain_id': 'policy-chain',
                'alert_types': ['policy-test'],
                'stages': [
                    {
                        'name': 'stage1',
                        'agent': None,
                        'agents': [
                            {'name': 'Agent1'},
                            {'name': 'Agent2'}
                        ],
                        'failure_policy': 'all'
                    },
                    {
                        'name': 'stage2',
                        'agent': None,
                        'agents': [
                            {'name': 'Agent3'},
                            {'name': 'Agent4'}
                        ],
                        'failure_policy': 'any'
                    }
                ]
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'policy-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('policy-test')
        assert chain is not None
        assert chain.stages[0].failure_policy == FailurePolicy.ALL
        assert chain.stages[1].failure_policy == FailurePolicy.ANY

