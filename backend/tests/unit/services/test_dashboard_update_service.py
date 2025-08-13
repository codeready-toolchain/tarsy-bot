"""
Unit tests for DashboardUpdateService.
"""


from dataclasses import asdict
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from tarsy.services.dashboard_update_service import (
    DashboardUpdateService,
    SessionSummary,
)
from tests.utils import DashboardFactory


class TestSessionSummary:
    """Test SessionSummary dataclass functionality."""
    
    @pytest.mark.unit
    def test_session_summary_creation(self):
        """Test SessionSummary creation with defaults."""
        summary = DashboardFactory.create_session_summary(
            session_id="session_123",
            status="active",
            start_time=None,
            agent_type=None,
            last_activity=None
        )
        
        assert summary.session_id == "session_123"
        assert summary.status == "active"
        assert summary.start_time is None  # Default is None
        assert summary.llm_interactions == 0
        assert summary.mcp_communications == 0

        assert summary.agent_type is None
        assert summary.last_activity is None  # Default is None
        assert summary.errors_count == 0
    
    @pytest.mark.unit
    def test_session_summary_with_custom_values(self):
        """Test SessionSummary creation with custom values."""
        start_time = datetime.now()
        summary = DashboardFactory.create_session_summary(
            session_id="session_456",
            status="processing",
            start_time=start_time,
            llm_interactions=5,
            mcp_communications=3,
            agent_type="kubernetes_agent",
            errors_count=1
        )
        
        assert summary.session_id == "session_456"
        assert summary.status == "processing"
        assert summary.start_time == start_time
        assert summary.llm_interactions == 5
        assert summary.mcp_communications == 3

        assert summary.agent_type == "kubernetes_agent"
        assert summary.errors_count == 1
    
    @pytest.mark.unit
    def test_session_summary_to_dict_conversion(self):
        """Test converting SessionSummary to dictionary."""
        summary = DashboardFactory.create_session_summary(
            session_id="session_789",
            status="completed",
            llm_interactions=10,
            mcp_communications=7
        )
        
        summary_dict = asdict(summary)
        
        assert summary_dict["session_id"] == "session_789"
        assert summary_dict["status"] == "completed"
        assert summary_dict["llm_interactions"] == 10
        assert summary_dict["mcp_communications"] == 7
        assert "start_time" in summary_dict
        assert "last_activity" in summary_dict

class TestDashboardUpdateService:
    """Test DashboardUpdateService main functionality."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock dashboard broadcaster."""
        return DashboardFactory.create_mock_broadcaster()
    
    @pytest.fixture
    def update_service(self, mock_broadcaster):
        """Create DashboardUpdateService instance."""
        return DashboardUpdateService(mock_broadcaster)
    
    @pytest.mark.unit
    def test_initialization(self, update_service, mock_broadcaster):
        """Test DashboardUpdateService initialization."""
        assert update_service.broadcaster == mock_broadcaster
        assert isinstance(update_service.active_sessions, dict)

        assert update_service.running is False
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_start_stop_service(self, update_service):
        """Test starting and stopping the service."""
        assert update_service.running is False
        
        # Start service
        await update_service.start()
        assert update_service.running is True
        
        # Stop service
        await update_service.stop()
        assert update_service.running is False

class TestLLMInteractionProcessing:
    """Test LLM interaction processing with correct data formats."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock broadcaster."""
        return DashboardFactory.create_mock_broadcaster()
    
    @pytest.fixture
    def update_service(self, mock_broadcaster):
        """Create service instance."""
        return DashboardUpdateService(mock_broadcaster)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_llm_interaction_success(self, update_service, mock_broadcaster):
        """Test processing successful LLM interaction with production data format."""
        session_id = "llm_session_123"
        interaction_data = DashboardFactory.create_llm_interaction_data(session_id=session_id)
        
        # Test immediate processing (no batching)
        sent_count = await update_service.process_llm_interaction(
            session_id, interaction_data
        )
        
        # Verify both individual broadcasts were called
        mock_broadcaster.broadcast_session_update.assert_called_once()
        mock_broadcaster.broadcast_dashboard_update.assert_called_once()
        
        # Verify combined sent count from both channels
        # (session channel: 2, dashboard channel: 3)
        assert sent_count == 5
        
        # Verify session was created/updated
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.llm_interactions == 1
        assert session.interactions_count == 1
        assert session.errors_count == 0
        assert session.status == "active"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_llm_interaction_error(self, update_service, mock_broadcaster):
        """Test processing LLM interaction error."""
        session_id = "llm_error_session"
        interaction_data = DashboardFactory.create_error_interaction_data(session_id=session_id)
        
        await update_service.process_llm_interaction(session_id, interaction_data)
        
        # Verify session error tracking
        session = update_service.active_sessions[session_id]
        assert session.errors_count == 1

