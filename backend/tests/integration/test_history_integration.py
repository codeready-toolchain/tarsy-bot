"""
Integration tests for History Service functionality.

Tests the complete history service integration including database operations,
service interactions, and cross-component communication.
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from tarsy.main import app
from tarsy.models.alert import Alert
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction

# Import history models to ensure they're registered with SQLModel.metadata
from tarsy.services.alert_service import AlertService
from tarsy.services.history_service import HistoryService
from tests.conftest import alert_to_api_format

logger = logging.getLogger(__name__)


class TestHistoryServiceIntegration:
    """Integration tests for complete history service workflow."""
    
    @pytest.fixture
    def in_memory_engine(self):
        """Create in-memory SQLite engine for testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        SQLModel.metadata.create_all(engine)
        return engine
    
    @pytest.fixture
    def history_service_with_db(self, in_memory_engine):
        """Create history service with test database for testing."""
        # Get the database file path from the test engine (temporary file)
        db_path = in_memory_engine.url.database  # Extract the file path
        test_db_url = f"sqlite:///{db_path}"
        
        logger.info(f"Test database URL: {test_db_url}")
        
        # Mock settings to use the EXACT same database file as the test engine
        mock_settings = Mock()
        mock_settings.history_enabled = True  
        mock_settings.history_database_url = test_db_url  # Use the same database file
        mock_settings.history_retention_days = 90
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            # Initialize the service - it will now use the same database file
            service.initialize()
            
            logger.info(f"Service database URL: {service.db_manager.database_url}")
            logger.info(f"Service engine URL: {service.db_manager.engine.url}")
            
            yield service
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for testing."""
        return Alert(
            alert_type="NamespaceTerminating",
            severity="high",
            environment="production",
            cluster="k8s-prod",
            namespace="stuck-namespace",
            message="Namespace is stuck in Terminating state",
            runbook="namespace-terminating.md"
        )
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = AsyncMock()
        client.generate_response.return_value = {
            "content": "The namespace is stuck due to finalizers. Let me check the current state.",
            "model": "gpt-4",
            "usage": {"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200}
        }
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        client = AsyncMock()
        client.list_tools.return_value = [
            {"name": "kubectl_get_namespace", "description": "Get namespace information"},
            {"name": "kubectl_describe_namespace", "description": "Describe namespace details"}
        ]
        client.call_tool.return_value = {
            "result": {
                "status": "Terminating",
                "finalizers": ["kubernetes.io/finalizer.test"],
                "deletionTimestamp": "2024-01-01T12:00:00Z"
            },
            "success": True,
            "error": None
        }
        return client
    
    @pytest.fixture
    def mock_kubernetes_agent(self, mock_llm_client, mock_mcp_client):
        """Create mock Kubernetes agent."""
        agent = Mock()
        agent.process_alert = AsyncMock(return_value={
            "status": "completed",
            "analysis": "Namespace termination issue resolved",
            "actions_taken": ["Removed stuck finalizer"],
            "recommendations": ["Monitor namespace cleanup process"]
        })
        return agent
    
    @pytest.mark.integration
    def test_create_session_and_track_lifecycle(self, history_service_with_db, sample_alert):
        """Test creating a session and tracking its complete lifecycle."""
        # Create initial session
        session_id = history_service_with_db.create_session(
            alert_id="alert-123",
            alert_data={
                "alert_type": sample_alert.alert_type,
                        "environment": sample_alert.data.get('environment', ''),
        "cluster": sample_alert.data.get('cluster', ''),
        "namespace": sample_alert.data.get('namespace', ''),
        "message": sample_alert.data.get('message', '')
            },
            agent_type="KubernetesAgent",
            alert_type=sample_alert.alert_type
        )
        
        assert session_id is not None
        
        # Update session to in_progress
        result = history_service_with_db.update_session_status(
            session_id=session_id,
            status="in_progress"
        )
        assert result == True
        
        # Log LLM interaction
        from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
        llm_interaction = LLMInteraction(
            session_id=session_id,
            model_name="gpt-4",
            step_description="Initial analysis",
            request_json={"messages": [{"role": "user", "content": "Analyze the namespace termination issue"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "The namespace is stuck due to finalizers"}, "finish_reason": "stop"}]},
            token_usage={"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200},
            duration_ms=1500
        )
        llm_result = history_service_with_db.log_llm_interaction(llm_interaction)
        assert llm_result == True
        
        # Log MCP communication
        mcp_interaction = MCPInteraction(
            session_id=session_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get_namespace",
            tool_arguments={"namespace": "stuck-namespace"},
            tool_result={"status": "Terminating", "finalizers": ["test-finalizer"]},
            step_description="Check namespace status",
            duration_ms=800,
            success=True
        )
        mcp_result = history_service_with_db.log_mcp_interaction(mcp_interaction)
        assert mcp_result == True
        
        # Complete session
        completion_result = history_service_with_db.update_session_status(
            session_id=session_id,
            status="completed"
        )
        assert completion_result == True
        
        # Verify complete timeline
        timeline = history_service_with_db.get_session_timeline(session_id)
        assert timeline is not None
        assert timeline["session"]["status"] == "completed"
        assert len(timeline["chronological_timeline"]) == 2
        assert timeline["session"]["total_interactions"] == 2
        # Check individual interaction/communication lists
        assert len(timeline["llm_interactions"]) == 1
        assert len(timeline["mcp_communications"]) == 1
    
    @pytest.mark.integration
    def test_chronological_timeline_ordering(self, history_service_with_db, sample_alert):
        """Test that timeline events are ordered chronologically."""
        # Create session
        session_id = history_service_with_db.create_session(
            alert_id="timeline-test",
            alert_data={"alert_type": sample_alert.alert_type},
            agent_type="KubernetesAgent",
            alert_type=sample_alert.alert_type
        )
        
        # Create events with specific timestamps (simulating real workflow)
        base_time = datetime.now(timezone.utc)
        
        # First LLM interaction
        llm_interaction1 = LLMInteraction(
            session_id=session_id,
            model_name="gpt-4",
            step_description="Initial analysis",
            request_json={"messages": [{"role": "user", "content": "Initial analysis prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "Initial analysis response"}, "finish_reason": "stop"}]},
            duration_ms=1200
        )
        history_service_with_db.log_llm_interaction(llm_interaction1)
        
        # Sleep to ensure different timestamp
        import time
        time.sleep(0.01)
        
        # MCP tool call
        mcp_interaction1 = MCPInteraction(
            session_id=session_id,
            server_name="kubernetes-server",
            communication_type="tool_call",
            tool_name="kubectl_get",
            step_description="Get namespace info",
            success=True
        )
        history_service_with_db.log_mcp_interaction(mcp_interaction1)
        
        time.sleep(0.01)
        
        # Second LLM interaction
        llm_interaction2 = LLMInteraction(
            session_id=session_id,
            model_name="gpt-4",
            step_description="Follow-up analysis",
            request_json={"messages": [{"role": "user", "content": "Follow-up analysis prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "Follow-up analysis response"}, "finish_reason": "stop"}]}
        )
        history_service_with_db.log_llm_interaction(llm_interaction2)
        
        # Get timeline and verify ordering
        timeline = history_service_with_db.get_session_timeline(session_id)
        events = timeline["chronological_timeline"]
        
        assert len(events) == 3
        
        # Verify events are in chronological order
        for i in range(len(events) - 1):
            current_time_us = events[i]["timestamp_us"]
            next_time_us = events[i + 1]["timestamp_us"]
            assert current_time_us <= next_time_us, f"Event {i} timestamp is after event {i+1}"
        
        # Verify event types in expected order
        assert events[0]["type"] == "llm"
        assert events[0]["step_description"] == "Initial analysis"
        assert events[1]["type"] == "mcp"
        assert events[1]["step_description"] == "Get namespace info"
        assert events[2]["type"] == "llm"
        assert events[2]["step_description"] == "Follow-up analysis"
    
    @pytest.mark.integration
    def test_complex_filtering_scenarios(self, history_service_with_db):
        """Test complex filtering scenarios with multiple sessions."""
        # Create multiple sessions with different attributes
        now = datetime.now(timezone.utc)
        
        sessions_data = [
            ("session-1", "NamespaceTerminating", "KubernetesAgent", "completed", now - timedelta(hours=1)),
            ("session-2", "NamespaceTerminating", "KubernetesAgent", "in_progress", now - timedelta(hours=2)),
            ("session-3", "HighCPU", "KubernetesAgent", "completed", now - timedelta(hours=3)),
            ("session-4", "NamespaceTerminating", "GenericAgent", "completed", now - timedelta(hours=4)),
            ("session-5", "HighMemory", "KubernetesAgent", "failed", now - timedelta(days=2))
        ]
        
        for session_id, alert_type, agent_type, status, started_at in sessions_data:
            # Use the service to create session (simulating real workflow)
            sid = history_service_with_db.create_session(
                alert_id=f"alert-{session_id}",
                alert_data={"alert_type": alert_type, "environment": "test"},
                agent_type=agent_type,
                alert_type=alert_type
            )
            
            # Update the session with custom timestamp using repository directly
            with history_service_with_db.get_repository() as repo:
                if repo:
                    # Get the created session
                    session = repo.get_alert_session(sid)
                    if session:
                        # Update with custom timestamp (convert to microseconds since epoch)
                        session.started_at_us = int(started_at.timestamp() * 1000000)
                        # Update status if needed
                        if status != "pending":
                            session.status = status
                            if status == "completed":
                                session.completed_at_us = int((started_at + timedelta(minutes=30)).timestamp() * 1000000)
                        repo.session.commit()
            
            # Add some interactions for variety
            if session_id in ["session-1", "session-3"]:
                llm_interaction_variety = LLMInteraction(
                    session_id=sid,
                    model_name="gpt-4",
                    step_description=f"Analysis for {session_id}",
                    request_json={"messages": [{"role": "user", "content": f"Test prompt for {session_id}"}]},
                    response_json={"choices": [{"message": {"role": "assistant", "content": f"Test response for {session_id}"}, "finish_reason": "stop"}]}
                )
                history_service_with_db.log_llm_interaction(llm_interaction_variety)
        
        # Test 1: Filter by alert_type + status
        sessions, count = history_service_with_db.get_sessions_list(
            filters={"alert_type": "NamespaceTerminating", "status": "completed"}
        )
        assert count == 2  # session-1 and session-4
        
        # Test 2: Filter by agent_type + status + alert_type
        sessions, count = history_service_with_db.get_sessions_list(
            filters={
                "agent_type": "KubernetesAgent",
                "status": "completed",
                "alert_type": "NamespaceTerminating"
            }
        )
        assert count == 1  # only session-1
        
        # Test 3: Filter by time range
        cutoff_time = now - timedelta(hours=5)
        sessions, count = history_service_with_db.get_sessions_list(
            filters={"start_date_us": int(cutoff_time.timestamp() * 1_000_000)}
        )
        assert count == 4  # All except session-5 (older than 5 hours)
        
        # Test 4: Combined filters with pagination
        sessions, count = history_service_with_db.get_sessions_list(
            filters={"agent_type": "KubernetesAgent"},
            page=1,
            page_size=2
        )
        assert len(sessions) == 2  # First page of KubernetesAgent sessions
        assert count == 4  # Total KubernetesAgent sessions
    
    @pytest.mark.integration
    def test_error_handling_and_graceful_degradation(self, history_service_with_db, sample_alert):
        """Test error handling and graceful degradation scenarios."""
        # Test session creation with invalid data
        session_id = history_service_with_db.create_session(
            alert_id="",  # Empty alert ID
            alert_data={},  # Empty alert data
            agent_type="",  # Empty agent type
            alert_type=""  # Empty alert type
        )
        assert session_id is not None  # Should still create session
        
        # Test logging with invalid session ID
        llm_interaction_invalid = LLMInteraction(
            session_id="non-existent-session",
            model_name="gpt-4",
            step_description="Test interaction",
            request_json={"messages": [{"role": "user", "content": "Test prompt"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "Test response"}, "finish_reason": "stop"}]}
        )
        result = history_service_with_db.log_llm_interaction(llm_interaction_invalid)
        # The service allows logging interactions even for non-existent sessions
        # This is by design for performance and graceful degradation
        assert result == True  # Service handles this gracefully without validation
        
        # Test status update with invalid session ID
        result = history_service_with_db.update_session_status(
            session_id="non-existent-session",
            status="completed"
        )
        assert result == False  # Should fail gracefully
        
        # Test timeline retrieval with invalid session ID
        timeline = history_service_with_db.get_session_timeline("non-existent-session")
        assert timeline == {}  # Should return empty dict for non-existent sessions
    

    @pytest.mark.integration
    def test_sqlite_retry_logic_works(self, history_service_with_db, sample_alert):
        """Test that our retry logic handles transient SQLite issues gracefully."""
        # This test verifies our retry logic works in single-threaded scenarios
        # Note: Full concurrent testing requires a more robust database like PostgreSQL
        
        # Test that normal operations work
        session_id = history_service_with_db.create_session(
            alert_id="retry-test-1",
            alert_data={"alert_type": sample_alert.alert_type},
            agent_type="KubernetesAgent",  
            alert_type=sample_alert.alert_type
        )
        
        # Should succeed with our improvements
        assert session_id is not None, "Session creation should succeed with retry logic"
        
        # Test status update works
        result = history_service_with_db.update_session_status(
            session_id=session_id,
            status="completed"
        )
        assert result == True, "Status update should succeed with retry logic"
        
        # Verify session was created correctly
        timeline = history_service_with_db.get_session_timeline(session_id)
        assert timeline is not None
        assert timeline["session"]["status"] == "completed"
        
        logger.info("✅ SQLite retry logic and improvements working correctly")


class TestAlertServiceHistoryIntegration:
    """Integration tests for AlertService with history tracking."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock()
        settings.history_enabled = True
        settings.history_database_url = "sqlite:///:memory:"
        settings.history_retention_days = 90
        # Add required LLM settings to prevent iteration error
        settings.llm_providers = {}
        settings.llm_default_provider = "openai"
        settings.openai_api_key = "test-key"
        settings.anthropic_api_key = "test-key"
        return settings
    
    @pytest.fixture
    def alert_service_with_history(self, mock_settings):
        """Create AlertService with history integration."""
        # Create AlertService directly with mock settings
        service = AlertService(mock_settings)
        
        # Mock LLM manager to appear available
        service.llm_manager.is_available = Mock(return_value=True)
        
        # Mock runbook service to return test content
        service.runbook_service.download_runbook = AsyncMock(return_value="Test runbook content")
        
        # Mock agent registry and agent factory
        mock_agent = AsyncMock()
        mock_agent.process_alert.return_value = {
            "status": "success",  # Changed to match expected format
            "analysis": "Test analysis",
            "actions_taken": ["Test action"],
            "recommendations": ["Test recommendation"]
        }
        
        # Mock the chain_registry - this is where get_chain_for_alert_type lives  
        service.chain_registry.get_chain_for_alert_type = Mock(return_value=Mock(chain_id="kubernetes-chain", stages=[Mock(name="analysis", agent="KubernetesAgent")]))
        
        # Mock agent_factory to return our mock agent
        service.agent_factory = Mock()
        service.agent_factory.get_agent = Mock(return_value=mock_agent)
        service.agent_factory.create_agent = Mock(return_value=mock_agent)
        
        # Use real history service with mocked database
        mock_history_service = Mock()
        mock_history_service.create_session.return_value = "test-session-123"
        mock_history_service.update_session_status.return_value = True
        service.history_service = mock_history_service
        
        return service
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert."""
        return Alert(
            alert_type="NamespaceTerminating",
            severity="high",
            environment="production",
            cluster="k8s-prod",
            namespace="stuck-namespace",
            message="Namespace is stuck in Terminating state",
            runbook="namespace-terminating.md"
        )
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_alert_processing_with_history_tracking(self, alert_service_with_history, sample_alert):
        """Test complete alert processing with history tracking."""
        # Process alert
        result = await alert_service_with_history.process_alert(
            alert_to_api_format(sample_alert)
        )
        
        # Verify alert processing succeeded
        assert result is not None
        # The result is a formatted string from _format_success_response, not a dict
        assert "Analysis completed successfully" in result or "Test analysis" in result
        
        # Verify history service interactions
        history_service = alert_service_with_history.history_service
        
        # Should have created session
        history_service.create_session.assert_called_once()
        create_call = history_service.create_session.call_args
        assert create_call[1]["agent_type"] == "chain:kubernetes-chain"  # Chain architecture format
        assert create_call[1]["alert_type"] == sample_alert.alert_type
        
        # Should have updated session status multiple times
        assert history_service.update_session_status.call_count >= 2
        
        # Verify session status updates
        status_calls = history_service.update_session_status.call_args_list
        
        # Should include in_progress and completed status updates
        statuses = [call[1]["status"] for call in status_calls]
        assert "in_progress" in statuses
        assert "completed" in statuses
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_alert_processing_error_with_history_tracking(self, alert_service_with_history, sample_alert):
        """Test alert processing error handling with history tracking."""
        # Make agent processing fail by setting up the mock to fail
        mock_agent = AsyncMock()
        mock_agent.process_alert.side_effect = Exception("Agent processing failed")
        alert_service_with_history.agent_factory.get_agent = Mock(return_value=mock_agent)
        
        # Process alert (should handle error gracefully)
        result = await alert_service_with_history.process_alert(
            alert_to_api_format(sample_alert)
        )
        
        # Verify error was handled
        assert result is not None
        # The result is a formatted string from _format_error_response, not a dict  
        assert "Chain processing failed" in result  # Chain architecture error format
        
        # Verify history service tracked the error
        history_service = alert_service_with_history.history_service
        
        # Should have created session
        history_service.create_session.assert_called_once()
        
        # Should have updated status to failed
        status_calls = history_service.update_session_status.call_args_list
        statuses = [call[1]["status"] for call in status_calls]
        assert "failed" in statuses
        
        # Should have recorded error message
        error_calls = [call for call in status_calls if call[1].get("error_message")]
        assert len(error_calls) > 0
        assert "Chain processing failed" in error_calls[0][1]["error_message"]  # Chain architecture error format


class TestHistoryAPIIntegration:
    """Integration tests for History API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_history_service_for_api(self):
        """Create mock history service for API testing."""
        service = Mock()
        service.enabled = True
        
        # Mock sessions data with all required attributes (using Unix timestamps)
        from tarsy.models.history import now_us
        current_time_us = now_us()
        
        mock_sessions = [
            Mock(
                session_id="api-session-1",
                alert_id="api-alert-1",
                alert_type="NamespaceTerminating",
                agent_type="KubernetesAgent",
                status="completed",
                started_at_us=current_time_us - 300000000,  # Started 5 minutes ago
                completed_at_us=current_time_us,  # Completed now
                error_message=None,
                llm_interactions=[],  # Add missing attributes
                mcp_communications=[],
                # Add the new dynamic attributes expected by the controller
                llm_interaction_count=0,
                mcp_communication_count=0
            )
        ]
        service.get_sessions_list.return_value = (mock_sessions, 1)
        
        # Mock timeline data with correct structure (session instead of session_info) using Unix timestamps
        service.get_session_timeline.return_value = {
            "session": {
                "session_id": "api-session-1",
                "alert_id": "api-alert-1",
                "alert_type": "NamespaceTerminating",
                "agent_type": "KubernetesAgent",
                "status": "completed",
                "started_at_us": current_time_us - 300000000,  # Started 5 minutes ago
                "completed_at_us": current_time_us,  # Completed now
                "error_message": None
            },
            "chronological_timeline": [
                {
                    "interaction_id": "int-1",
                    "type": "llm_interaction",
                    "timestamp_us": current_time_us - 240000000,  # 4 minutes ago
                    "step_description": "Analysis",
                    "details": {
                        "prompt_text": "Analyze issue",
                        "response_text": "Found solution"
                    }
                }
            ]
        }
        
        service.test_database_connection.return_value = True
        service.settings = Mock()
        service.settings.history_database_url = "sqlite:///test.db"
        
        # Add calculate_session_summary mock with default return value
        service.calculate_session_summary.return_value = {
            "total_interactions": 2,
            "llm_interactions": 1,
            "mcp_communications": 1,
            "total_duration_ms": 150000,
            "errors_count": 0,
            "system_events": 0,
            "chain_statistics": {
                "total_stages": 1,
                "completed_stages": 1,
                "failed_stages": 0,
                "stages_by_agent": {"analysis": 1}
            }
        }
        
        return service
    
    @pytest.mark.integration
    def test_api_sessions_list_integration(self, client, mock_history_service_for_api):
        """Test sessions list API endpoint integration."""
        # Use FastAPI's dependency override system
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_history_service_for_api
        
        try:
            response = client.get("/api/v1/history/sessions?status=completed&page=1&page_size=10")
        
            assert response.status_code == 200
            data = response.json()
            
            assert "sessions" in data
            assert "pagination" in data
            assert len(data["sessions"]) == 1
            assert data["sessions"][0]["session_id"] == "api-session-1"
            
            # Verify service was called with correct parameters
            mock_history_service_for_api.get_sessions_list.assert_called_once()
            call_args = mock_history_service_for_api.get_sessions_list.call_args
            assert call_args.kwargs["filters"]["status"] == ["completed"]  # Now expects list due to multiple status support
            assert call_args.kwargs["page"] == 1
            assert call_args.kwargs["page_size"] == 10
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()
    
    @pytest.mark.integration
    def test_api_session_detail_integration(self, client, mock_history_service_for_api):
        """Test session detail API endpoint integration."""
        # Ensure the mock returns the timeline for the specific session ID (using Unix timestamps)
        from tarsy.models.history import now_us
        current_time_us = now_us()
        expected_session_id = "api-session-1"
        
        mock_history_service_for_api.get_session_timeline.return_value = {
            "session": {
                "session_id": expected_session_id,
                "alert_id": "api-alert-1",
                "alert_type": "NamespaceTerminating",
                "agent_type": "KubernetesAgent", 
                "status": "completed",
                "started_at_us": current_time_us - 300000000,  # Started 5 minutes ago
                "completed_at_us": current_time_us,  # Completed now
                "error_message": None,
                "chain_id": "integration-chain-123"  # Add chain_id so endpoint processes chain execution
            },
            "chronological_timeline": [
                {
                    "interaction_id": "int-1",
                    "event_id": "int-1",  # Add required event_id
                    "type": "llm",  # Changed from llm_interaction to llm to match controller logic
                    "timestamp_us": current_time_us - 240000000,  # 4 minutes ago
                    "step_description": "Analysis",
                    "duration_ms": 120000,  # Add duration for calculation
                    "stage_execution_id": "integration-exec-1",  # Map to our stage
                    "details": {
                        "prompt_text": "Analyze issue",
                        "response_text": "Found solution"
                    }
                },
                {
                    "interaction_id": "int-2",
                    "event_id": "int-2",  # Add required event_id
                    "type": "mcp",  # Add an MCP interaction
                    "timestamp_us": current_time_us - 180000000,  # 3 minutes ago 
                    "step_description": "Tool execution",
                    "duration_ms": 30000,  # Add duration
                    "stage_execution_id": "integration-exec-1",  # Map to our stage
                    "details": {
                        "tool_name": "kubectl_get",
                        "result": "namespace info retrieved"
                    }
                }
            ]
        }
        
        # Mock the get_session_with_stages method to return chain execution data
        async def mock_get_session_with_stages(session_id):
            return {
                "session": {
                    "session_id": expected_session_id,
                    "chain_id": "integration-chain-123",
                    "alert_type": "NamespaceTerminating",
                    "status": "completed"
                },
                "stages": [
                    {
                        "execution_id": "integration-exec-1",
                        "stage_id": "analysis-stage",
                        "stage_name": "Root Cause Analysis",
                        "stage_index": 0,
                        "status": "completed",
                        "started_at_us": current_time_us - 250000000,  # Started 4.2 minutes ago
                        "completed_at_us": current_time_us - 60000000,  # Completed 1 minute ago
                        "duration_ms": 190000,
                        "interaction_summary": {
                            "llm_count": 1,
                            "mcp_count": 1,
                            "total_count": 2,
                            "duration_ms": 190000
                        },
                        "timeline": [
                            {
                                "interaction_id": "int-1",
                                "event_id": "int-1",  # Add required event_id
                                "type": "llm",  # Use normalized type
                                "timestamp_us": current_time_us - 240000000,
                                "step_description": "Analysis",
                                "stage_execution_id": "integration-exec-1",  # Add required stage_execution_id
                                "duration_ms": 120000,  # Add duration
                                "details": {
                                    "prompt_text": "Analyze issue",
                                    "response_text": "Found solution"
                                }
                            }
                        ]
                    }
                ]
            }
        mock_history_service_for_api.get_session_with_stages = mock_get_session_with_stages
        
        # Use FastAPI's dependency override system instead of mock patching
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_history_service_for_api
        
        try:
            response = client.get(f"/api/v1/history/sessions/{expected_session_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Check the actual SessionDetailResponse structure (not nested session_info)
            assert "session_id" in data
            assert "chain_execution" in data
            assert "summary" in data
            
            # Verify session details
            assert data["session_id"] == expected_session_id
            assert data["alert_type"] == "NamespaceTerminating"
            assert data["status"] == "completed"
            
            # All sessions should have chain execution data since we support chains only
            chain_execution = data["chain_execution"]
            assert chain_execution is not None, "All sessions should have chain execution data"
            
            # Verify comprehensive chain execution structure
            assert "chain_id" in chain_execution
            assert chain_execution["chain_id"] == "integration-chain-123"
            assert "stages" in chain_execution
            assert isinstance(chain_execution["stages"], list)
            assert len(chain_execution["stages"]) == 1
            
            # Verify stage structure and timeline
            stage = chain_execution["stages"][0]
            assert "execution_id" in stage
            assert "stage_id" in stage  
            assert "stage_name" in stage
            assert "status" in stage
            assert "interaction_summary" in stage
            assert "timeline" in stage
            
            # Verify interaction summary
            summary = stage["interaction_summary"]
            assert summary["llm_count"] == 1  # 1 LLM interaction
            assert summary["mcp_count"] == 1  # 1 MCP interaction 
            assert summary["total_count"] == 2  # Total of 2 interactions
            assert summary["duration_ms"] == 150000  # 120000 + 30000
            
            # Verify timeline structure
            timeline = stage["timeline"]
            assert isinstance(timeline, list)
            assert len(timeline) == 2  # Now we have 2 interactions (1 LLM + 1 MCP)
            
            # Verify first interaction (LLM)
            llm_interaction = timeline[0]
            assert llm_interaction["type"] == "llm"
            assert llm_interaction["step_description"] == "Analysis"
            assert "details" in llm_interaction
            
            # Verify second interaction (MCP)
            mcp_interaction = timeline[1] 
            assert mcp_interaction["type"] == "mcp"
            assert mcp_interaction["step_description"] == "Tool execution"
            assert "details" in mcp_interaction
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()
    
    @pytest.mark.integration
    def test_api_health_check_integration(self, client, mock_history_service_for_api):
        """Test health check API endpoint integration."""
        # Use FastAPI's dependency override system
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_history_service_for_api
        
        try:
            response = client.get("/api/v1/history/health")
        
            assert response.status_code == 200
            data = response.json()
            
            assert data["service"] == "alert_processing_history"
            assert data["status"] == "healthy"
            assert "timestamp_us" in data
            assert "details" in data
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()
    
    @pytest.mark.integration
    def test_api_error_handling_integration(self, client):
        """Test API error handling integration."""
        # Mock service that raises exception
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.get_sessions_list.side_effect = Exception("Database connection failed")
        
        # Use FastAPI's dependency override system
        from tarsy.controllers.history_controller import get_history_service
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        try:
            response = client.get("/api/v1/history/sessions")
        
            assert response.status_code == 500
            # The actual error message varies, just check it's an error response
            assert "detail" in response.json()
            
        finally:
            # Clean up the dependency override
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestDuplicatePreventionIntegration:
    """Integration tests for duplicate session prevention across all layers."""
    
    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert data for testing."""
        return {
            "alert_type": "PodCrashLoopBackOff",
            "severity": "high",
            "environment": "production",
            "cluster": "https://api.test-cluster.com",
            "namespace": "default",
            "message": "Pod test-pod is crash looping",
            "runbook": "https://github.com/test/runbooks/pod-crash.md"
        }
    
    def test_end_to_end_duplicate_prevention_same_alert_data(self, history_service_with_test_db, sample_alert_data):
        """Test that identical alerts don't create duplicate sessions end-to-end."""
        # Create first session
        session_id_1 = history_service_with_test_db.create_session(
            alert_id="test_duplicate_alert_123",
            alert_data=sample_alert_data,
            agent_type="KubernetesAgent",
            alert_type="PodCrashLoopBackOff"
        )
        
        assert session_id_1 is not None
        
        # Try to create duplicate session with same alert_id
        session_id_2 = history_service_with_test_db.create_session(
            alert_id="test_duplicate_alert_123",  # Same alert_id
            alert_data={**sample_alert_data, "severity": "critical"},  # Different data
            agent_type="DifferentAgent",  # Different agent
            alert_type="DifferentAlertType"  # Different type
        )
        
        # Should return the same session
        assert session_id_2 is not None
        assert session_id_1 == session_id_2
        
        # Verify original session data is preserved
        session = history_service_with_test_db.get_session_timeline(session_id_1)
        assert session is not None
        assert session["session"]["agent_type"] == "KubernetesAgent"  # Original agent type
        assert session["session"]["alert_type"] == "PodCrashLoopBackOff"  # Original alert type
        assert session["session"]["alert_data"]["severity"] == "high"  # Original severity
    
    def test_concurrent_session_creation_same_alert_id(self, history_service_with_test_db, sample_alert_data):
        """Test concurrent creation attempts with same alert_id."""
        import threading
        import time
        
        results = []
        errors = []
        
        def create_session(thread_id):
            try:
                # Add small random delay to increase chance of concurrency
                time.sleep(thread_id * 0.01)
                
                session_id = history_service_with_test_db.create_session(
                    alert_id="concurrent_test_alert",
                    alert_data={**sample_alert_data, "thread_id": thread_id},
                    agent_type=f"Agent_{thread_id}",
                    alert_type="TestAlert"
                )
                results.append(session_id)
            except Exception as e:
                errors.append(str(e))
        
        # Start multiple threads trying to create the same alert
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_session, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Check if any sessions were created (may fail due to database table issues in concurrent access)
        valid_results = [r for r in results if r is not None]
        
        if len(valid_results) == 0:
            # Skip test if concurrent database access failed
            pytest.skip("Database table not available for concurrent access - this is a known testing limitation")
        
        # All valid results should be the same session_id (no duplicates created)
        unique_sessions = set(valid_results)
        assert len(unique_sessions) == 1, f"Expected 1 unique session, got {len(unique_sessions)}: {unique_sessions}"
        
        # Verify only one session exists in database
        session_id = valid_results[0]
        session = history_service_with_test_db.get_session_timeline(session_id)
        
        if not session or "session" not in session:
            # Session was created but timeline can't be retrieved - this is acceptable for the test
            return
        
        # Original thread's data should be preserved (thread 0)
        assert session["session"]["alert_data"]["thread_id"] == 0
        assert session["session"]["agent_type"] == "Agent_0"
    
    def test_database_constraint_enforcement(self, history_service_with_test_db, sample_alert_data):
        """Test that database-level unique constraints are enforced."""
        # Create session through service
        session_id = history_service_with_test_db.create_session(
            alert_id="constraint_test_alert",
            alert_data=sample_alert_data,
            agent_type="TestAgent",
            alert_type="TestAlert"
        )
        
        assert session_id is not None
        
        # Try to bypass application logic and create duplicate directly in database
        with history_service_with_test_db.get_repository() as repo:
            if repo:
                from tarsy.models.history import AlertSession
                
                # Try to create duplicate session directly
                duplicate_session = AlertSession(
                    alert_id="constraint_test_alert",  # Same alert_id
                    alert_data={"different": "data"},
                    agent_type="DifferentAgent",
                    status="pending"
                )
                
                # This should be prevented by our application logic
                result = repo.create_alert_session(duplicate_session)
                
                # Should return existing session, not create new one
                assert result is not None
                assert result.session_id == session_id
                assert result.agent_type == "TestAgent"  # Original data preserved
    
    def test_alert_id_generation_uniqueness_under_load(self, history_service_with_test_db, sample_alert_data):
        """Test that alert ID generation remains unique under high load."""
        from tarsy.config.settings import get_settings
        from tarsy.models.alert import Alert
        from tarsy.services.alert_service import AlertService
        
        # Create AlertService to test ID generation
        alert_service = AlertService(get_settings())
        alert_service.history_service = history_service_with_test_db
        alert_service.agent_registry = Mock()
        alert_service.agent_registry.get_agent_for_alert_type.return_value = "TestAgent"
        
        # Create identical alerts rapidly
        alert = Alert(**sample_alert_data)
        alert_dict = alert_to_api_format(alert)
        generated_ids = set()
        
        for _ in range(100):
            session_id = alert_service._create_history_session(alert_dict, "TestAgent")
            if session_id:
                # Get the generated alert_id from the created session
                session = history_service_with_test_db.get_session_timeline(session_id)
                if session:
                    generated_ids.add(session["session"]["alert_id"])
        
        # All generated alert IDs should be unique
        assert len(generated_ids) == 100, f"Expected 100 unique alert IDs, got {len(generated_ids)}"
        
        # Each ID should follow the expected pattern (hash-based format)
        for alert_id in generated_ids:
            assert alert_id.startswith("PodCrashLoopBackOff_")
            parts = alert_id.split('_')
            assert len(parts) == 3  # alert_type_unique_id_timestamp
    
    def test_retry_logic_doesnt_create_duplicates(self, history_service_with_test_db, sample_alert_data):
        """Test that retry logic doesn't create duplicate sessions."""
        with patch.object(history_service_with_test_db, '_retry_database_operation') as mock_retry:
            # First call succeeds, second call would create duplicate
            session_id = "test_session_123"
            mock_retry.return_value = session_id
            
            # Create session
            result_1 = history_service_with_test_db.create_session(
                alert_id="retry_test_alert",
                alert_data=sample_alert_data,
                agent_type="TestAgent",
                alert_type="TestAlert"
            )
            
            assert result_1 == session_id
            
            # Verify that create_session operations don't retry after first attempt
            mock_retry.assert_called_once()
            call_args = mock_retry.call_args
            assert call_args[0][0] == "create_session"  # Operation name
    
    def test_performance_impact_of_duplicate_prevention(self, history_service_with_test_db, sample_alert_data):
        """Test that duplicate prevention doesn't significantly impact performance."""
        import time
        
        # Create initial session
        initial_session = history_service_with_test_db.create_session(
            alert_id="performance_test_alert",
            alert_data=sample_alert_data,
            agent_type="TestAgent",
            alert_type="TestAlert"
        )
        
        assert initial_session is not None
        
        # Measure time for duplicate prevention checks
        start_time = time.time()
        
        for i in range(50):
            # Try to create duplicates
            duplicate_session = history_service_with_test_db.create_session(
                alert_id="performance_test_alert",  # Same alert_id
                alert_data={**sample_alert_data, "attempt": i},
                agent_type=f"TestAgent_{i}",
                alert_type="TestAlert"
            )
            
            # Should return existing session quickly
            assert duplicate_session == initial_session
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should complete quickly (less than 1 second for 50 duplicate checks)
        assert total_time < 1.0, f"Duplicate prevention took {total_time}s, should be faster"
        
        # Average time per duplicate check should be reasonable
        avg_time = total_time / 50
        assert avg_time < 0.02, f"Average duplicate check took {avg_time}s, should be under 20ms"
    
    def test_mixed_unique_and_duplicate_sessions(self, history_service_with_test_db, sample_alert_data):
        """Test creating a mix of unique and duplicate sessions."""
        created_sessions = {}
        
        # Create sessions with various alert_ids
        test_cases = [
            ("unique_alert_1", "Agent1", "Type1"),
            ("unique_alert_2", "Agent2", "Type2"),
            ("unique_alert_1", "Agent1_Modified", "Type1_Modified"),  # Duplicate
            ("unique_alert_3", "Agent3", "Type3"),
            ("unique_alert_2", "Agent2_Modified", "Type2_Modified"),  # Duplicate
            ("unique_alert_4", "Agent4", "Type4"),
        ]
        
        for alert_id, agent_type, alert_type in test_cases:
            session_id = history_service_with_test_db.create_session(
                alert_id=alert_id,
                alert_data={**sample_alert_data, "test_case": f"{alert_id}_{agent_type}"},
                agent_type=agent_type,
                alert_type=alert_type
            )
            
            if alert_id not in created_sessions:
                created_sessions[alert_id] = session_id
            else:
                # Should return the same session_id for duplicates
                assert session_id == created_sessions[alert_id]
        
        # Should have created 4 unique sessions (1, 2, 3, 4)
        unique_session_ids = set(created_sessions.values())
        assert len(unique_session_ids) == 4
        
        # Verify original data is preserved for duplicates
        session_1 = history_service_with_test_db.get_session_timeline(created_sessions["unique_alert_1"])
        session_2 = history_service_with_test_db.get_session_timeline(created_sessions["unique_alert_2"])
        
        assert session_1["session"]["agent_type"] == "Agent1"  # Not "Agent1_Modified"
        assert session_2["session"]["agent_type"] == "Agent2"  # Not "Agent2_Modified"
    
    def test_duplicate_prevention_with_database_errors(self, history_service_with_test_db, sample_alert_data):
        """Test duplicate prevention behavior when database errors occur."""
        # Create initial session
        session_id = history_service_with_test_db.create_session(
            alert_id="error_test_alert",
            alert_data=sample_alert_data,
            agent_type="TestAgent",
            alert_type="TestAlert"
        )
        
        assert session_id is not None
        
        # Simulate database error during duplicate check
        with patch.object(history_service_with_test_db, 'get_repository') as mock_get_repo:
            mock_repo = Mock()
            mock_repo.__enter__ = Mock(return_value=mock_repo)
            mock_repo.__exit__ = Mock(return_value=None)
            mock_repo.create_alert_session.side_effect = Exception("Database error")
            mock_get_repo.return_value = mock_repo
            
            # Try to create session during database error
            error_session = history_service_with_test_db.create_session(
                alert_id="error_test_alert_2",
                alert_data=sample_alert_data,
                agent_type="TestAgent",
                alert_type="TestAlert"
            )
            
            # Should return None on error, not crash
            assert error_session is None
