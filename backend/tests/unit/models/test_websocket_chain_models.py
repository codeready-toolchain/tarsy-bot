"""
Unit tests for chain-related WebSocket models.

Tests ChainProgressUpdate, StageProgressUpdate and related WebSocket functionality
for sequential agent chains.
"""

import pytest
from pydantic import ValidationError
from tarsy.models.websocket_models import (
    ChainProgressUpdate, StageProgressUpdate, ChannelType
)
from tests.utils import ModelValidationTester, TestUtils


@pytest.mark.unit
class TestChainProgressUpdate:
    """Test ChainProgressUpdate WebSocket message model."""
    
    def test_basic_creation(self):
        """Test basic chain progress update creation."""
        update = ChainProgressUpdate(
            session_id="session_123",
            chain_id="kubernetes-chain"
        )
        
        assert update.type == "chain_progress"
        assert update.session_id == "session_123"
        assert update.chain_id == "kubernetes-chain"
        assert update.overall_status == "processing"  # Default value
        assert update.current_stage is None
        assert update.current_stage_index is None
        assert update.total_stages is None
    
    def test_creation_with_all_fields(self):
        """Test chain progress update with all fields."""
        update = ChainProgressUpdate(
            session_id="session_456",
            chain_id="troubleshooting-chain",
            current_stage="analysis",
            current_stage_index=1,
            total_stages=3,
            completed_stages=1,
            failed_stages=0,
            overall_status="processing",
            stage_details={"agent": "KubernetesAgent", "started_at": 1234567890},
            channel="session_456"
        )
        
        assert update.session_id == "session_456"
        assert update.chain_id == "troubleshooting-chain"
        assert update.current_stage == "analysis"
        assert update.current_stage_index == 1
        assert update.total_stages == 3
        assert update.completed_stages == 1
        assert update.failed_stages == 0
        assert update.overall_status == "processing"
        assert update.stage_details["agent"] == "KubernetesAgent"
        assert update.channel == "session_456"
    
    @pytest.mark.parametrize("valid_status", [
        "pending", "processing", "completed", "failed", "partial"
    ])
    def test_valid_status_values(self, valid_status):
        """Test valid overall status values."""
        update = ChainProgressUpdate(
            session_id="test_session",
            chain_id="test_chain",
            overall_status=valid_status
        )
        assert update.overall_status == valid_status

    def test_invalid_status(self):
        """Test invalid overall status raises validation error."""
        with pytest.raises(ValidationError):
            ChainProgressUpdate(
                session_id="test_session",
                chain_id="test_chain",
                overall_status="invalid_status"
            )
    
    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that chain progress update can be serialized and deserialized correctly."""
        valid_data = {
            "session_id": "session_789",
            "chain_id": "multi-stage-chain",
            "current_stage": "data-collection",
            "current_stage_index": 0,
            "total_stages": 4,
            "completed_stages": 0,
            "overall_status": "processing"
        }
        
        model_test_helpers.test_serialization_roundtrip(ChainProgressUpdate, valid_data)


@pytest.mark.unit
class TestStageProgressUpdate:
    """Test StageProgressUpdate WebSocket message model."""
    
    def test_basic_creation(self):
        """Test basic stage progress update creation."""
        update = StageProgressUpdate(
            session_id="session_123",
            chain_id="kubernetes-chain",
            stage_execution_id="stage_exec_456",
            stage_name="data-collection",
            stage_index=0,
            agent="KubernetesAgent"
        )
        
        assert update.type == "stage_progress"
        assert update.session_id == "session_123"
        assert update.chain_id == "kubernetes-chain"
        assert update.stage_execution_id == "stage_exec_456"
        assert update.stage_name == "data-collection"
        assert update.stage_index == 0
        assert update.agent == "KubernetesAgent"
        assert update.status == "pending"  # Default value
    
    def test_creation_with_all_fields(self):
        """Test stage progress update with all fields."""
        update = StageProgressUpdate(
            session_id="session_789",
            chain_id="troubleshooting-chain",
            stage_execution_id="stage_exec_999",
            stage_name="root-cause-analysis",
            stage_index=2,
            agent="ConfigurableAgent:analyzer",
            status="active",
            started_at_us=1234567890000000,
            completed_at_us=1234567890500000,
            duration_ms=500,
            error_message=None,
            iteration_strategy="react",
            channel="session_789"
        )
        
        assert update.stage_name == "root-cause-analysis"
        assert update.stage_index == 2
        assert update.agent == "ConfigurableAgent:analyzer"
        assert update.status == "active"
        assert update.started_at_us == 1234567890000000
        assert update.completed_at_us == 1234567890500000
        assert update.duration_ms == 500
        assert update.error_message is None
        assert update.iteration_strategy == "react"
        assert update.channel == "session_789"
    
    @pytest.mark.parametrize("valid_status", [
        "pending", "active", "completed", "failed"
    ])
    def test_valid_status_values(self, valid_status):
        """Test valid stage status values."""
        update = StageProgressUpdate(
            session_id="test_session",
            chain_id="test_chain",
            stage_execution_id="test_exec",
            stage_name="test_stage",
            stage_index=0,
            agent="TestAgent",
            status=valid_status
        )
        assert update.status == valid_status

    def test_invalid_status(self):
        """Test invalid stage status raises validation error."""
        with pytest.raises(ValidationError):
            StageProgressUpdate(
                session_id="test_session",
                chain_id="test_chain",
                stage_execution_id="test_exec",
                stage_name="test_stage",
                stage_index=0,
                agent="TestAgent",
                status="invalid_status"
            )
    
    def test_with_error_message(self):
        """Test stage progress update with error."""
        update = StageProgressUpdate(
            session_id="session_error",
            chain_id="failed-chain",
            stage_execution_id="stage_failed",
            stage_name="failed-stage",
            stage_index=1,
            agent="FailingAgent",
            status="failed",
            error_message="Agent execution failed: timeout"
        )
        
        assert update.status == "failed"
        assert update.error_message == "Agent execution failed: timeout"
    
    def test_configurable_agent_identifier(self):
        """Test stage progress with configurable agent identifier."""
        update = StageProgressUpdate(
            session_id="session_config",
            chain_id="configurable-chain",
            stage_execution_id="stage_config",
            stage_name="custom-analysis",
            stage_index=0,
            agent="ConfigurableAgent:my-custom-agent",
            iteration_strategy="regular"
        )
        
        assert update.agent == "ConfigurableAgent:my-custom-agent"
        assert update.iteration_strategy == "regular"
    
    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that stage progress update can be serialized and deserialized correctly."""
        valid_data = {
            "session_id": "session_serialize",
            "chain_id": "serialize-chain",
            "stage_execution_id": "stage_serialize",
            "stage_name": "serialization-test",
            "stage_index": 1,
            "agent": "SerializeAgent",
            "status": "completed",
            "started_at_us": 1000000,
            "completed_at_us": 2000000,
            "duration_ms": 1000
        }
        
        model_test_helpers.test_serialization_roundtrip(StageProgressUpdate, valid_data)


