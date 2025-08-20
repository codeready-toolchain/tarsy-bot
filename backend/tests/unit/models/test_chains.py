"""
Unit tests for Chain models - ChainStageModel and ChainConfigModel.

Tests model creation, validation, serialization, and data access methods.
"""

import pytest
from pydantic import ValidationError

from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel


@pytest.mark.unit
class TestChainStageConfigModel:
    """Test ChainStageConfigModel functionality."""
    
    def test_basic_creation(self):
        """Test basic stage model creation."""
        stage = ChainStageConfigModel(
            name="data-collection",
            agent="KubernetesAgent"
        )
        
        assert stage.name == "data-collection"
        assert stage.agent == "KubernetesAgent"
        assert stage.iteration_strategy is None
    
    def test_creation_with_iteration_strategy(self):
        """Test stage creation with iteration strategy."""
        stage = ChainStageConfigModel(
            name="analysis",
            agent="KubernetesAgent",
            iteration_strategy="react"
        )
        
        assert stage.name == "analysis"
        assert stage.agent == "KubernetesAgent"
        assert stage.iteration_strategy == "react"
    
    def test_creation_with_configurable_agent(self):
        """Test stage creation with configurable agent syntax."""
        stage = ChainStageConfigModel(
            name="custom-analysis",
            agent="ConfigurableAgent:my-custom-agent",
            iteration_strategy="react"
        )
        
        assert stage.name == "custom-analysis"
        assert stage.agent == "ConfigurableAgent:my-custom-agent"
        assert stage.iteration_strategy == "react"
    
    @pytest.mark.parametrize("stage_data,expected_dict", [
        (
            {"name": "test-stage", "agent": "TestAgent", "iteration_strategy": "react"},
            {'name': 'test-stage', 'agent': 'TestAgent', 'iteration_strategy': 'react'}
        ),
        (
            {"name": "test-stage", "agent": "TestAgent"},
            {'name': 'test-stage', 'agent': 'TestAgent', 'iteration_strategy': None}
        ),
        (
            {"name": "custom-stage", "agent": "ConfigurableAgent:custom", "iteration_strategy": "react"},
            {'name': 'custom-stage', 'agent': 'ConfigurableAgent:custom', 'iteration_strategy': 'react'}
        )
    ])
    def test_to_dict_serialization(self, stage_data, expected_dict):
        """Test stage serialization to dictionary with various configurations."""
        stage = ChainStageConfigModel(**stage_data)
        result = stage.model_dump()
        assert result == expected_dict


