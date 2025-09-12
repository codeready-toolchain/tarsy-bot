"""
Tests for history models including MCPEventDetails error message handling.
"""

import pytest
from pydantic import ValidationError

from tarsy.models.history_models import MCPEventDetails, MCPTimelineEvent


class TestMCPEventDetails:
    """Test suite for MCPEventDetails model validation and error handling."""
    
    def test_mcp_event_details_successful_creation(self):
        """Test successful creation of MCPEventDetails with all fields."""
        mcp_details = MCPEventDetails(
            tool_name="kubectl_get_pods",
            server_name="kubernetes-server",
            communication_type="tool_call",
            parameters={"namespace": "default", "selector": "app=nginx"},
            result={"pods": ["nginx-1", "nginx-2"]},
            available_tools={},
            success=True,
            error_message=None,
            duration_ms=1500
        )
        
        assert mcp_details.tool_name == "kubectl_get_pods"
        assert mcp_details.server_name == "kubernetes-server"
        assert mcp_details.communication_type == "tool_call"
        assert mcp_details.parameters == {"namespace": "default", "selector": "app=nginx"}
        assert mcp_details.result == {"pods": ["nginx-1", "nginx-2"]}
        assert mcp_details.success == True
        assert mcp_details.error_message is None
        assert mcp_details.duration_ms == 1500
    
    def test_mcp_event_details_with_error_message(self):
        """Test MCPEventDetails creation with error message for failed interactions."""
        error_message = 'Failed to call tool unhealthyApplications on argocd-server: Type=McpError | Message=Get "https://argocd.example.com/api/v1/applications": net/http: invalid header field value for "Authorization"'
        
        mcp_details = MCPEventDetails(
            tool_name="unhealthyApplications",
            server_name="argocd-server",
            communication_type="tool_call",
            parameters={},
            result={},
            available_tools={},
            success=False,
            error_message=error_message,
            duration_ms=2
        )
        
        assert mcp_details.tool_name == "unhealthyApplications"
        assert mcp_details.server_name == "argocd-server"
        assert mcp_details.success == False
        assert mcp_details.error_message == error_message
        assert "Failed to call tool unhealthyApplications" in mcp_details.error_message
        assert "net/http: invalid header field value" in mcp_details.error_message
        assert mcp_details.duration_ms == 2
    
    def test_mcp_event_details_optional_fields(self):
        """Test that error_message and duration_ms are optional fields."""
        # Minimal required fields only
        mcp_details = MCPEventDetails(
            tool_name="list_tools",
            server_name="test-server",
            communication_type="tool_list",
            success=True
        )
        
        assert mcp_details.tool_name == "list_tools"
        assert mcp_details.server_name == "test-server"
        assert mcp_details.success == True
        assert mcp_details.error_message is None  # Default None
        assert mcp_details.duration_ms is None  # Default None
        assert mcp_details.parameters == {}  # Default empty dict
        assert mcp_details.result == {}  # Default empty dict
        assert mcp_details.available_tools == {}  # Default empty dict
    
    def test_mcp_event_details_required_fields_validation(self):
        """Test that required fields are validated."""
        # Missing tool_name
        with pytest.raises(ValidationError) as exc_info:
            MCPEventDetails(
                server_name="test-server",
                communication_type="tool_call",
                success=True
            )
        assert "tool_name" in str(exc_info.value)
        
        # Missing server_name  
        with pytest.raises(ValidationError) as exc_info:
            MCPEventDetails(
                tool_name="test_tool",
                communication_type="tool_call",
                success=True
            )
        assert "server_name" in str(exc_info.value)
        
        # Missing communication_type
        with pytest.raises(ValidationError) as exc_info:
            MCPEventDetails(
                tool_name="test_tool",
                server_name="test-server",
                success=True
            )
        assert "communication_type" in str(exc_info.value)
        
        # Missing success
        with pytest.raises(ValidationError) as exc_info:
            MCPEventDetails(
                tool_name="test_tool",
                server_name="test-server",
                communication_type="tool_call"
            )
        assert "success" in str(exc_info.value)


class TestMCPTimelineEvent:
    """Test suite for MCPTimelineEvent model validation."""
    
    def test_mcp_timeline_event_with_error_details(self):
        """Test MCPTimelineEvent creation with error details."""
        from tarsy.utils.timestamp import now_us
        
        error_message = "Connection timeout to MCP server"
        mcp_details = MCPEventDetails(
            tool_name="failed_tool",
            server_name="test-server",
            communication_type="tool_call",
            success=False,
            error_message=error_message,
            duration_ms=5000
        )
        
        timeline_event = MCPTimelineEvent(
            id="mcp-timeline-1",
            event_id="mcp-timeline-1",
            timestamp_us=now_us(),
            duration_ms=5000,
            step_description="Failed MCP call",
            stage_execution_id="test-stage-1",
            details=mcp_details
        )
        
        assert timeline_event.type == "mcp"
        assert timeline_event.details.success == False
        assert timeline_event.details.error_message == error_message
        assert timeline_event.details.duration_ms == 5000
        assert timeline_event.step_description == "Failed MCP call"
    
    def test_mcp_timeline_event_validation_error(self):
        """Test MCPTimelineEvent validation for required fields."""
        # Missing server_name in details should fail validation
        with pytest.raises(ValidationError) as exc_info:
            invalid_details = MCPEventDetails(
                tool_name="test_tool",
                server_name="",  # Empty server name
                communication_type="tool_call",
                success=True
            )
            
            MCPTimelineEvent(
                id="mcp-timeline-1",
                event_id="mcp-timeline-1",
                timestamp_us=12345678,
                step_description="Test MCP call",
                stage_execution_id="test-stage-1",
                details=invalid_details
            )
        assert "server_name" in str(exc_info.value)