@pytest.mark.unit
class TestChannelTypeChainSupport:
    """Test ChannelType utility functions for chain WebSocket routing."""
    
    def test_session_channel_generation(self):
        """Test session channel name generation."""
        channel = ChannelType.session_channel("session_123")
        assert channel == "session_session_123"
        
        channel2 = ChannelType.session_channel("abc-def-456")
        assert channel2 == "session_abc-def-456"
    
    def test_is_session_channel_detection(self):
        """Test session channel detection."""
        assert ChannelType.is_session_channel("session_123") is True
        assert ChannelType.is_session_channel("session_abc-def") is True
        assert ChannelType.is_session_channel("dashboard_updates") is False
        assert ChannelType.is_session_channel("system_health") is False
        assert ChannelType.is_session_channel("random_channel") is False
    
    def test_extract_session_id(self):
        """Test session ID extraction from channel names."""
        session_id = ChannelType.extract_session_id("session_123")
        assert session_id == "123"
        
        session_id2 = ChannelType.extract_session_id("session_abc-def-456")
        assert session_id2 == "abc-def-456"
        
        # Non-session channels should return None
        assert ChannelType.extract_session_id("dashboard_updates") is None
        assert ChannelType.extract_session_id("system_health") is None
        assert ChannelType.extract_session_id("not_a_session") is None