@pytest.mark.unit
class TestChainConfigModel:
    """Test ChainConfigModel functionality."""
    
    def test_basic_creation(self):
        """Test basic chain definition creation."""
        stage = ChainStageConfigModel(name="analysis", agent="TestAgent")
        chain = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test-alert"],
            stages=[stage]
        )
        
        assert chain.chain_id == "test-chain"
        assert chain.alert_types == ["test-alert"]
        assert len(chain.stages) == 1
        assert chain.stages[0] == stage

    def test_required_fields_validation(self, model_validation_tester):
        """Test that required fields are enforced."""
        valid_data = {
            "chain_id": "test-chain",
            "alert_types": ["test-alert"],
            "stages": [ChainStageConfigModel(name="analysis", agent="TestAgent")]
        }
        
        required_fields = ["chain_id", "alert_types", "stages"]
        model_validation_tester.test_required_fields(ChainConfigModel, required_fields, valid_data)

    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that chain definition can be serialized and deserialized correctly."""
        # Create the model instance first
        chain = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test-alert"],
            stages=[ChainStageConfigModel(name="analysis", agent="TestAgent")],
            description="Test chain description"
        )
        
        # Test serialization to dict
        chain_dict = chain.model_dump()
        
        # Test that we can reconstruct the stages properly
        reconstructed_stages = [ChainStageConfigModel(**stage_dict) for stage_dict in chain_dict['stages']]
        
        # Create a new chain with reconstructed stages
        reconstructed_chain = ChainConfigModel(
            chain_id=chain_dict['chain_id'],
            alert_types=chain_dict['alert_types'],
            stages=reconstructed_stages,
            description=chain_dict['description']
        )
        
        # Verify they're equal
        assert chain == reconstructed_chain
    
    def test_creation_with_description(self):
        """Test chain creation with description."""
        stage = ChainStageConfigModel(name="analysis", agent="TestAgent")
        chain = ChainConfigModel(
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
            ChainStageConfigModel(name="data-collection", agent="DataAgent"),
            ChainStageConfigModel(name="analysis", agent="AnalysisAgent", iteration_strategy="react"),
            ChainStageConfigModel(name="response", agent="ResponseAgent")
        ]
        
        chain = ChainConfigModel(
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
            ChainStageConfigModel(name="stage1", agent="Agent1"),
            ChainStageConfigModel(name="stage2", agent="Agent2", iteration_strategy="react")
        ]
        
        chain = ChainConfigModel(
            chain_id="serialization-test",
            alert_types=["alert1", "alert2"],
            stages=stages,
            description="Test serialization"
        )
        
        result = chain.model_dump()
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
        stage = ChainStageConfigModel(name="test-stage", agent="TestAgent")
        chain = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage]
        )
        
        result = chain.model_dump()
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
        """Test chain with empty stages list should fail validation."""
        # This should raise a validation error due to min_length=1 constraint
        with pytest.raises(ValidationError) as exc_info:
            ChainConfigModel(
                chain_id="empty-chain",
                alert_types=["test"],
                stages=[]
            )
        
        assert "too_short" in str(exc_info.value)
    
    def test_empty_alert_types_list(self):
        """Test chain with empty alert types list should fail validation."""
        # This should raise a validation error due to min_length=1 constraint
        stage = ChainStageConfigModel(name="test", agent="TestAgent")
        with pytest.raises(ValidationError) as exc_info:
            ChainConfigModel(
                chain_id="no-alerts-chain",
                alert_types=[],
                stages=[stage]
            )
        
        assert "too_short" in str(exc_info.value)
    
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
            stage = ChainStageConfigModel(name=name, agent="TestAgent")
            assert stage.name == name
            assert stage.model_dump()['name'] == name
    
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
            stage = ChainStageConfigModel(name="test", agent=agent)
            assert stage.agent == agent
            assert stage.model_dump()['agent'] == agent


@pytest.mark.unit
class TestChainModelComplexScenarios:
    """Test complex scenarios and real-world usage patterns."""
    
    def test_kubernetes_troubleshooting_chain(self):
        """Test a realistic Kubernetes troubleshooting chain."""
        stages = [
            ChainStageConfigModel(
                name="data-collection",
                agent="KubernetesAgent",
                iteration_strategy="react"
            ),
            ChainStageConfigModel(
                name="log-analysis",
                agent="ConfigurableAgent:log-analyzer",
                iteration_strategy="react"
            ),
            ChainStageConfigModel(
                name="root-cause-analysis",
                agent="KubernetesAgent",
                iteration_strategy="react"
            ),
            ChainStageConfigModel(
                name="remediation-planning",
                agent="ConfigurableAgent:remediation-planner"
            )
        ]
        
        chain = ChainConfigModel(
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
        serialized = chain.model_dump()
        assert len(serialized['stages']) == 4
        assert serialized['stages'][0]['iteration_strategy'] == 'react'
        assert serialized['stages'][1]['agent'] == 'ConfigurableAgent:log-analyzer'
        assert serialized['stages'][3]['iteration_strategy'] is None
    
    def test_single_stage_chain_conversion(self):
        """Test that single-agent workflows become single-stage chains."""
        stage = ChainStageConfigModel(
            name="analysis",
            agent="KubernetesAgent"
        )
        
        chain = ChainConfigModel(
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
            ChainStageConfigModel(name="builtin-stage", agent="KubernetesAgent"),
            ChainStageConfigModel(name="configurable-stage1", agent="ConfigurableAgent:custom1"),
            ChainStageConfigModel(name="configurable-stage2", agent="ConfigurableAgent:custom2"),
            ChainStageConfigModel(name="another-builtin", agent="SomeOtherBuiltinAgent")
        ]
        
        chain = ChainConfigModel(
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
        serialized = chain.model_dump()
        agent_ids = [stage['agent'] for stage in serialized['stages']]
        assert "KubernetesAgent" in agent_ids
        assert "ConfigurableAgent:custom1" in agent_ids
        assert "ConfigurableAgent:custom2" in agent_ids