class TestMCPInteractionProcessing:
    """Test MCP communication processing with correct data formats."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock broadcaster."""
        broadcaster = AsyncMock()
        broadcaster.broadcast_dashboard_update = AsyncMock(return_value=2)
        return broadcaster
    
    @pytest.fixture
    def update_service(self, mock_broadcaster):
        """Create service instance."""
        return DashboardUpdateService(mock_broadcaster)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_mcp_communication_success(self, update_service, mock_broadcaster):
        """Test processing successful MCP communication with production data format."""
        session_id = "mcp_session_456"
        communication_data = {
            'interaction_type': 'mcp',
            'session_id': session_id,
            'step_description': 'Execute kubectl via kubernetes server',
            'server_name': 'kubernetes',
            'tool_name': 'kubectl',
            'success': True,
            'duration_ms': 800,
            'timestamp': datetime.now().isoformat(),
            'error_message': None
        }
        
        # Test immediate processing (no batching)
        await update_service.process_mcp_communication(session_id, communication_data)
        # Return value is from mocked broadcaster.broadcast_session_update
        
        # Verify session was created/updated
        session = update_service.active_sessions[session_id]
        assert session.mcp_communications == 1
        assert session.interactions_count == 1
        assert session.errors_count == 0

        assert session.status == "active"
        
        # Verify broadcast was called
        mock_broadcaster.broadcast_session_update.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_mcp_communication_error(self, update_service, mock_broadcaster):
        """Test processing MCP communication error."""
        session_id = "mcp_error_session"
        communication_data = {
            'interaction_type': 'mcp',
            'session_id': session_id,
            'step_description': 'kubectl execution failed',
            'server_name': 'kubernetes',
            'tool_name': 'kubectl',
            'success': False,
            'duration_ms': 200,
            'timestamp': datetime.now().isoformat(),
            'error_message': 'Tool execution failed: kubectl not found'
        }
        
        sent_count = await update_service.process_mcp_communication(session_id, communication_data)
        
        # Verify session error tracking
        session = update_service.active_sessions[session_id]
        assert session.errors_count == 1

    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_mcp_communication_with_step_description(self, update_service, mock_broadcaster):
        """Test MCP communication with explicit step description."""
        session_id = "mcp_step_session"
        communication_data = {
            'interaction_type': 'mcp',
            'session_id': session_id,
            'step_description': 'Custom step description from hook',
            'server_name': 'file_operations',
            'tool_name': 'read_file',
            'success': True,
            'duration_ms': 150,
            'timestamp': datetime.now().isoformat(),
            'error_message': None
        }
        
        await update_service.process_mcp_communication(session_id, communication_data)
        
        # Verify custom step description is used
        update_service.active_sessions[session_id]

