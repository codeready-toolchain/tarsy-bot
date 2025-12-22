"""
Unit tests for ChainRegistry parallel stage support.

Tests ChainRegistry functionality specific to parallel agent stages including
multi-agent parallelism, replica parallelism, and failure policy configuration.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.config.agent_config import ConfigurationLoader
from tarsy.models.agent_config import ParallelAgentConfig
from tarsy.models.constants import SuccessPolicy
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
        
        for agent in chain.stages[0].agents:
            assert isinstance(agent, ParallelAgentConfig)
            assert agent.name == 'TestAgent'
        
        assert chain.stages[0].agents[0].llm_provider == 'openai'
        assert chain.stages[0].agents[0].iteration_strategy == 'react'
        assert chain.stages[0].agents[1].llm_provider == 'anthropic'
        assert chain.stages[0].agents[1].iteration_strategy == 'react-stage'
        assert chain.stages[0].agents[2].llm_provider == 'gemini'
        assert chain.stages[0].agents[2].iteration_strategy == 'native-thinking'
    
    def test_stage_level_success_policy_propagation(self) -> None:
        """Test that success_policy is correctly propagated from YAML."""
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
                        'success_policy': 'all'
                    },
                    {
                        'name': 'stage2',
                        'agent': None,
                        'agents': [
                            {'name': 'Agent3'},
                            {'name': 'Agent4'}
                        ],
                        'success_policy': 'any'
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
        assert chain.stages[0].success_policy == SuccessPolicy.ALL
        assert chain.stages[1].success_policy == SuccessPolicy.ANY
    
    def test_loading_yaml_chain_with_synthesis_config(self) -> None:
        """Test loading YAML chain with synthesis configuration for parallel stages."""
        yaml_chains = {
            'synthesis-chain': {
                'chain_id': 'synthesis-chain',
                'alert_types': ['synthesis-test'],
                'stages': [
                    {
                        'name': 'investigation',
                        'agent': None,
                        'agents': [
                            {'name': 'Agent1', 'iteration_strategy': 'react'},
                            {'name': 'Agent2', 'iteration_strategy': 'native-thinking'}
                        ],
                        'synthesis': {
                            'agent': 'SynthesisAgent',
                            'iteration_strategy': 'synthesis-native-thinking',
                            'llm_provider': 'google-default'
                        }
                    }
                ]
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'synthesis-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('synthesis-test')
        assert chain is not None
        assert chain.chain_id == 'synthesis-chain'
        assert len(chain.stages) == 1
        
        # Verify synthesis configuration is loaded
        stage = chain.stages[0]
        assert stage.synthesis is not None, "Synthesis config should be loaded"
        assert stage.synthesis.agent == 'SynthesisAgent'
        assert stage.synthesis.iteration_strategy.value == 'synthesis-native-thinking'
        assert stage.synthesis.llm_provider == 'google-default'
    
    def test_loading_yaml_chain_with_chat_config(self) -> None:
        """Test loading YAML chain with chat configuration."""
        yaml_chains = {
            'chat-chain': {
                'chain_id': 'chat-chain',
                'alert_types': ['chat-test'],
                'stages': [
                    {
                        'name': 'analysis',
                        'agent': 'TestAgent'
                    }
                ],
                'chat': {
                    'enabled': True,
                    'agent': 'CustomChatAgent',
                    'iteration_strategy': 'native-thinking',
                    'llm_provider': 'anthropic-default'
                }
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'chat-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('chat-test')
        assert chain is not None
        assert chain.chain_id == 'chat-chain'
        
        # Verify chat configuration is loaded
        assert chain.chat is not None, "Chat config should be loaded"
        assert chain.chat.enabled is True
        assert chain.chat.agent == 'CustomChatAgent'
        assert chain.chat.iteration_strategy.value == 'native-thinking'
        assert chain.chat.llm_provider == 'anthropic-default'
    
    def test_loading_yaml_chain_with_synthesis_missing_iteration_strategy(self) -> None:
        """Test loading YAML chain with synthesis config that omits iteration_strategy."""
        yaml_chains = {
            'synthesis-default-chain': {
                'chain_id': 'synthesis-default-chain',
                'alert_types': ['synthesis-default-test'],
                'stages': [
                    {
                        'name': 'investigation',
                        'agent': None,
                        'agents': [
                            {'name': 'Agent1'},
                            {'name': 'Agent2'}
                        ],
                        'synthesis': {
                            'agent': 'SynthesisAgent',
                            'llm_provider': 'openai'
                            # Note: iteration_strategy is intentionally omitted
                        }
                    }
                ]
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'synthesis-default-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('synthesis-default-test')
        assert chain is not None
        
        # Verify synthesis configuration uses default iteration_strategy
        stage = chain.stages[0]
        assert stage.synthesis is not None, "Synthesis config should be loaded"
        assert stage.synthesis.agent == 'SynthesisAgent'
        assert stage.synthesis.iteration_strategy.value == 'synthesis', "Should default to 'synthesis'"
        assert stage.synthesis.llm_provider == 'openai'
    
    def test_loading_yaml_chain_with_synthesis_and_chat(self) -> None:
        """Test loading YAML chain with both synthesis and chat configuration."""
        yaml_chains = {
            'full-chain': {
                'chain_id': 'full-chain',
                'alert_types': ['full-test'],
                'stages': [
                    {
                        'name': 'investigation',
                        'agent': None,
                        'agents': [
                            {'name': 'Agent1'},
                            {'name': 'Agent2'}
                        ],
                        'synthesis': {
                            'agent': 'SynthesisAgent',
                            'iteration_strategy': 'synthesis',
                            'llm_provider': 'openai'
                        }
                    }
                ],
                'chat': {
                    'enabled': True,
                    'iteration_strategy': 'react'
                }
            }
        }
        
        mock_config_loader = Mock(spec=ConfigurationLoader)
        mock_config_loader.get_chain_configs.return_value = yaml_chains
        mock_config = Mock()
        mock_config.default_alert_type = 'full-test'
        mock_config_loader.load_and_validate.return_value = mock_config
        
        with patch('tarsy.services.chain_registry.get_builtin_chain_definitions') as mock_builtin:
            mock_builtin.return_value = {}
            registry = ChainRegistry(mock_config_loader)
        
        chain = registry.get_chain_for_alert_type('full-test')
        assert chain is not None
        
        # Verify both synthesis and chat are loaded
        assert chain.stages[0].synthesis is not None
        assert chain.stages[0].synthesis.iteration_strategy.value == 'synthesis'
        assert chain.chat is not None
        assert chain.chat.enabled is True
        assert chain.chat.iteration_strategy.value == 'react'