@pytest.mark.unit
class TestChainWebSocketIntegration:
    """Test integration scenarios for chain WebSocket messages."""
    
    def test_chain_execution_message_flow(self):
        """Test typical message flow for chain execution."""
        session_id = "integration_session"
        chain_id = "integration-chain"
        
        # 1. Chain starts - overall progress update
        chain_start = ChainProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            current_stage="data-collection",
            current_stage_index=0,
            total_stages=3,
            completed_stages=0,
            overall_status="processing"
        )
        
        # 2. First stage starts
        stage1_start = StageProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            stage_execution_id="exec_001",
            stage_name="data-collection",
            stage_index=0,
            agent="KubernetesAgent",
            status="active"
        )
        
        # 3. First stage completes
        stage1_complete = StageProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            stage_execution_id="exec_001",
            stage_name="data-collection",
            stage_index=0,
            agent="KubernetesAgent",
            status="completed",
            duration_ms=5000
        )
        
        # 4. Chain progress after first stage
        chain_progress = ChainProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            current_stage="analysis",
            current_stage_index=1,
            total_stages=3,
            completed_stages=1,
            overall_status="processing"
        )
        
        # Verify all messages are valid and consistent
        assert chain_start.session_id == stage1_start.session_id == stage1_complete.session_id
        assert chain_start.chain_id == stage1_start.chain_id == stage1_complete.chain_id
        assert stage1_start.stage_index == stage1_complete.stage_index == 0
        assert chain_progress.completed_stages == 1
        assert chain_progress.current_stage_index == 1
    
    def test_multi_stage_chain_tracking(self):
        """Test message tracking for multi-stage chain execution."""
        session_id = "multi_stage_session"
        chain_id = "kubernetes-troubleshooting-chain"
        
        stages = [
            ("data-collection", "KubernetesAgent"),
            ("log-analysis", "ConfigurableAgent:log-analyzer"), 
            ("root-cause-analysis", "KubernetesAgent"),
            ("remediation", "ConfigurableAgent:remediation-planner")
        ]
        
        # Create stage progress updates for all stages
        for i, (stage_name, agent) in enumerate(stages):
            stage_update = StageProgressUpdate(
                session_id=session_id,
                chain_id=chain_id,
                stage_execution_id=f"exec_{i:03d}",
                stage_name=stage_name,
                stage_index=i,
                agent=agent,
                status="pending"
            )
            
            assert stage_update.stage_index == i
            assert stage_update.stage_name == stage_name
            assert stage_update.agent == agent
            
            # Test configurable agent handling
            if agent.startswith("ConfigurableAgent:"):
                assert ":" in stage_update.agent
            else:
                assert ":" not in stage_update.agent
        
        # Test final chain progress
        final_progress = ChainProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            current_stage=None,  # All stages complete
            total_stages=len(stages),
            completed_stages=len(stages),
            failed_stages=0,
            overall_status="completed"
        )
        
        assert final_progress.total_stages == 4
        assert final_progress.completed_stages == 4
        assert final_progress.overall_status == "completed"
    
    def test_error_handling_in_chain_messages(self):
        """Test error scenarios in chain WebSocket messages."""
        session_id = "error_session" 
        chain_id = "error-prone-chain"
        
        # Stage that fails
        failed_stage = StageProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            stage_execution_id="exec_error",
            stage_name="failing-stage",
            stage_index=1,
            agent="UnreliableAgent",
            status="failed",
            error_message="Agent execution timeout after 30 seconds"
        )
        
        # Chain progress reflects the failure
        chain_failure = ChainProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            current_stage="failing-stage",
            current_stage_index=1,
            total_stages=3,
            completed_stages=1,
            failed_stages=1,
            overall_status="partial"
        )
        
        assert failed_stage.status == "failed"
        assert failed_stage.error_message is not None
        assert chain_failure.failed_stages == 1
        assert chain_failure.overall_status == "partial"