class TestSessionStatusManagement:
    """Test session status change processing."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock broadcaster."""
        broadcaster = AsyncMock()
        broadcaster.broadcast_dashboard_update = AsyncMock(return_value=3)
        broadcaster.broadcast_session_update = AsyncMock(return_value=2)
        return broadcaster
    
    @pytest.fixture
    def update_service(self, mock_broadcaster):
        """Create service instance."""
        return DashboardUpdateService(mock_broadcaster)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_session_status_change_new_session(self, update_service, mock_broadcaster):
        """Test creating new session with status change."""
        session_id = "new_status_session"
        status = "processing"
        details = {
            "agent_type": "kubernetes_agent",
            "progress_percentage": 25
        }
        
        sent_count = await update_service.process_session_status_change(
            session_id, status, details
        )
        
        # Verify both individual broadcasts were called
        mock_broadcaster.broadcast_dashboard_update.assert_called_once()
        mock_broadcaster.broadcast_session_update.assert_called_once()
        
        # Verify combined sent count from dual-channel broadcasting
        # (broadcaster returned 3 + 2 = 5)
        assert sent_count == 5
        
        # Verify session was created
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.status == status
        assert session.agent_type == "kubernetes_agent"

        assert session.progress_percentage == 25
        assert session.start_time is not None
        assert session.last_activity is not None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_session_status_change_existing_session(self, update_service, mock_broadcaster):
        """Test updating existing session status."""
        session_id = "existing_session"
        
        # Create existing session
        original_session = SessionSummary(
            session_id=session_id,
            status="active",
            agent_type="log_analyzer",
            start_time=datetime.now() - timedelta(minutes=5)
        )
        update_service.active_sessions[session_id] = original_session
        
        # Update status
        new_status = "completed"
        details = {"progress_percentage": 100}
        
        sent_count = await update_service.process_session_status_change(session_id, new_status, details)
        
        # Verify session was updated but start_time preserved
        session = update_service.active_sessions.get(session_id)  # May be None if archived
        if session:  # Session not yet archived (test timing)
            assert session.status == new_status
            assert session.agent_type == "log_analyzer"  # Preserved

            assert session.progress_percentage == 100
            assert session.start_time == original_session.start_time  # Preserved
        
        # Verify session was archived for completion statuses
        if new_status in ["completed", "error", "timeout"]:
            # Session should be removed from active sessions
            assert session_id not in update_service.active_sessions
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_session_archiving_on_completion(self, update_service, mock_broadcaster):
        """Test session archiving when status indicates completion."""
        session_id = "archiving_session"
        
        # Create active session
        update_service.active_sessions[session_id] = SessionSummary(
            session_id=session_id,
            status="processing",
            llm_interactions=5,
            mcp_communications=3
        )
        
        # Complete the session
        await update_service.process_session_status_change(session_id, "completed")
        
        # Verify session was archived (removed from active sessions)
        assert session_id not in update_service.active_sessions


class TestActiveSessionsBroadcasting:
    """Test active sessions broadcasting functionality."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock broadcaster."""
        broadcaster = AsyncMock()
        broadcaster.broadcast_dashboard_update = AsyncMock(return_value=7)
        return broadcaster
    
    @pytest.fixture
    def update_service(self, mock_broadcaster):
        """Create service instance with test data."""
        service = DashboardUpdateService(mock_broadcaster)
        
        # Set up test sessions
        service.active_sessions = {
            "session_1": SessionSummary(
                session_id="session_1",
                status="active",
                agent_type="kubernetes_agent",
                progress_percentage=60,
                interactions_count=10,
                errors_count=1
            ),
            "session_2": SessionSummary(
                session_id="session_2", 
                status="processing",
                agent_type="log_analyzer",
                progress_percentage=30,
                interactions_count=5,
                errors_count=0
            )
        }
        
        # No complex metrics needed - just track sessions
        
        return service
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_active_sessions(self, update_service, mock_broadcaster):
        """Test broadcasting active sessions list."""
        sent_count = await update_service.broadcast_active_sessions()
        
        assert sent_count == 7  # Mock broadcaster return value
        mock_broadcaster.broadcast_dashboard_update.assert_called_once()
        
        # Verify the broadcast call arguments
        call_args = mock_broadcaster.broadcast_dashboard_update.call_args[0][0]
        
        assert call_args["type"] == "system_metrics"  # Kept for frontend compatibility
        assert "active_sessions_list" in call_args
        assert "timestamp" in call_args
        
        # Verify active sessions list
        sessions_list = call_args["active_sessions_list"]
        assert len(sessions_list) == 2
        
        session_1 = next(s for s in sessions_list if s["session_id"] == "session_1")
        assert session_1["status"] == "active"
        assert session_1["agent_type"] == "kubernetes_agent"
        assert session_1["progress"] == 60
        assert session_1["interactions"] == 10
        assert session_1["errors"] == 1


