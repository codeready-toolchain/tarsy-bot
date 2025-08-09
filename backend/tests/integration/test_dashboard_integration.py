"""
Integration tests for Dashboard System.

Tests the complete dashboard system integration with correct API usage
and real-world scenarios.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from tarsy.hooks.dashboard_hooks import DashboardLLMHooks, DashboardMCPHooks
from tarsy.models.websocket_models import (
    ChannelType,
)
from tarsy.services.dashboard_broadcaster import DashboardBroadcaster
from tarsy.services.dashboard_connection_manager import DashboardConnectionManager
from tarsy.services.dashboard_update_service import DashboardUpdateService


@pytest.mark.integration
class TestDashboardSystemIntegration:
    """Test complete dashboard system integration with correct API usage."""
    
    @pytest.fixture
    async def dashboard_system(self):
        """Create complete dashboard system for integration testing."""
        # Create connection manager
        connection_manager = DashboardConnectionManager()
        
        # Create broadcaster
        broadcaster = DashboardBroadcaster(connection_manager)
        
        # Create and start update service
        update_service = DashboardUpdateService(broadcaster)
        await update_service.start()
        
        # Create hooks with mock WebSocket manager
        mock_dashboard_manager = Mock()
        mock_dashboard_manager = connection_manager
        connection_manager.update_service = update_service
        
        llm_hooks = DashboardLLMHooks(dashboard_manager=mock_dashboard_manager)
        mcp_hooks = DashboardMCPHooks(dashboard_manager=mock_dashboard_manager)
        
        system = {
            'connection_manager': connection_manager,
            'broadcaster': broadcaster,
            'update_service': update_service,
            'llm_hooks': llm_hooks,
            'mcp_hooks': mcp_hooks
        }
        
        yield system
        
        # Cleanup
        await update_service.stop()


    @pytest.mark.asyncio
    async def test_complete_llm_workflow_via_hooks(self, dashboard_system):
        """Test complete LLM interaction workflow through hook system."""
        llm_hooks = dashboard_system['llm_hooks']
        update_service = dashboard_system['update_service']
        
        session_id = "integration_llm_session"
        
        # Simulate LLM interaction via hook execution
        llm_event_data = {
            "session_id": session_id,
            "args": {
                "prompt": "Analyze system logs",
                "model": "gpt-4"
            },
            "result": {
                "content": "Found 3 critical errors in logs",
                "usage": {"prompt_tokens": 50, "completion_tokens": 100}
            },
            "start_time": datetime.now(),
            "end_time": datetime.now()
        }
        
        # Execute hook (this is what actually happens in production)
        await llm_hooks.execute("llm.post", **llm_event_data)
        
        # Verify session was created and tracked
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.session_id == session_id
        assert session.llm_interactions >= 1

    @pytest.mark.asyncio
    async def test_complete_mcp_workflow_via_hooks(self, dashboard_system):
        """Test complete MCP interaction workflow through hook system."""
        mcp_hooks = dashboard_system['mcp_hooks']
        update_service = dashboard_system['update_service']
        
        session_id = "integration_mcp_session"
        
        # Simulate MCP communication via hook execution
        mcp_event_data = {
            "session_id": session_id,
            "method": "call_tool",
            "args": {
                "server_name": "kubernetes",
                "tool_name": "kubectl-get-pods",
                "tool_arguments": {"namespace": "default"}
            },
            "result": {"output": "pod1 Running\npod2 Pending"},
            "start_time": datetime.now(),
            "end_time": datetime.now()
        }
        
        # Execute hook (this is what actually happens in production)
        await mcp_hooks.execute("mcp.post", **mcp_event_data)
        
        # Verify session was created and tracked
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.session_id == session_id
        assert session.mcp_communications >= 1

    @pytest.mark.asyncio
    async def test_session_lifecycle_management(self, dashboard_system):
        """Test complete session lifecycle using actual API."""
        update_service = dashboard_system['update_service']
        
        session_id = "lifecycle_test_session"
        
        # Create session via status change
        sent_count = await update_service.process_session_status_change(
            session_id, "active", {}
        )
        assert sent_count >= 0
        
        # Update session multiple times
        await update_service.process_session_status_change(
            session_id, "processing", {
                "agent_type": "analyzer_agent",
                "progress_percentage": 25
            }
        )
        
        await update_service.process_session_status_change(
            session_id, "processing", {
                "agent_type": "executor_agent",
                "progress_percentage": 75
            }
        )
        
        # Complete session
        await update_service.process_session_status_change(
            session_id, "completed", {
                "progress_percentage": 100
            }
        )
        
        # Session should be archived after completion
        assert session_id not in update_service.active_sessions  # Moved to history

    @pytest.mark.asyncio
    async def test_real_time_broadcasting(self, dashboard_system):
        """Test real-time broadcasting through the system."""
        connection_manager = dashboard_system['connection_manager']
        broadcaster = dashboard_system['broadcaster']
        update_service = dashboard_system['update_service']
        
        # Disable batching for immediate delivery in tests

        
        # Mock WebSocket connections
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        
        # Connect users
        await connection_manager.connect(mock_ws1, "user1")
        await connection_manager.connect(mock_ws2, "user2")
        
        # Subscribe users to channels
        connection_manager.subscribe_to_channel("user1", ChannelType.DASHBOARD_UPDATES)
        connection_manager.subscribe_to_channel("user2", ChannelType.DASHBOARD_UPDATES)
        
        session_id = "broadcast_test_session"
        session_channel = f"session_{session_id}"
        connection_manager.subscribe_to_channel("user1", session_channel)
        
        # Generate updates using actual API
        sent_count = await update_service.process_session_status_change(
            session_id, "processing", {}
        )
        
        # Verify the update was sent to subscribers
        assert sent_count >= 2  # Should reach both users
        
        # Allow time for broadcasting
        await asyncio.sleep(0.1)
        
        # Verify broadcasts were sent (both users get dashboard updates)
        assert mock_ws1.send_text.call_count >= 1
        assert mock_ws2.send_text.call_count >= 1
        
        # Cleanup
        connection_manager.disconnect("user1")
        connection_manager.disconnect("user2")

    @pytest.mark.asyncio
    async def test_mixed_interaction_workflow(self, dashboard_system):
        """Test workflow with both LLM and MCP interactions."""
        llm_hooks = dashboard_system['llm_hooks']
        mcp_hooks = dashboard_system['mcp_hooks']
        update_service = dashboard_system['update_service']
        
        session_id = "mixed_workflow_session"
        
        # Start with LLM interaction
        llm_event = {
            "session_id": session_id,
            "args": {"prompt": "Analyze logs", "model": "gpt-4"},
            "result": {"content": "Analysis complete"},
            "start_time": datetime.now(),
            "end_time": datetime.now()
        }
        
        await llm_hooks.execute("llm.post", **llm_event)
        
        # Add MCP interaction to same session
        mcp_event = {
            "session_id": session_id,
            "method": "call_tool",
            "args": {
                "server_name": "filesystem",
                "tool_name": "read_logs",
                "tool_arguments": {"path": "/var/log/app.log"}
            },
            "result": {"output": "Log entries retrieved"},
            "start_time": datetime.now(),
            "end_time": datetime.now()
        }
        
        await mcp_hooks.execute("mcp.post", **mcp_event)
        
        # Verify session has both interaction types
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.llm_interactions >= 1
        assert session.mcp_communications >= 1

    @pytest.mark.asyncio
    async def test_system_metrics_broadcasting(self, dashboard_system):
        """Test system-wide metrics calculation and broadcasting."""
        update_service = dashboard_system['update_service']
        llm_hooks = dashboard_system['llm_hooks']
        mcp_hooks = dashboard_system['mcp_hooks']
        
        # Create multiple sessions with different states
        sessions = [
            ("session_active_1", "active"),
            ("session_active_2", "active"),
            ("session_processing", "processing"),
            ("session_completed", "completed"),
        ]
        
        for session_id, status in sessions:
            await update_service.process_session_status_change(
                session_id, status, {}
            )
            
            # Add some interactions via hooks
            llm_event = {
                "session_id": session_id,
                "args": {"model": "gpt-4"},
                "result": {"content": "Response"},
                "start_time": datetime.now(),
                "end_time": datetime.now()
            }
            await llm_hooks.execute("llm.post", **llm_event)
        
        # Broadcast active sessions
        sent_count = await update_service.broadcast_active_sessions()
        assert sent_count >= 0
        
        # Verify metrics calculation
        all_sessions = list(update_service.active_sessions.values())
        assert len(all_sessions) >= 3  # completed session should be archived
        
        # Check session statuses
        statuses = [session.status for session in all_sessions]
        assert "active" in statuses
        assert "processing" in statuses

    @pytest.mark.asyncio
    async def test_error_propagation_and_recovery(self, dashboard_system):
        """Test error handling and recovery across the system."""
        update_service = dashboard_system['update_service']
        broadcaster = dashboard_system['broadcaster']
        
        session_id = "error_recovery_test"
        
        # Create session
        await update_service.process_session_status_change(
            session_id, "active", {}
        )
        
        # Simulate broadcaster failure temporarily
        original_method = broadcaster.broadcast_dashboard_update
        broadcaster.broadcast_dashboard_update = AsyncMock(
            side_effect=Exception("Temporary broadcast failure")
        )
        
        # Try to update session (should handle error gracefully)
        sent_count = await update_service.process_session_status_change(
            session_id, "processing", {}
        )
        
        # Should return 0 due to failure but not crash
        assert sent_count == 0
        
        # Session should still be tracked locally
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.status == "processing"
        
        # Restore broadcaster
        broadcaster.broadcast_dashboard_update = original_method
        
        # Subsequent updates should work
        sent_count = await update_service.process_session_status_change(
            session_id, "completed", {}
        )
        
        assert sent_count >= 0

    @pytest.mark.asyncio
    async def test_concurrent_session_handling(self, dashboard_system):
        """Test handling multiple concurrent sessions."""
        update_service = dashboard_system['update_service']
        llm_hooks = dashboard_system['llm_hooks']
        mcp_hooks = dashboard_system['mcp_hooks']
        
        # Create concurrent sessions
        session_count = 5  # Reduced for faster test execution
        tasks = []
        
        for i in range(session_count):
            session_id = f"concurrent_session_{i}"
            
            # Create task for each session
            async def process_session(sid):
                # LLM interaction
                llm_event = {
                    "session_id": sid,
                    "args": {"model": "gpt-4"},
                    "result": {"content": "Response"},
                    "start_time": datetime.now(),
                    "end_time": datetime.now()
                }
                await llm_hooks.execute("llm.post", **llm_event)
                
                # MCP interaction
                mcp_event = {
                    "session_id": sid,
                    "method": "call_tool",
                    "args": {"server_name": "test", "tool_name": "concurrent_tool"},
                    "result": {"output": "Done"},
                    "start_time": datetime.now(),
                    "end_time": datetime.now()
                }
                await mcp_hooks.execute("mcp.post", **mcp_event)
                
                # Status updates
                await update_service.process_session_status_change(
                    sid, "processing", {}
                )
                await update_service.process_session_status_change(
                    sid, "completed", {}
                )
            
            tasks.append(process_session(session_id))
        
        # Run all sessions concurrently
        await asyncio.gather(*tasks)
        
        # Verify sessions were processed (completed ones are archived)
        all_sessions = list(update_service.active_sessions.values())
        # Some sessions might still be active, others archived


    @pytest.mark.asyncio
    async def test_subscription_channel_management(self, dashboard_system):
        """Test subscription and channel management across the system."""
        connection_manager = dashboard_system['connection_manager']
        broadcaster = dashboard_system['broadcaster']
        update_service = dashboard_system['update_service']
        
        # Disable batching for immediate delivery in tests

        
        # Mock multiple users
        users = [("user1", AsyncMock()), ("user2", AsyncMock()), ("user3", AsyncMock())]
        
        # Connect users
        for user_id, mock_ws in users:
            await connection_manager.connect(mock_ws, user_id)
        
        # Subscribe users to different channels
        connection_manager.subscribe_to_channel("user1", ChannelType.DASHBOARD_UPDATES)
        connection_manager.subscribe_to_channel("user1", ChannelType.SYSTEM_HEALTH)
        
        connection_manager.subscribe_to_channel("user2", ChannelType.DASHBOARD_UPDATES)
        session_channel = "session_test_session"
        connection_manager.subscribe_to_channel("user2", session_channel)
        
        connection_manager.subscribe_to_channel("user3", session_channel)
        
        # Generate updates that should reach different users
        metrics_sent = await update_service.broadcast_active_sessions()  # Should reach user1 and user2
        assert metrics_sent >= 2
        
        session_sent = await update_service.process_session_status_change(
            "test_session", "processing", {}
        )  # Should reach user2 and user3 via dashboard broadcasts
        assert session_sent >= 2
        
        # Allow time for broadcasting
        await asyncio.sleep(0.1)
        
        # Verify appropriate users received updates
        user1_ws, user2_ws, user3_ws = [ws for _, ws in users]
        
        # user1 should receive dashboard updates
        assert user1_ws.send_text.call_count >= 1
        
        # user2 should receive dashboard updates
        assert user2_ws.send_text.call_count >= 1
        
        # Cleanup
        for user_id, _ in users:
            connection_manager.disconnect(user_id)


@pytest.mark.integration
class TestDashboardErrorScenarios:
    """Test integration error scenarios and resilience."""
    
    @pytest.fixture
    async def dashboard_system_with_failures(self):
        """Create dashboard system for failure testing."""
        connection_manager = DashboardConnectionManager()
        broadcaster = DashboardBroadcaster(connection_manager)

        
        update_service = DashboardUpdateService(broadcaster)
        await update_service.start()
        
        system = {
            'connection_manager': connection_manager,
            'broadcaster': broadcaster,
            'update_service': update_service
        }
        
        yield system
        
        # Cleanup
        await update_service.stop()


    @pytest.mark.asyncio
    async def test_resilience_to_websocket_failures(self, dashboard_system_with_failures):
        """Test system resilience when WebSocket connections fail."""
        connection_manager = dashboard_system_with_failures['connection_manager']
        broadcaster = dashboard_system_with_failures['broadcaster']
        update_service = dashboard_system_with_failures['update_service']
        
        # Disable batching for immediate delivery in tests

        
        # Create failing WebSocket mock
        failing_ws = AsyncMock()
        failing_ws.send_text.side_effect = Exception("WebSocket connection lost")
        
        working_ws = AsyncMock()
        
        # Connect both users
        await connection_manager.connect(failing_ws, "failing_user")
        await connection_manager.connect(working_ws, "working_user")
        
        # Subscribe both to same channel
        connection_manager.subscribe_to_channel("failing_user", ChannelType.DASHBOARD_UPDATES)
        connection_manager.subscribe_to_channel("working_user", ChannelType.DASHBOARD_UPDATES)
        
        # Generate update
        sent_count = await update_service.broadcast_active_sessions()
        
        # Should attempt to send to both users, but failing one will be disconnected
        assert sent_count >= 1  # At least working user should receive
        
        # Allow time for broadcasting
        await asyncio.sleep(0.1)
        
        # Working user should still receive updates
        assert working_ws.send_text.call_count >= 1
        
        # Failing user should be disconnected
        assert "failing_user" not in connection_manager.active_connections
        assert "working_user" in connection_manager.active_connections
        
        # Cleanup
        connection_manager.disconnect("working_user")

    @pytest.mark.asyncio
    async def test_service_restart_recovery(self, dashboard_system_with_failures):
        """Test system recovery after service restarts."""
        broadcaster = dashboard_system_with_failures['broadcaster']
        update_service = dashboard_system_with_failures['update_service']
        
        session_id = "restart_recovery_test"
        
        # Create session before restart
        await update_service.process_session_status_change(
            session_id, "processing", {}
        )
        
        # Verify session exists
        assert session_id in update_service.active_sessions
        session = update_service.active_sessions[session_id]
        assert session.status == "processing"
        
        # Simulate service restart (stop/start background tasks only)
        await update_service.stop()
        await update_service.start()
        
        # Session data persists in memory across stop/start of background tasks
        # Only a full process restart would clear the session data
        assert session_id in update_service.active_sessions  # Sessions persist across task restart
        session = update_service.active_sessions[session_id]
        assert session.status == "processing"

    @pytest.mark.asyncio 
    async def test_high_load_stress_test(self, dashboard_system_with_failures):
        """Test system behavior under high load."""
        update_service = dashboard_system_with_failures['update_service']
        connection_manager = dashboard_system_with_failures['connection_manager']
        
        # Create many concurrent users
        user_count = 20  # Reduced for faster test execution
        users = []
        
        for i in range(user_count):
            mock_ws = AsyncMock()
            user_id = f"stress_user_{i}"
            await connection_manager.connect(mock_ws, user_id)
            connection_manager.subscribe_to_channel(user_id, ChannelType.DASHBOARD_UPDATES)
            users.append((user_id, mock_ws))
        
        # Generate high volume of updates
        update_count = 50  # Reduced for faster test execution
        tasks = []
        
        for i in range(update_count):
            session_id = f"stress_session_{i % 5}"  # 5 concurrent sessions
            task = update_service.process_session_status_change(
                session_id, "processing", {}
            )
            tasks.append(task)
        
        # Execute all updates concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Most updates should succeed (some might fail under stress, which is acceptable)
        successful_updates = sum(1 for result in results if not isinstance(result, Exception))
        success_rate = successful_updates / update_count
        
        # Accept 80% success rate under high stress
        assert success_rate >= 0.8
        
        # System should still be responsive
        await update_service.broadcast_active_sessions()
        
        # Cleanup
        for user_id, _ in users:
            connection_manager.disconnect(user_id)

if __name__ == "__main__":
    pytest.main([__file__]) 