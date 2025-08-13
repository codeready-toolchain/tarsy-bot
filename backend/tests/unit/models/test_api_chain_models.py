"""
Unit tests for chain-related API models.

Tests StageExecution, ChainExecution and other API response models
used for chain functionality.
"""

import pytest
from pydantic import ValidationError
from tarsy.models.api_models import StageExecution, ChainExecution
from tests.utils import ModelValidationTester, TestUtils


@pytest.mark.unit
class TestStageExecutionAPIModel:
    """Test StageExecution API model."""
    
    def test_basic_creation(self):
        """Test basic stage execution creation."""
        stage = StageExecution(
            execution_id="exec_123",
            stage_id="data-collection",
            stage_index=0,
            stage_name="Data Collection",
            agent="KubernetesAgent",
            status="pending"
        )
        
        assert stage.execution_id == "exec_123"
        assert stage.stage_id == "data-collection"
        assert stage.stage_index == 0
        assert stage.stage_name == "Data Collection"
        assert stage.agent == "KubernetesAgent"
        assert stage.status == "pending"
        assert stage.iteration_strategy is None
        assert stage.started_at_us is None
        assert stage.completed_at_us is None
        assert stage.duration_ms is None
    
    def test_creation_with_all_fields(self):
        """Test stage execution with all fields."""
        stage = StageExecution(
            execution_id="exec_456",
            stage_id="analysis",
            stage_index=1,
            stage_name="Root Cause Analysis",
            agent="ConfigurableAgent:analyzer",
            iteration_strategy="react",
            status="completed",
            started_at_us=1234567890000000,
            completed_at_us=1234567895000000,
            duration_ms=5000,
            stage_output={"analysis": "Found root cause", "confidence": 0.95},
            error_message=None
        )
        
        assert stage.execution_id == "exec_456"
        assert stage.stage_name == "Root Cause Analysis"
        assert stage.agent == "ConfigurableAgent:analyzer"
        assert stage.iteration_strategy == "react"
        assert stage.status == "completed"
        assert stage.started_at_us == 1234567890000000
        assert stage.completed_at_us == 1234567895000000
        assert stage.duration_ms == 5000
        assert stage.stage_output["analysis"] == "Found root cause"
        assert stage.stage_output["confidence"] == 0.95
        assert stage.error_message is None
    
    def test_creation_with_error(self):
        """Test stage execution with error."""
        stage = StageExecution(
            execution_id="exec_error",
            stage_id="failed-stage",
            stage_index=2,
            stage_name="Failed Analysis",
            agent="UnreliableAgent",
            status="failed",
            started_at_us=1234567890000000,
            completed_at_us=1234567892000000,
            duration_ms=2000,
            stage_output=None,
            error_message="Agent execution timeout"
        )
        
        assert stage.status == "failed"
        assert stage.stage_output is None
        assert stage.error_message == "Agent execution timeout"
        assert stage.duration_ms == 2000
    
    def test_configurable_agent_syntax(self):
        """Test stage execution with configurable agent."""
        stage = StageExecution(
            execution_id="exec_config",
            stage_id="custom-analysis", 
            stage_index=0,
            stage_name="Custom Analysis",
            agent="ConfigurableAgent:my-custom-agent",
            status="active"
        )
        
        assert stage.agent == "ConfigurableAgent:my-custom-agent"
        assert ":" in stage.agent
    
    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that stage execution can be serialized and deserialized correctly."""
        valid_data = {
            "execution_id": "exec_serialize",
            "stage_id": "serialize-test",
            "stage_index": 1,
            "stage_name": "Serialization Test",
            "agent": "TestAgent",
            "status": "completed",
            "duration_ms": 1500,
            "stage_output": {"test": "result"}
        }
        
        model_test_helpers.test_serialization_roundtrip(StageExecution, valid_data)


@pytest.mark.unit
class TestChainExecutionAPIModel:
    """Test ChainExecution API model."""
    
    def test_basic_creation(self):
        """Test basic chain execution creation."""
        stage1 = StageExecution(
            execution_id="exec_1",
            stage_id="stage1",
            stage_index=0,
            stage_name="Stage 1",
            agent="Agent1",
            status="completed"
        )
        
        stage2 = StageExecution(
            execution_id="exec_2",
            stage_id="stage2",
            stage_index=1,
            stage_name="Stage 2",
            agent="Agent2",
            status="active"
        )
        
        chain = ChainExecution(
            chain_id="test-chain",
            chain_definition={"chain_id": "test-chain", "stages": []},
            stages=[stage1, stage2]
        )
        
        assert chain.chain_id == "test-chain"
        assert len(chain.stages) == 2
        assert chain.current_stage_index is None
        assert chain.current_stage_id is None
        assert chain.chain_definition["chain_id"] == "test-chain"
    
    def test_creation_with_current_stage(self):
        """Test chain execution with current stage tracking."""
        stage1 = StageExecution(
            execution_id="exec_1",
            stage_id="data-collection",
            stage_index=0,
            stage_name="Data Collection",
            agent="KubernetesAgent",
            status="completed"
        )
        
        stage2 = StageExecution(
            execution_id="exec_2", 
            stage_id="analysis",
            stage_index=1,
            stage_name="Analysis",
            agent="KubernetesAgent",
            status="active"
        )
        
        chain_definition = {
            "chain_id": "kubernetes-troubleshooting",
            "alert_types": ["kubernetes"],
            "stages": [
                {"name": "data-collection", "agent": "KubernetesAgent"},
                {"name": "analysis", "agent": "KubernetesAgent"}
            ]
        }
        
        chain = ChainExecution(
            chain_id="kubernetes-troubleshooting",
            chain_definition=chain_definition,
            current_stage_index=1,
            current_stage_id="analysis",
            stages=[stage1, stage2]
        )
        
        assert chain.current_stage_index == 1
        assert chain.current_stage_id == "analysis"
        assert len(chain.stages) == 2
        assert chain.stages[1].status == "active"
    
    def test_multi_stage_chain(self):
        """Test chain execution with multiple stages."""
        stages = []
        for i in range(4):
            stage = StageExecution(
                execution_id=f"exec_{i}",
                stage_id=f"stage_{i}",
                stage_index=i,
                stage_name=f"Stage {i+1}",
                agent=f"Agent{i+1}",
                status="pending" if i > 1 else "completed"
            )
            stages.append(stage)
        
        chain_definition = {
            "chain_id": "multi-stage-chain",
            "alert_types": ["complex"],
            "stages": [{"name": f"stage_{i}", "agent": f"Agent{i+1}"} for i in range(4)]
        }
        
        chain = ChainExecution(
            chain_id="multi-stage-chain",
            chain_definition=chain_definition,
            current_stage_index=2,
            current_stage_id="stage_2",
            stages=stages
        )
        
        assert len(chain.stages) == 4
        assert chain.current_stage_index == 2
        assert chain.stages[0].status == "completed"
        assert chain.stages[1].status == "completed"  
        assert chain.stages[2].status == "pending"
        assert chain.stages[3].status == "pending"
    
    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that chain execution can be serialized and deserialized correctly."""
        stage = StageExecution(
            execution_id="exec_test",
            stage_id="test-stage",
            stage_index=0,
            stage_name="Test Stage",
            agent="TestAgent",
            status="completed",
            stage_output={"result": "success"}
        )
        
        valid_data = {
            "chain_id": "serialization-test",
            "chain_definition": {
                "chain_id": "serialization-test",
                "description": "Test chain"
            },
            "current_stage_index": 0,
            "current_stage_id": "test-stage",
            "stages": [stage]
        }
        
        model_test_helpers.test_serialization_roundtrip(ChainExecution, valid_data)