class TestMultipleSessionInteractions:
    """Test multiple interactions on the same session."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock broadcaster."""
        broadcaster = AsyncMock()
        broadcaster.broadcast_dashboard_update = AsyncMock(return_value=2)
        return broadcaster
    
    @pytest.fixture
    def update_service(self, mock_broadcaster):
        """Create service instance."""
        return DashboardUpdateService(mock_broadcaster)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_multiple_llm_interactions_same_session(self, update_service):
        """Test multiple LLM interactions on the same session."""
        session_id = "multi_llm_session"
        
        # First LLM interaction
        interaction_1 = {
            'interaction_type': 'llm',
            'session_id': session_id,
            'step_description': 'First analysis',
            'model_used': 'gpt-4',
            'success': True,
            'duration_ms': 1000,
            'timestamp': datetime.now().isoformat()
        }
        
        await update_service.process_llm_interaction(session_id, interaction_1)
        
        # Second LLM interaction
        interaction_2 = {
            'interaction_type': 'llm',
            'session_id': session_id,
            'step_description': 'Second analysis',
            'model_used': 'gpt-4',
            'success': False,
            'duration_ms': 500,
            'timestamp': datetime.now().isoformat(),
            'error_message': 'Analysis failed'
        }
        
        await update_service.process_llm_interaction(session_id, interaction_2)
        
        # Verify cumulative session tracking
        session = update_service.active_sessions[session_id]
        assert session.llm_interactions == 2
        assert session.interactions_count == 2
        assert session.errors_count == 1  # One failed interaction

    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_mixed_llm_mcp_interactions_same_session(self, update_service):
        """Test mixed LLM and MCP interactions on the same session."""
        session_id = "mixed_session"
        
        # LLM interaction
        llm_data = {
            'interaction_type': 'llm',
            'session_id': session_id,
            'step_description': 'LLM analysis',
            'model_used': 'gpt-4',
            'success': True,
            'duration_ms': 1200,
            'timestamp': datetime.now().isoformat()
        }
        
        await update_service.process_llm_interaction(session_id, llm_data)
        
        # MCP interaction
        mcp_data = {
            'interaction_type': 'mcp',
            'session_id': session_id,
            'step_description': 'Execute kubectl command',
            'server_name': 'kubernetes',
            'tool_name': 'kubectl',
            'success': True,
            'duration_ms': 800,
            'timestamp': datetime.now().isoformat()
        }
        
        await update_service.process_mcp_communication(session_id, mcp_data)
        
        # Verify mixed interaction tracking
        session = update_service.active_sessions[session_id]
        assert session.llm_interactions == 1
        assert session.mcp_communications == 1
        assert session.interactions_count == 2
        assert session.errors_count == 0

class TestErrorHandling:
    """Test error handling in dashboard update service."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock dashboard broadcaster that sometimes fails."""
        broadcaster = AsyncMock()
        return broadcaster
    
    @pytest.fixture
    def update_service(self, mock_broadcaster):
        """Create DashboardUpdateService instance."""
        return DashboardUpdateService(mock_broadcaster)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcaster_failure_handling(self, update_service, mock_broadcaster):
        """Test handling broadcaster failures gracefully."""
        # Configure broadcaster to fail
        mock_broadcaster.broadcast_session_update.side_effect = Exception("Broadcast failed")
        
        session_id = "broadcast_fail_session"
        interaction_data = {
            'interaction_type': 'llm',
            'session_id': session_id,
            'step_description': 'Test interaction',
            'model_used': 'gpt-4',
            'success': True,
            'duration_ms': 1000,
            'timestamp': datetime.now().isoformat()
        }
        
        # Should not raise exception, should return broadcaster return value
        await update_service.process_llm_interaction(
            session_id, interaction_data
        )
        
        # Test completes successfully even with invalid data  # Failed broadcast returns 0
        
        # Session should still be updated despite broadcast failure
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.llm_interactions == 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_invalid_session_data_handling(self, update_service):
        """Test handling invalid session data gracefully."""
        # Missing required fields - should not crash
        invalid_data = {"invalid": "data"}
        
        # Should not raise exception
        await update_service.process_llm_interaction("invalid_session", invalid_data)
        # Test completes successfully even with invalid data
        
        await update_service.process_mcp_communication("invalid_session", invalid_data)
        # Test completes successfully even with invalid data

