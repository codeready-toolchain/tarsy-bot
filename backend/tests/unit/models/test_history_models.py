"""
Tests for history models - focusing on custom validation logic.
"""

import pytest
from pydantic import ValidationError

from tarsy.models.history_models import MCPEventDetails, MCPTimelineEvent


class TestMCPEventDetails:
    """Test suite for MCPEventDetails custom validation logic."""
    
    def test_mcp_event_details_with_error_message(self):
        """Test MCPEventDetails preserves complex error messages."""
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
        
        # Verify error message preserved exactly
        assert mcp_details.error_message == error_message
        assert "Failed to call tool unhealthyApplications" in mcp_details.error_message
        assert "net/http: invalid header field value" in mcp_details.error_message
    


class TestMCPTimelineEvent:
    """Test suite for MCPTimelineEvent custom validation."""
    
    def test_mcp_timeline_event_tool_name_validation(self):
        """Test MCPTimelineEvent validation for tool_name requirement in tool_call communications."""
        from tarsy.utils.timestamp import now_us
        
        # tool_call communication without tool_name should fail
        with pytest.raises(ValidationError) as exc_info:
            invalid_details = MCPEventDetails(
                tool_name=None,  # Missing tool_name for tool_call
                server_name="test-server",
                communication_type="tool_call",
                success=True
            )
            
            MCPTimelineEvent(
                id="mcp-timeline-1",
                event_id="mcp-timeline-1", 
                timestamp_us=now_us(),
                step_description="Test MCP call",
                stage_execution_id="test-stage-1",
                details=invalid_details
            )
        
        assert "tool_name" in str(exc_info.value)
        assert "tool_call" in str(exc_info.value)
        
        # tool_list communication without tool_name should succeed
        valid_details = MCPEventDetails(
            tool_name=None,  # No tool_name needed for tool_list
            server_name="test-server",
            communication_type="tool_list",
            success=True
        )
        
        timeline_event = MCPTimelineEvent(
            id="mcp-timeline-2",
            event_id="mcp-timeline-2",
            timestamp_us=now_us(),
            step_description="List MCP tools",
            stage_execution_id="test-stage-1", 
            details=valid_details
        )
        
        assert timeline_event.details.tool_name is None
        assert timeline_event.details.communication_type == "tool_list"