@pytest.mark.unit
class TestAPIModelValidation:
    """Test validation and edge cases for API models."""
    
    def test_stage_execution_required_fields(self, model_validation_tester):
        """Test that required fields are validated."""
        valid_data = {
            "execution_id": "exec_123",
            "stage_id": "data-collection",
            "stage_index": 0,
            "stage_name": "Data Collection",
            "agent": "KubernetesAgent",
            "status": "pending"
        }
        
        required_fields = ["execution_id", "stage_id", "stage_index", "stage_name", "agent", "status"]
        model_validation_tester.test_required_fields(StageExecution, required_fields, valid_data)
    
    def test_chain_execution_required_fields(self, model_validation_tester):
        """Test that chain execution requires necessary fields."""
        stage = StageExecution(
            execution_id="exec_1",
            stage_id="stage1",
            stage_index=0,
            stage_name="Stage 1",
            agent="Agent1",
            status="completed"
        )
        
        valid_data = {
            "chain_id": "test-chain",
            "chain_definition": {"chain_id": "test-chain", "stages": []},
            "stages": [stage]
        }
        
        required_fields = ["chain_id", "chain_definition", "stages"]
        model_validation_tester.test_required_fields(ChainExecution, required_fields, valid_data)
    
    def test_empty_stages_list(self):
        """Test chain execution with empty stages list."""
        chain = ChainExecution(
            chain_id="empty-chain",
            chain_definition={"chain_id": "empty-chain"},
            stages=[]
        )
        
        assert len(chain.stages) == 0
        assert chain.chain_id == "empty-chain"
    
    def test_negative_stage_index(self):
        """Test stage execution with negative index."""
        # This should be allowed by the model but may be invalid in business logic
        stage = StageExecution(
            execution_id="negative_test",
            stage_id="test",
            stage_index=-1,  # Negative index
            stage_name="Test",
            agent="TestAgent",
            status="pending"
        )
        
        assert stage.stage_index == -1