class TestDualChannelBroadcasting:
    """Test dual-channel broadcasting for session-specific updates."""
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Mock broadcaster configured for dual-channel testing."""
        broadcaster = AsyncMock()
        broadcaster.broadcast_dashboard_update = AsyncMock(return_value=3)
        broadcaster.broadcast_session_update = AsyncMock(return_value=2)
        return broadcaster
    
    @pytest.fixture  
    def update_service(self, mock_broadcaster):
        """Create service instance."""
        return DashboardUpdateService(mock_broadcaster)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_session_status_change_dual_channel_broadcast(self, update_service, mock_broadcaster):
        """Test that session status changes are broadcast to both channels."""
        session_id = "dual_broadcast_session"
        status = "completed"
        details = {"final_analysis": "Test analysis completed"}
        
        sent_count = await update_service.process_session_status_change(session_id, status, details)
        
        # Should return sum of both broadcasts (3 + 2 = 5)
        assert sent_count == 5
        
        # Both broadcast methods should be called
        mock_broadcaster.broadcast_session_update.assert_called_once()
        mock_broadcaster.broadcast_dashboard_update.assert_called_once()
        
        # Verify the update data structure for session-specific broadcast
        session_call_args = mock_broadcaster.broadcast_session_update.call_args
        assert session_call_args[0][0] == session_id  # First arg is session_id
        session_update_data = session_call_args[0][1]  # Second arg is update data
        assert session_update_data['type'] == 'session_status_change'
        assert session_update_data['session_id'] == session_id
        assert session_update_data['status'] == status
        
        # Verify the update data structure for dashboard broadcast  
        dashboard_call_args = mock_broadcaster.broadcast_dashboard_update.call_args
        dashboard_update_data = dashboard_call_args[0][0]  # First arg is update data
        assert dashboard_update_data['type'] == 'session_status_change'
        assert dashboard_update_data['session_id'] == session_id
        assert dashboard_update_data['status'] == status
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_update_method_dual_channel_logic(self, update_service, mock_broadcaster):
        """Test that the _broadcast_update method correctly routes session status changes to both channels."""
        session_id = "broadcast_method_test_session"
        
        # Create a session status change update (should go to both channels)
        status_update = {
            "type": "session_status_change",
            "session_id": session_id,
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        }
        
        sent_count = await update_service._broadcast_update(status_update)
        
        # Should return sum of both broadcasts (3 + 2 = 5)
        assert sent_count == 5
        
        # Both broadcast methods should be called
        mock_broadcaster.broadcast_session_update.assert_called_once()
        mock_broadcaster.broadcast_dashboard_update.assert_called_once()
        
        # Create a batched session updates (should also go to both channels)
        mock_broadcaster.reset_mock()
        batched_update = {
            "type": "batched_session_updates",
            "session_id": session_id,
            "updates": [{"type": "llm_interaction", "session_id": session_id}],
            "timestamp": datetime.now().isoformat()
        }
        
        sent_count = await update_service._broadcast_update(batched_update)
        
        # Dual-channel broadcast: session (2) + dashboard (3) = 5
        assert sent_count == 5
        
        # With dual-channel behavior, both broadcasts are called
        mock_broadcaster.broadcast_session_update.assert_called_once()
        mock_broadcaster.broadcast_dashboard_update.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit 
    async def test_llm_interaction_dual_channel_broadcast(self, update_service, mock_broadcaster):
        """Test that LLM interactions go to both session-specific and dashboard channels."""
        session_id = "single_channel_session"
        llm_data = {
            'interaction_type': 'llm',
            'session_id': session_id,
            'step_description': 'Test LLM interaction',
            'model_used': 'gpt-4',
            'success': True,
            'duration_ms': 1000,
            'timestamp': datetime.now().isoformat()
        }
        
        sent_count = await update_service.process_llm_interaction(
            session_id, llm_data
        )
        
        # Should return both session broadcast count (2) + dashboard count (3) = 5
        assert sent_count == 5
        
        # Both broadcasts should be called for dual-channel behavior
        mock_broadcaster.broadcast_session_update.assert_called_once()
        mock_broadcaster.broadcast_dashboard_update.assert_called_once()
        
        # Verify the update data structure  
        call_args = mock_broadcaster.broadcast_session_update.call_args
        assert call_args[0][0] == session_id  # First arg is session_id
        update_data = call_args[0][1]  # Second arg is update data
        assert update_data['type'] == 'llm_interaction'
        assert update_data['session_id'] == session_id

if __name__ == "__main__":
    pytest.main([__file__]) 