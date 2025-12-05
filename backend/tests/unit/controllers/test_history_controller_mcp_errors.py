"""
Tests for history controller MCP error message API endpoints.
"""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from tarsy.controllers.history_controller import get_session_detail
from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.history_models import (
    DetailedSession,
    DetailedStage,
    MCPEventDetails,
    MCPTimelineEvent,
)
from tarsy.utils.timestamp import now_us


class TestHistoryControllerMCPErrors:
    """Test suite for history controller MCP error message handling."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_session_detail_includes_mcp_error_messages(self):
        """Test that get_session_detail API returns MCP error messages."""
        # Create mock history service
        mock_history_service = Mock()
        
        # Create test data with MCP error
        error_message = 'Failed to call tool unhealthyApplications on argocd-server: Type=McpError | Message=Get "https://argocd.example.com/api/v1/applications": net/http: invalid header field value for "Authorization"'
        
        mcp_details_with_error = MCPEventDetails(
            tool_name="unhealthyApplications",
            server_name="argocd-server",
            communication_type="tool_call",
            tool_arguments={},
            tool_result={},
            available_tools={},
            success=False,
            error_message=error_message,
            duration_ms=2
        )
        
        mcp_timeline_event = MCPTimelineEvent(
            id="mcp-comm-failed",
            event_id="mcp-comm-failed",
            timestamp_us=now_us(),
            duration_ms=2,
            step_description="Check unhealthy ArgoCD applications",
            stage_execution_id="stage-with-error",
            details=mcp_details_with_error
        )
        
        stage_with_error = DetailedStage(
            execution_id="stage-with-error",
            session_id="test-session-123",
            stage_id="analysis-stage",
            stage_index=0,
            stage_name="Analysis Stage",
            agent="ArgocdAgent",
            status=StageStatus.FAILED,
            started_at_us=now_us(),
            completed_at_us=now_us() + 5000000,
            duration_ms=5000,
            error_message=None,
            mcp_communications=[mcp_timeline_event],
            mcp_communication_count=1,
            total_interactions=1
        )
        
        session_with_mcp_error = DetailedSession(
            session_id="test-session-123",
            alert_type="ArgocdUnhealthy",
            agent_type="chain:argocd",
            status=AlertSessionStatus.FAILED,
            started_at_us=now_us(),
            completed_at_us=now_us() + 10000000,
            alert_data={"alert_type": "ArgocdUnhealthy"},
            chain_id="argocd-analysis-chain",
            chain_definition={"stages": []},
            stages=[stage_with_error],
            total_interactions=1,
            mcp_communication_count=1
        )
        
        # Mock history service to return our test data
        mock_history_service.get_session_details.return_value = session_with_mcp_error
        
        # Call the API endpoint
        result = await get_session_detail(
            session_id="test-session-123",
            history_service=mock_history_service
        )
        
        # Verify the result includes MCP error messages
        assert result.session_id == "test-session-123"
        assert len(result.stages) == 1
        
        stage = result.stages[0]
        assert stage.mcp_communication_count == 1
        assert len(stage.mcp_communications) == 1
        
        mcp_comm = stage.mcp_communications[0]
        assert mcp_comm.details.success == False
        assert mcp_comm.details.error_message is not None
        assert "Failed to call tool unhealthyApplications" in mcp_comm.details.error_message
        assert "net/http: invalid header field value" in mcp_comm.details.error_message
        assert mcp_comm.details.duration_ms == 2
        assert mcp_comm.details.server_name == "argocd-server"
        assert mcp_comm.details.tool_name == "unhealthyApplications"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_session_detail_successful_mcp_no_error(self):
        """Test that successful MCP interactions have None error_message."""
        mock_history_service = Mock()
        
        # Create successful MCP details
        mcp_details_success = MCPEventDetails(
            tool_name="kubectl_get_pods",
            server_name="kubernetes-server", 
            communication_type="tool_call",
            parameters={"namespace": "default"},
            result={"pods": ["pod1", "pod2"]},
            available_tools={},
            success=True,
            error_message=None,
            duration_ms=1500
        )
        
        mcp_timeline_event = MCPTimelineEvent(
            id="mcp-comm-success",
            event_id="mcp-comm-success",
            timestamp_us=now_us(),
            duration_ms=1500,
            step_description="Get pods from Kubernetes",
            stage_execution_id="stage-success",
            details=mcp_details_success
        )
        
        stage_success = DetailedStage(
            execution_id="stage-success",
            session_id="test-session-456",
            stage_id="kubernetes-check",
            stage_index=0,
            stage_name="Kubernetes Check",
            agent="KubernetesAgent",
            status=StageStatus.COMPLETED,
            started_at_us=now_us(),
            completed_at_us=now_us() + 2000000,
            duration_ms=2000,
            mcp_communications=[mcp_timeline_event],
            mcp_communication_count=1,
            total_interactions=1
        )
        
        session_success = DetailedSession(
            session_id="test-session-456",
            alert_type="KubernetesAlert",
            agent_type="chain:kubernetes",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=now_us(),
            completed_at_us=now_us() + 5000000,
            alert_data={"alert_type": "KubernetesAlert"},
            chain_id="kubernetes-chain",
            chain_definition={"stages": []},
            stages=[stage_success],
            total_interactions=1,
            mcp_communication_count=1
        )
        
        mock_history_service.get_session_details.return_value = session_success
        
        # Call the API endpoint
        result = await get_session_detail(
            session_id="test-session-456",
            history_service=mock_history_service
        )
        
        # Verify successful MCP has no error message
        mcp_comm = result.stages[0].mcp_communications[0]
        assert mcp_comm.details.success == True
        assert mcp_comm.details.error_message is None
        assert mcp_comm.details.duration_ms == 1500
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_session_detail_not_found(self):
        """Test that get_session_detail returns 404 when session not found."""
        mock_history_service = Mock()
        mock_history_service.get_session_details.return_value = None
        
        # Should raise HTTPException with 404 status
        with pytest.raises(HTTPException) as exc_info:
            await get_session_detail(
                session_id="non-existent-session",
                history_service=mock_history_service
            )
        
        assert exc_info.value.status_code == 404
        assert "Session non-existent-session not found" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_session_detail_service_error(self):
        """Test that get_session_detail handles service errors properly."""
        mock_history_service = Mock()
        mock_history_service.get_session_details.side_effect = Exception("Database connection failed")
        
        # Should raise HTTPException with 500 status
        with pytest.raises(HTTPException) as exc_info:
            await get_session_detail(
                session_id="test-session",
                history_service=mock_history_service
            )
        
        assert exc_info.value.status_code == 500
        assert "Failed to retrieve session details" in str(exc_info.value.detail)
