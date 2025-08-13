"""
Unit tests for Chain models - ChainStageModel and ChainDefinitionModel.

Tests model creation, validation, serialization, and data access methods.
"""

import pytest
from tarsy.models.chains import ChainStageModel, ChainDefinitionModel


@pytest.mark.unit
class TestChainStageModel:
    """Test ChainStageModel functionality."""
    
    def test_basic_creation(self):
        """Test basic stage model creation."""
        stage = ChainStageModel(
            name="data-collection",
            agent="KubernetesAgent"
        )
        
        assert stage.name == "data-collection"
        assert stage.agent == "KubernetesAgent"
        assert stage.iteration_strategy is None
    
    def test_creation_with_iteration_strategy(self):
        """Test stage creation with iteration strategy."""
        stage = ChainStageModel(
            name="analysis",
            agent="KubernetesAgent",
            iteration_strategy="react"
        )
        
        assert stage.name == "analysis"
        assert stage.agent == "KubernetesAgent"
        assert stage.iteration_strategy == "react"
    
    def test_creation_with_configurable_agent(self):
        """Test stage creation with configurable agent syntax."""
        stage = ChainStageModel(
            name="custom-analysis",
            agent="ConfigurableAgent:my-custom-agent",
            iteration_strategy="regular"
        )
        
        assert stage.name == "custom-analysis"
        assert stage.agent == "ConfigurableAgent:my-custom-agent"
        assert stage.iteration_strategy == "regular"
    
    def test_to_dict_serialization(self):
        """Test stage serialization to dictionary."""
        stage = ChainStageModel(
            name="test-stage",
            agent="TestAgent",
            iteration_strategy="react"
        )
        
        result = stage.to_dict()
        expected = {
            'name': 'test-stage',
            'agent': 'TestAgent',
            'iteration_strategy': 'react'
        }
        
        assert result == expected
    
    def test_to_dict_serialization_none_strategy(self):
        """Test stage serialization with None strategy."""
        stage = ChainStageModel(
            name="test-stage",
            agent="TestAgent"
        )
        
        result = stage.to_dict()
        expected = {
            'name': 'test-stage',
            'agent': 'TestAgent',
            'iteration_strategy': None
        }
        
        assert result == expected


@pytest.mark.unit
class TestChainDefinitionModel:
    """Test ChainDefinitionModel functionality."""
    
    def test_basic_creation(self):
        """Test basic chain definition creation."""
        stage = ChainStageModel(name="analysis", agent="TestAgent")
        chain = ChainDefinitionModel(
            chain_id="test-chain",
            alert_types=["test-alert"],
            stages=[stage]
        )
        
        assert chain.chain_id == "test-chain"
        assert chain.alert_types == ["test-alert"]
        assert len(chain.stages) == 1
        assert chain.stages[0] == stage
        assert chain.description is None
    
    def test_creation_with_description(self):
        """Test chain creation with description."""
        stage = ChainStageModel(name="analysis", agent="TestAgent")
        chain = ChainDefinitionModel(
            chain_id="test-chain",
            alert_types=["test1", "test2"],
            stages=[stage],
            description="Test chain description"
        )
        
        assert chain.description == "Test chain description"
        assert len(chain.alert_types) == 2
    
    def test_multi_stage_chain(self):
        """Test chain with multiple stages."""
        stages = [
            ChainStageModel(name="data-collection", agent="DataAgent"),
            ChainStageModel(name="analysis", agent="AnalysisAgent", iteration_strategy="react"),
            ChainStageModel(name="response", agent="ResponseAgent")
        ]
        
        chain = ChainDefinitionModel(
            chain_id="multi-stage-chain",
            alert_types=["kubernetes", "pod-failure"],
            stages=stages,
            description="Multi-stage processing chain"
        )
        
        assert len(chain.stages) == 3
        assert chain.stages[0].name == "data-collection"
        assert chain.stages[1].name == "analysis"
        assert chain.stages[1].iteration_strategy == "react"
        assert chain.stages[2].name == "response"
    
    def test_to_dict_serialization(self):
        """Test chain definition serialization to dictionary."""
        stages = [
            ChainStageModel(name="stage1", agent="Agent1"),
            ChainStageModel(name="stage2", agent="Agent2", iteration_strategy="react")
        ]
        
        chain = ChainDefinitionModel(
            chain_id="serialization-test",
            alert_types=["alert1", "alert2"],
            stages=stages,
            description="Test serialization"
        )
        
        result = chain.to_dict()
        expected = {
            'chain_id': 'serialization-test',
            'alert_types': ['alert1', 'alert2'],
            'stages': [
                {'name': 'stage1', 'agent': 'Agent1', 'iteration_strategy': None},
                {'name': 'stage2', 'agent': 'Agent2', 'iteration_strategy': 'react'}
            ],
            'description': 'Test serialization'
        }
        
        assert result == expected
    
    def test_to_dict_serialization_none_description(self):
        """Test chain serialization with None description."""
        stage = ChainStageModel(name="test-stage", agent="TestAgent")
        chain = ChainDefinitionModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage]
        )
        
        result = chain.to_dict()
        expected = {
            'chain_id': 'test-chain',
            'alert_types': ['test'],
            'stages': [
                {'name': 'test-stage', 'agent': 'TestAgent', 'iteration_strategy': None}
            ],
            'description': None
        }
        
        assert result == expected