@pytest.mark.unit
class TestAPIModelIntegration:
    """Test integration scenarios for API models."""
    
    def test_kubernetes_troubleshooting_chain_api(self):
        """Test realistic Kubernetes troubleshooting chain API representation."""
        # Create stages representing a realistic troubleshooting workflow
        data_collection = StageExecution(
            execution_id="exec_dc_001",
            stage_id="data-collection",
            stage_index=0,
            stage_name="Data Collection",
            agent="KubernetesAgent",
            iteration_strategy="regular",
            status="completed",
            started_at_us=1000000000,
            completed_at_us=1000005000,
            duration_ms=5000,
            stage_output={
                "pods_collected": 5,
                "events_collected": 12,
                "logs_collected": 3
            }
        )
        
        analysis = StageExecution(
            execution_id="exec_an_002",
            stage_id="analysis",
            stage_index=1,
            stage_name="Root Cause Analysis",
            agent="KubernetesAgent",
            iteration_strategy="react",
            status="completed",
            started_at_us=1000005000,
            completed_at_us=1000015000,
            duration_ms=10000,
            stage_output={
                "root_cause": "Resource exhaustion",
                "confidence": 0.92,
                "evidence": ["High CPU usage", "Memory pressure"]
            }
        )
        
        remediation = StageExecution(
            execution_id="exec_rem_003",
            stage_id="remediation",
            stage_index=2,
            stage_name="Remediation Planning",
            agent="ConfigurableAgent:remediation-planner",
            status="active",
            started_at_us=1000015000,
            completed_at_us=None,
            duration_ms=None
        )
        
        chain_definition = {
            "chain_id": "kubernetes-troubleshooting-chain",
            "alert_types": ["PodFailure", "ServiceDown"],
            "stages": [
                {"name": "data-collection", "agent": "KubernetesAgent", "iteration_strategy": "regular"},
                {"name": "analysis", "agent": "KubernetesAgent", "iteration_strategy": "react"},
                {"name": "remediation", "agent": "ConfigurableAgent:remediation-planner"}
            ],
            "description": "Comprehensive Kubernetes issue resolution workflow"
        }
        
        chain = ChainExecution(
            chain_id="kubernetes-troubleshooting-chain",
            chain_definition=chain_definition,
            current_stage_index=2,
            current_stage_id="remediation",
            stages=[data_collection, analysis, remediation]
        )
        
        # Verify the complete chain structure
        assert len(chain.stages) == 3
        assert chain.current_stage_index == 2
        assert chain.current_stage_id == "remediation"
        
        # Verify completed stages have output
        assert chain.stages[0].stage_output["pods_collected"] == 5
        assert chain.stages[1].stage_output["root_cause"] == "Resource exhaustion"
        
        # Verify active stage has no completion data
        assert chain.stages[2].completed_at_us is None
        assert chain.stages[2].stage_output is None
        
        # Verify serialization works
        serialized = chain.dict()
        assert serialized["chain_definition"]["description"] == "Comprehensive Kubernetes issue resolution workflow"
        assert len(serialized["stages"]) == 3
    
    def test_chain_with_failures(self):
        """Test chain execution with failed stages."""
        successful_stage = StageExecution(
            execution_id="exec_success",
            stage_id="success-stage",
            stage_index=0,
            stage_name="Successful Stage",
            agent="ReliableAgent",
            status="completed",
            duration_ms=2000,
            stage_output={"result": "success"}
        )
        
        failed_stage = StageExecution(
            execution_id="exec_fail",
            stage_id="failed-stage", 
            stage_index=1,
            stage_name="Failed Stage",
            agent="UnreliableAgent",
            status="failed",
            duration_ms=1000,
            stage_output=None,
            error_message="Agent execution timeout after 30 seconds"
        )
        
        chain = ChainExecution(
            chain_id="failure-test-chain",
            chain_definition={"chain_id": "failure-test-chain"},
            current_stage_index=1,
            current_stage_id="failed-stage",
            stages=[successful_stage, failed_stage]
        )
        
        # Verify mixed success/failure handling
        assert chain.stages[0].status == "completed"
        assert chain.stages[0].stage_output is not None
        assert chain.stages[1].status == "failed"
        assert chain.stages[1].stage_output is None
        assert chain.stages[1].error_message is not None