@pytest.mark.unit
class TestChainModelValidation:
    """Test validation and edge cases for chain models."""
    
    def test_empty_stages_list(self):
        """Test chain with empty stages list."""
        # This should be allowed by the model but may be invalid in business logic
        chain = ChainDefinitionModel(
            chain_id="empty-chain",
            alert_types=["test"],
            stages=[]
        )
        
        assert len(chain.stages) == 0
        assert chain.to_dict()['stages'] == []
    
    def test_empty_alert_types_list(self):
        """Test chain with empty alert types list."""
        stage = ChainStageModel(name="test", agent="TestAgent")
        chain = ChainDefinitionModel(
            chain_id="no-alerts-chain",
            alert_types=[],
            stages=[stage]
        )
        
        assert len(chain.alert_types) == 0
        assert chain.to_dict()['alert_types'] == []
    
    def test_stage_name_variations(self):
        """Test stage names with various formats."""
        test_names = [
            "simple",
            "hyphen-separated",
            "underscore_separated",
            "Mixed Case Name",
            "with123numbers",
            "special!@#chars"
        ]
        
        for name in test_names:
            stage = ChainStageModel(name=name, agent="TestAgent")
            assert stage.name == name
            assert stage.to_dict()['name'] == name
    
    def test_agent_identifier_variations(self):
        """Test agent identifiers with various formats."""
        test_agents = [
            "SimpleAgent",
            "KubernetesAgent",
            "ConfigurableAgent:my-agent",
            "ConfigurableAgent:hyphen-agent",
            "ConfigurableAgent:underscore_agent",
            "ConfigurableAgent:with.dots.agent"
        ]
        
        for agent in test_agents:
            stage = ChainStageModel(name="test", agent=agent)
            assert stage.agent == agent
            assert stage.to_dict()['agent'] == agent


@pytest.mark.unit
class TestChainModelComplexScenarios:
    """Test complex scenarios and real-world usage patterns."""
    
    def test_kubernetes_troubleshooting_chain(self):
        """Test a realistic Kubernetes troubleshooting chain."""
        stages = [
            ChainStageModel(
                name="data-collection",
                agent="KubernetesAgent",
                iteration_strategy="regular"
            ),
            ChainStageModel(
                name="log-analysis",
                agent="ConfigurableAgent:log-analyzer",
                iteration_strategy="react"
            ),
            ChainStageModel(
                name="root-cause-analysis",
                agent="KubernetesAgent",
                iteration_strategy="react"
            ),
            ChainStageModel(
                name="remediation-planning",
                agent="ConfigurableAgent:remediation-planner"
            )
        ]
        
        chain = ChainDefinitionModel(
            chain_id="kubernetes-troubleshooting-chain",
            alert_types=["PodFailure", "ServiceDown", "NamespaceTerminating"],
            stages=stages,
            description="Comprehensive Kubernetes issue resolution workflow"
        )
        
        # Verify structure
        assert len(chain.stages) == 4
        assert len(chain.alert_types) == 3
        assert "Comprehensive" in chain.description
        
        # Verify serialization works
        serialized = chain.to_dict()
        assert len(serialized['stages']) == 4
        assert serialized['stages'][0]['iteration_strategy'] == 'regular'
        assert serialized['stages'][1]['agent'] == 'ConfigurableAgent:log-analyzer'
        assert serialized['stages'][3]['iteration_strategy'] is None
    
    def test_single_stage_chain_conversion(self):
        """Test that single-agent workflows become single-stage chains."""
        stage = ChainStageModel(
            name="analysis",
            agent="KubernetesAgent"
        )
        
        chain = ChainDefinitionModel(
            chain_id="kubernetes-agent-chain",
            alert_types=["kubernetes", "NamespaceTerminating"],
            stages=[stage],
            description="Single-stage Kubernetes analysis"
        )
        
        # This represents the conversion of existing single-agent workflows
        assert len(chain.stages) == 1
        assert chain.stages[0].name == "analysis"
        assert "kubernetes" in chain.alert_types
        assert "NamespaceTerminating" in chain.alert_types
    
    def test_chain_with_mixed_agent_types(self):
        """Test chain mixing built-in and configurable agents."""
        stages = [
            ChainStageModel(name="builtin-stage", agent="KubernetesAgent"),
            ChainStageModel(name="configurable-stage1", agent="ConfigurableAgent:custom1"),
            ChainStageModel(name="configurable-stage2", agent="ConfigurableAgent:custom2"),
            ChainStageModel(name="another-builtin", agent="SomeOtherBuiltinAgent")
        ]
        
        chain = ChainDefinitionModel(
            chain_id="mixed-agents-chain",
            alert_types=["mixed-processing"],
            stages=stages
        )
        
        # Verify mixed agent types
        builtin_agents = [s for s in chain.stages if not s.agent.startswith("ConfigurableAgent:")]
        configurable_agents = [s for s in chain.stages if s.agent.startswith("ConfigurableAgent:")]
        
        assert len(builtin_agents) == 2
        assert len(configurable_agents) == 2
        
        # Verify serialization preserves agent identifiers
        serialized = chain.to_dict()
        agent_ids = [stage['agent'] for stage in serialized['stages']]
        assert "KubernetesAgent" in agent_ids
        assert "ConfigurableAgent:custom1" in agent_ids
        assert "ConfigurableAgent:custom2" in agent_ids
