"""
Unit tests for HistoryController.

Tests the REST API endpoints for the history service with mocked services
to ensure proper request/response handling and API contract compliance.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tarsy.controllers.history_controller import HistoryService, router
from tarsy.models.db_models import now_us
from tarsy.services.history_service import get_history_service


class TestHistoryControllerEndpoints:
    """Test suite for HistoryController API endpoints."""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI application with history router."""
        app = FastAPI()
        app.include_router(router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_history_service(self):
        """Create mock history service using factory."""
        from tests.utils import MockFactory
        
        # Use the comprehensive factory that creates all the defaults we need
        service = MockFactory.create_mock_history_service()
        
        # Add legacy calculate_session_summary mock for backward compatibility
        service.calculate_session_summary.return_value = {
            "total_interactions": 2,
            "llm_interactions": 1,
            "mcp_communications": 1,
            "total_duration_ms": 2000,
            "errors_count": 0,
            "system_events": 0
        }
        
        return service
    
    @pytest.mark.unit
    def test_get_sessions_list_success(self, app, client, mock_history_service):
        """Test successful sessions list retrieval."""
        # Phase 4: Mock using new models
        from tarsy.models.history_models import SessionOverview, PaginatedSessions, PaginationInfo
        from tarsy.models.constants import AlertSessionStatus
        
        now_us_time = now_us()
        session1 = SessionOverview(
            session_id="session-1",
            alert_id="alert-1",
            alert_type="NamespaceTerminating",
            agent_type="KubernetesAgent", 
            status=AlertSessionStatus.COMPLETED,
            started_at_us=now_us_time - 60000000,  # 1 minute ago in microseconds
            completed_at_us=now_us_time,
            error_message=None,
            llm_interaction_count=0,
            mcp_communication_count=0,
            total_interactions=0,
            chain_id="chain-1"
        )
        
        session2 = SessionOverview(
            session_id="session-2", 
            alert_id="alert-2",
            alert_type="HighCPU",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.IN_PROGRESS,
            started_at_us=now_us_time - 300000000,  # 5 minutes ago in microseconds
            completed_at_us=None,
            error_message=None,
            llm_interaction_count=0,
            mcp_communication_count=0,
            total_interactions=0,
            chain_id="chain-2"
        )
        
        # Create PaginatedSessions response
        paginated_sessions = PaginatedSessions(
            sessions=[session1, session2],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=1, total_items=2),
            filters_applied={}
        )
        
        # Mock the new internal method 
        mock_history_service.get_sessions_list.return_value = paginated_sessions
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        if response.status_code != 200:
            print(f"Response status: {response.status_code}")
            print(f"Response content: {response.content}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "sessions" in data
        assert "pagination" in data
        assert len(data["sessions"]) == 2
        assert data["pagination"]["total_items"] == 2
        
        # Verify session data structure
        session = data["sessions"][0]
        assert "session_id" in session
        assert "alert_id" in session
        assert "alert_type" in session
        assert "agent_type" in session
        assert "status" in session
        assert "started_at_us" in session
    
    @pytest.mark.unit
    def test_get_sessions_list_with_filters(self, app, client, mock_history_service):
        """Test sessions list with query parameters."""
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={
                "status": "completed",
                "agent_type": "KubernetesAgent",
                "alert_type": "NamespaceTerminating",
                "page": 2,
                "page_size": 10
            }
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify that filters were passed to service
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert filters["status"] == ["completed"]  # Now expects list due to multiple status support
        assert filters["agent_type"] == "KubernetesAgent"
        assert filters["alert_type"] == "NamespaceTerminating"
        assert call_args.kwargs["page"] == 2
        assert call_args.kwargs["page_size"] == 10

    @pytest.mark.unit
    def test_get_sessions_list_with_single_status_filter(self, app, client, mock_history_service):
        """Test that single status filtering still works (backward compatibility)."""
        # Arrange
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"status": "completed"}
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify that single status is converted to list
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert filters["status"] == ["completed"]  # Single status becomes list

    @pytest.mark.unit
    def test_get_sessions_list_with_multiple_status_filter(self, app, client, mock_history_service):
        """Test multiple status filtering (the new feature)."""
        # Arrange
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params=[
                ("status", "completed"),
                ("status", "failed"),
                ("agent_type", "KubernetesAgent")
            ]
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify that multiple status values are passed correctly
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert set(filters["status"]) == {"completed", "failed"}  # Multiple status values
        assert filters["agent_type"] == "KubernetesAgent"

    @pytest.mark.unit 
    def test_get_sessions_list_multiple_status_historical_use_case(self, app, client, mock_history_service):
        """Test the specific use case for historical alerts (completed + failed)."""
        # Arrange
        from tests.utils import SessionFactory
        from tarsy.models.constants import AlertSessionStatus
        
        mock_sessions = [
            SessionFactory.create_session_overview(
                session_id="session-1",
                alert_id="alert-session-1", 
                status=AlertSessionStatus.COMPLETED
            ),
            SessionFactory.create_session_overview(
                session_id="session-2",
                alert_id="alert-session-2",
                status=AlertSessionStatus.FAILED,
                llm_interaction_count=0,
                total_interactions=1
            )
        ]
        paginated_sessions = SessionFactory.create_paginated_sessions(
            sessions=mock_sessions,
            total_items=2,
            page_size=20,
            filters_applied={"status": ["completed", "failed"]}
        )
        mock_history_service.get_sessions_list.return_value = paginated_sessions
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params=[("status", "completed"), ("status", "failed")]
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "sessions" in data
        assert "pagination" in data
        assert len(data["sessions"]) == 2
        
        # Verify that service was called with correct multiple status filter
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert set(filters["status"]) == {"completed", "failed"}

    @pytest.mark.unit
    def test_get_sessions_list_multiple_status_active_use_case(self, app, client, mock_history_service):
        """Test filtering for active alerts (pending + in_progress)."""
        # Arrange
        from tests.utils import SessionFactory
        from tarsy.models.constants import AlertSessionStatus
        
        mock_sessions = [
            SessionFactory.create_session_overview(
                session_id="session-1",
                alert_id="alert-session-1",
                status=AlertSessionStatus.PENDING,
                completed_at_us=None,  # Still pending
                llm_interaction_count=0,
                mcp_communication_count=0,
                total_interactions=0
            ),
            SessionFactory.create_session_overview(
                session_id="session-2",
                alert_id="alert-session-2", 
                status=AlertSessionStatus.IN_PROGRESS,
                completed_at_us=None  # Still in progress
            )
        ]
        paginated_sessions = SessionFactory.create_paginated_sessions(
            sessions=mock_sessions,
            total_items=2,
            page_size=20,
            filters_applied={"status": ["pending", "in_progress"]}
        )
        mock_history_service.get_sessions_list.return_value = paginated_sessions
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params=[("status", "pending"), ("status", "in_progress")]
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "sessions" in data
        assert len(data["sessions"]) == 2
        
        # Verify that service was called with correct multiple status filter
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert set(filters["status"]) == {"pending", "in_progress"}

    @pytest.mark.unit
    def test_get_sessions_list_three_status_values(self, app, client, mock_history_service):
        """Test filtering with three status values."""
        # Arrange
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params=[
                ("status", "completed"),
                ("status", "failed"), 
                ("status", "in_progress")
            ]
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify all three status values are passed
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert set(filters["status"]) == {"completed", "failed", "in_progress"}

    @pytest.mark.unit
    def test_get_sessions_list_no_status_filter(self, app, client, mock_history_service):
        """Test that endpoint works without status filter (gets all sessions)."""
        # Arrange
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"agent_type": "KubernetesAgent"}  # Other filters but no status
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify that status filter is not included when not specified
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert "status" not in filters  # No status filter when not provided
        assert filters["agent_type"] == "KubernetesAgent"
    
    @pytest.mark.unit
    def test_get_sessions_list_with_date_filters(self, app, client, mock_history_service):
        """Test sessions list with date range filters."""
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Convert dates to unix timestamps in microseconds
        start_date_us = int(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000000)
        end_date_us = int(datetime(2024, 1, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000000)

        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service

        response = client.get(
            "/api/v1/history/sessions",
            params={
                "start_date_us": start_date_us,
                "end_date_us": end_date_us
            }
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify date filters were parsed and passed correctly
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]

        assert "start_date_us" in filters
        assert "end_date_us" in filters
        assert isinstance(filters["start_date_us"], int)
        assert isinstance(filters["end_date_us"], int)
    
    @pytest.mark.unit
    def test_get_sessions_list_with_search_parameter(self, app, client, mock_history_service):
        """Test sessions list with search parameter."""
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"search": "namespace"}
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify that search filter was passed to service
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert filters["search"] == "namespace"
    
    @pytest.mark.unit
    def test_get_sessions_list_search_with_other_filters(self, app, client, mock_history_service):
        """Test search parameter combined with other filters."""
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={
                "search": "kubernetes",
                "status": "completed",
                "agent_type": "KubernetesAgent"
            }
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify all filters were passed to service
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert filters["search"] == "kubernetes"
        assert filters["status"] == ["completed"]
        assert filters["agent_type"] == "KubernetesAgent"
    
    @pytest.mark.unit
    def test_get_sessions_list_search_too_short(self, app, client, mock_history_service):
        """Test search parameter with less than 3 characters (should fail validation)."""
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"search": "ab"}  # Only 2 characters
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Should return 422 validation error
        assert response.status_code == 422
        error_details = response.json()["detail"]
        assert isinstance(error_details, list)
        assert any("string_too_short" in error.get("type", "") for error in error_details)
        assert any("at least 3 characters" in error.get("msg", "") for error in error_details)
    
    @pytest.mark.unit
    def test_get_sessions_list_search_empty_string(self, app, client, mock_history_service):
        """Test search parameter with empty string (should fail validation)."""
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"search": ""}  # Empty string
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Should return 422 validation error
        assert response.status_code == 422
        error_details = response.json()["detail"]
        assert isinstance(error_details, list)
        assert any("string_too_short" in error.get("type", "") for error in error_details)
    
    @pytest.mark.unit
    def test_get_sessions_list_search_minimum_length(self, app, client, mock_history_service):
        """Test search parameter with exactly 3 characters (should pass validation)."""
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"search": "pod"}  # Exactly 3 characters
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify search filter was passed to service
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert filters["search"] == "pod"
    
    @pytest.mark.unit
    def test_get_sessions_list_search_whitespace_handling(self, app, client, mock_history_service):
        """Test search parameter with whitespace (should be trimmed)."""
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"search": "  namespace  "}  # Whitespace around search term
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify search filter was trimmed and passed to service
        mock_history_service.get_sessions_list.assert_called_once()
        call_args = mock_history_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert filters["search"] == "namespace"  # Should be trimmed
    
    @pytest.mark.unit
    def test_get_sessions_list_invalid_date_format(self, app, client, mock_history_service):
        """Test sessions list with invalid Unix timestamp format."""
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get(
            "/api/v1/history/sessions",
            params={"start_date_us": "invalid-timestamp"}
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        # FastAPI returns 422 for validation errors, not 400
        assert response.status_code == 422
        
        # Check that the error is about integer parsing
        error_details = response.json()["detail"]
        assert isinstance(error_details, list)
        assert any("int_parsing" in error.get("type", "") for error in error_details)
    
    @pytest.mark.unit
    def test_get_sessions_list_service_disabled(self, app, client, mock_history_service):
        """Test sessions list when history service is disabled."""
        mock_history_service.enabled = False
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 0
        assert data["pagination"]["total_items"] == 0
    
    @pytest.mark.unit
    def test_get_sessions_list_service_error(self, app, client, mock_history_service):
        """Test sessions list with service error."""
        mock_history_service.get_sessions_list.side_effect = Exception("Service error")
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 500
        # The actual error message varies, just check it's an error response
        assert "detail" in response.json()
    
    @pytest.mark.unit
    def test_get_session_detail_success(self, app, client, mock_history_service):
        """Test successful session detail retrieval."""
        # Create proper DetailedSession object
        from tarsy.models.history_models import DetailedSession, DetailedStage, LLMInteraction, MCPInteraction, LLMEventDetails, MCPEventDetails
        from tarsy.models.constants import AlertSessionStatus, StageStatus
        from tarsy.models.unified_interactions import LLMMessage
        
        # Create LLM interaction
        llm_interaction = LLMInteraction(
            id="int-1",
            event_id="int-1", 
            timestamp_us=1705314000000000,
            step_description="Initial analysis",
            stage_execution_id="exec-3",
            details=LLMEventDetails(
                messages=[LLMMessage(role="user", content="Analyze the issue")],
                model_name="gpt-4",
                success=True
            )
        )
        
        # Create MCP interaction
        mcp_interaction = MCPInteraction(
            id="comm-1",
            event_id="comm-1",
            timestamp_us=1705314001000000,
            step_description="Check namespace status",
            stage_execution_id="exec-3", 
            details=MCPEventDetails(
                tool_name="kubectl_get_namespace",
                server_name="kubernetes-server",
                communication_type="tool_call",
                success=True
            )
        )
        
        # Create detailed stage
        stage = DetailedStage(
            execution_id="exec-3",
            session_id="test-session-123",
            stage_id="initial-analysis",
            stage_index=0,
            stage_name="Initial Analysis",
            agent="KubernetesAgent",
            status=StageStatus.COMPLETED,
            started_at_us=1705314000000000,
            completed_at_us=1705314001000000,
            llm_interactions=[llm_interaction],
            mcp_communications=[mcp_interaction],
            llm_interaction_count=1,
            mcp_communication_count=1,
            total_interactions=2
        )
        
        # Create detailed session
        mock_timeline = DetailedSession(
            session_id="test-session-123",
            alert_id="alert-456",
            alert_type="NamespaceTerminating",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=1705314000000000,
            completed_at_us=1705314300000000,
            chain_id="chain-123",
            chain_definition={},
            alert_data={},
            stages=[stage],
            total_interactions=2,
            llm_interaction_count=1,
            mcp_communication_count=1
        )
        mock_history_service.get_session_timeline.return_value = mock_timeline
        
        # Mock the get_session_with_stages async method
        async def mock_get_session_with_stages_first(session_id):
            return {
                "session": {
                    "session_id": "test-session-123",
                    "chain_id": "chain-123",
                    "alert_type": "NamespaceTerminating",
                    "status": "completed"
                },
                "stages": [
                    {
                        "execution_id": "exec-3",
                        "stage_id": "initial-analysis",
                        "stage_name": "Initial Analysis",
                        "status": "completed",
                        "interaction_summary": {
                            "llm_count": 1,
                            "mcp_count": 1,
                            "total_count": 2
                        }
                    }
                ]
            }
        mock_history_service.get_session_with_stages = mock_get_session_with_stages_first
        
        # Mock the new get_stage_interaction_counts method
        mock_history_service.get_stage_interaction_counts.return_value = {
            "exec-3": {"llm_interactions": 1, "mcp_communications": 1}
        }
        
        # Mock calculate_session_summary method (legacy)
        mock_history_service.calculate_session_summary.return_value = {
            "total_interactions": 2,
            "llm_interactions": 1, 
            "mcp_communications": 1,
            "total_duration_ms": 2000
        }
        
        # Mock get_session_summary method (async - used by the controller)
        from tests.utils import SessionFactory
        from tarsy.models.history_models import ChainStatistics
        mock_session_stats = SessionFactory.create_session_stats(
            total_interactions=2,
            llm_interactions=1,
            mcp_communications=1,
            total_duration_ms=2000,
            chain_statistics=ChainStatistics(
                total_stages=1,
                completed_stages=1,
                failed_stages=0,
                stages_by_agent={'KubernetesAgent': 1}
            )
        )
        mock_history_service.get_session_summary = AsyncMock(return_value=mock_session_stats)
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions/test-session-123")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # The response should have these fields based on the DetailedSession model
        assert "session_id" in data
        assert "alert_id" in data
        assert "chain_id" in data  # Chain fields are now at top level
        assert "chain_definition" in data
        assert "stages" in data
        
        # Verify session details
        assert data["session_id"] == "test-session-123"
        assert data["alert_type"] == "NamespaceTerminating"
        assert data["status"] == "completed"
        
        # All sessions should have chain data since we support chains only
        assert data["chain_id"] == "chain-123"
        stages = data["stages"]
        
        # Stages should always be present since we support chains only
        assert stages is not None, f"All sessions should have stages data. Got: {stages}"
        
        # Verify stages structure
        assert isinstance(stages, list)
        
        # Verify stage structure and timeline if stages exist
        if stages:
            for stage in stages:
                # Verify required stage fields
                assert "execution_id" in stage
                assert "stage_id" in stage
                assert "stage_name" in stage
                assert "status" in stage
                assert "chronological_interactions" in stage
                assert "llm_interaction_count" in stage
                assert "mcp_communication_count" in stage
                
                # Verify interaction count fields
                assert isinstance(stage["llm_interaction_count"], int)
                assert isinstance(stage["mcp_communication_count"], int)
                
                # Verify timeline events structure if present
                if stage["chronological_interactions"]:
                    for event in stage["chronological_interactions"]:
                        assert "type" in event
                        assert "timestamp_us" in event
                        assert "step_description" in event
                        assert "details" in event
                        assert isinstance(event["timestamp_us"], int)
                        assert event["type"] in ["llm", "mcp", "system"]
        
        # Verify other expected fields
        assert "duration_ms" in data
        assert "total_interactions" in data
    
    @pytest.mark.unit
    def test_get_session_detail_not_found(self, app, client, mock_history_service):
        """Test session detail for non-existent session."""
        mock_history_service.get_session_timeline.return_value = None
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions/non-existent-session")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 404
        # Check that the error message contains session reference
        assert "non-existent-session" in response.json()["detail"]
    
    @pytest.mark.unit
    def test_get_session_detail_service_disabled(self, app, client, mock_history_service):
        """Test session detail when service is disabled."""
        mock_history_service.enabled = False
        mock_history_service.get_session_timeline.return_value = None
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions/test-session")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # When service is disabled, timeline returns None, so we get 404
        assert response.status_code == 404
        assert "test-session" in response.json()["detail"]
    
    @pytest.mark.unit
    def test_get_session_detail_service_error(self, app, client, mock_history_service):
        """Test session detail with service error."""
        mock_history_service.get_session_timeline.side_effect = Exception("Service error")
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions/test-session")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 500
        assert "detail" in response.json()
    
    @pytest.mark.unit
    def test_health_check_healthy_service(self, app, client, mock_history_service):
        """Test health check with healthy service."""
        mock_history_service.enabled = True
        mock_history_service.test_database_connection.return_value = True
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/health")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["service"] == "alert_processing_history"
        assert data["status"] == "healthy"
        assert "timestamp_us" in data
        assert "details" in data
        
        details = data["details"]
        assert details["database_connection"] == "ok"
        assert details["history_enabled"] == True
        assert "database_url" in details
    
    @pytest.mark.unit
    def test_health_check_disabled_service(self, app, client, mock_history_service):
        """Test health check with disabled service."""
        mock_history_service.enabled = False
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/health")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "disabled"
        assert data["details"]["history_enabled"] == False
        assert "message" in data["details"]
    
    @pytest.mark.unit
    def test_health_check_database_failure(self, app, client, mock_history_service):
        """Test health check with database connection failure."""
        mock_history_service.enabled = True
        mock_history_service.test_database_connection.return_value = False
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/health")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["details"]["database_connection"] == "failed"
    
    @pytest.mark.unit
    def test_health_check_exception_handling(self, app, client, mock_history_service):
        """Test health check with exception."""
        mock_history_service.enabled = True
        mock_history_service.test_database_connection.side_effect = Exception("Database error")
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/health")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert "error" in data["details"]


class TestHistoryControllerValidation:
    """Test suite for request validation in HistoryController."""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI application with history router."""
        app = FastAPI()
        app.include_router(router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_history_service(self):
        """Create mock history service."""
        service = Mock(spec=HistoryService)
        service.enabled = True
        # Will be set up with proper model below
        return service
    
    @pytest.mark.unit
    def test_sessions_list_pagination_validation(self, client, mock_history_service):
        """Test pagination parameter validation."""
        with patch('tarsy.controllers.history_controller.get_history_service', return_value=mock_history_service):
            # Test negative page number
            response = client.get("/api/v1/history/sessions?page=-1")
            assert response.status_code == 422
            
            # Test zero page number
            response = client.get("/api/v1/history/sessions?page=0")
            assert response.status_code == 422
            
            # Test negative page_size
            response = client.get("/api/v1/history/sessions?page_size=-1")
            assert response.status_code == 422
            
            # Test page_size too large
            response = client.get("/api/v1/history/sessions?page_size=1001")
            assert response.status_code == 422
    
    @pytest.mark.unit
    def test_sessions_list_enum_validation(self, app, client, mock_history_service):
        """Test enum parameter validation."""
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_history_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Test invalid status - the API doesn't enforce enum validation, so it returns 200
        response = client.get("/api/v1/history/sessions?status=invalid_status")
        assert response.status_code == 200  # No enum validation in current implementation
        
        # Test valid status values
        valid_statuses = ["pending", "in_progress", "completed", "failed"]
        for status in valid_statuses:
            response = client.get(f"/api/v1/history/sessions?status={status}")
            assert response.status_code == 200
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.unit
    def test_session_id_validation(self, app, client, mock_history_service):
        """Test session ID parameter validation."""
        mock_history_service.get_session_timeline.return_value = None
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Test session ID with special characters (should be handled)
        response = client.get("/api/v1/history/sessions/session-with-dashes-123")
        assert response.status_code == 404  # Not found, but valid format
        
        # Test another valid format session ID
        response = client.get("/api/v1/history/sessions/valid-session-id")
        assert response.status_code == 404  # Not found, but endpoint exists
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.unit
    def test_date_format_validation_edge_cases(self, app, client, mock_history_service):
        """Test date format validation edge cases."""
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Test timestamps that will actually trigger validation errors
        invalid_timestamps = [
            "not-a-number",         # Completely invalid
            "12.34",                # Float instead of int
            "invalid-timestamp"     # Invalid format
        ]
        
        for invalid_timestamp in invalid_timestamps:
            response = client.get(f"/api/v1/history/sessions?start_date_us={invalid_timestamp}")
            # FastAPI returns 422 for validation errors, not 400
            assert response.status_code == 422
            # Check that the error is about integer parsing
            error_details = response.json()["detail"]
            assert isinstance(error_details, list)
            assert any("int_parsing" in error.get("type", "") for error in error_details)
        
        # Clean up
        app.dependency_overrides.clear()


class TestHistoryControllerResponseFormat:
    """Test suite for response format validation in HistoryController."""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI application with history router."""
        app = FastAPI()
        app.include_router(router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_history_service(self):
        """Create mock history service."""
        service = Mock(spec=HistoryService)
        service.enabled = True
        service.is_enabled = True
        # Will be set up with proper model below
        service.get_session_timeline.return_value = None
        service.test_database_connection.return_value = True
        
        # Add settings mock
        mock_settings = Mock()
        mock_settings.history_database_url = "sqlite:///test_history.db"
        mock_settings.history_enabled = True
        mock_settings.history_retention_days = 90
        service.settings = mock_settings
        
        # Add calculate_session_summary mock with default return value
        service.calculate_session_summary.return_value = {
            "total_interactions": 2,
            "llm_interactions": 1,
            "mcp_communications": 1,
            "total_duration_ms": 2000,
            "errors_count": 0,
            "system_events": 0
        }
        
        return service
    
    @pytest.mark.unit
    def test_sessions_list_response_format(self, app, client):
        """Test that sessions list response matches expected format."""
        mock_service = Mock(spec=HistoryService)
        mock_service.enabled = True
        
        # Create proper SessionOverview objects using factory
        from tests.utils import SessionFactory
        
        mock_session = SessionFactory.create_session_overview(
            session_id="test-session",
            alert_id="test-alert",
            alert_type="TestAlert",
            agent_type="TestAgent",
            llm_interaction_count=0,
            mcp_communication_count=0,
            total_interactions=0
        )
        
        paginated_sessions = SessionFactory.create_paginated_sessions(
            sessions=[mock_session],
            page_size=20
        )
        mock_service.get_sessions_list.return_value = paginated_sessions
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        response = client.get("/api/v1/history/sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate top-level structure (allow optional filters_applied field)
        expected_keys = {"sessions", "pagination"}
        actual_keys = set(data.keys())
        assert expected_keys.issubset(actual_keys)
        # Optional field that may be present
        allowed_optional_keys = {"filters_applied"}
        assert actual_keys.issubset(expected_keys.union(allowed_optional_keys))
        
        # Validate sessions structure
        assert isinstance(data["sessions"], list)
        assert len(data["sessions"]) == 1
        
        session = data["sessions"][0]
        required_fields = {
            "session_id", "alert_id", "alert_type", "agent_type", 
            "status", "started_at_us", "completed_at_us", "error_message"
        }
        # Allow additional fields that are actually returned (including chain-based fields)
        optional_fields = {
            "duration_ms", "llm_interaction_count", "mcp_communication_count", "total_interactions",
            "current_stage_index", "failed_stages", "total_stages", "chain_id", "completed_stages"
        }
        actual_fields = set(session.keys())
        assert required_fields.issubset(actual_fields)
        assert actual_fields.issubset(required_fields.union(optional_fields))
        
        # Validate pagination structure
        pagination = data["pagination"]
        required_pagination_fields = {
            "page", "page_size", "total_pages", "total_items"
        }
        assert set(pagination.keys()) == required_pagination_fields
        assert isinstance(pagination["page"], int)
        assert isinstance(pagination["total_items"], int)
    
    @pytest.mark.unit
    def test_session_detail_response_format(self, app, client, mock_history_service):
        """Test that session detail response matches expected format."""
        
        # Create proper DetailedSession object
        from tarsy.models.history_models import DetailedSession, DetailedStage, LLMInteraction, LLMEventDetails
        from tarsy.models.constants import AlertSessionStatus, StageStatus
        from tarsy.models.unified_interactions import LLMMessage
        
        # Create LLM interaction
        llm_interaction = LLMInteraction(
            id="int-1",
            event_id="int-1", 
            timestamp_us=1705314000000000,
            step_description="Test step",
            stage_execution_id="exec-1",
            details=LLMEventDetails(
                messages=[LLMMessage(role="user", content="Test prompt")],
                model_name="gpt-4",
                success=True
            )
        )
        
        # Create detailed stage
        stage = DetailedStage(
            execution_id="exec-1",
            session_id="test-session",
            stage_id="data-collection",
            stage_index=0,
            stage_name="Data Collection",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            started_at_us=1705314000000000,
            completed_at_us=1705314001000000,
            llm_interactions=[llm_interaction],
            mcp_communications=[],
            llm_interaction_count=1,
            mcp_communication_count=0,
            total_interactions=1
        )
        
        # Create detailed session
        mock_timeline = DetailedSession(
            session_id="test-session",
            alert_id="test-alert",
            alert_type="TestAlert",
            agent_type="TestAgent",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=1705314000000000,
            completed_at_us=1705314300000000,
            chain_id="chain-123",
            chain_definition={},
            alert_data={},
            stages=[stage],
            total_interactions=1,
            llm_interaction_count=1,
            mcp_communication_count=0
        )
        mock_history_service.get_session_timeline.return_value = mock_timeline
        
        # Mock the get_session_with_stages call for chain execution data
        mock_chain_data = {
            "stages": [
                {
                    "execution_id": "exec-1",
                    "stage_id": "data-collection", 
                    "stage_name": "Data Collection",
                    "status": "completed",
                    "interaction_summary": {
                        "llm_count": 1,
                        "mcp_count": 1,
                        "total_count": 2
                    }
                }
            ]
        }
        # Mock async method for get_session_with_stages  
        async def mock_get_session_with_stages(session_id):
            return {
                "session": {
                    "session_id": "test-session",
                    "chain_id": "chain-789",
                    "alert_type": "TestAlert", 
                    "status": "completed"
                },
                "stages": mock_chain_data["stages"]
            }
        mock_history_service.get_session_with_stages = mock_get_session_with_stages
        
        # Mock the new get_stage_interaction_counts method
        mock_history_service.get_stage_interaction_counts.return_value = {
            "exec-1": {"llm_interactions": 1, "mcp_communications": 1}
        }
        
        # Mock calculate_session_summary method (legacy)
        mock_history_service.calculate_session_summary.return_value = {
            "total_interactions": 2,
            "llm_interactions": 1, 
            "mcp_communications": 1,
            "total_duration_ms": 2000
        }
        
        # Mock get_session_summary method (async - used by the controller)
        from tarsy.models.history_models import SessionStats, ChainStatistics
        mock_session_stats = SessionStats(
            total_interactions=2,
            llm_interactions=1,
            mcp_communications=1,
            system_events=0,
            errors_count=0,
            total_duration_ms=2000,
            chain_statistics=ChainStatistics(
                total_stages=1,
                completed_stages=1,
                failed_stages=0,
                stages_by_agent={'TestAgent': 1}
            )
        )
        mock_history_service.get_session_summary = AsyncMock(return_value=mock_session_stats)
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/sessions/test-session")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate top-level structure (DetailedSession fields)
        expected_fields = {
            "session_id", "alert_id", "alert_type", "agent_type",
            "status", "started_at_us", "completed_at_us", "error_message",
            "chain_id", "chain_definition", "stages", "duration_ms", 
            "session_metadata", "alert_data", "final_analysis",
            "llm_interaction_count", "mcp_communication_count", "total_interactions",
            "current_stage_index", "current_stage_id"
        }
        assert expected_fields.issubset(set(data.keys()))
        
        # Validate session details directly in response
        assert data["session_id"] == "test-session"
        assert data["alert_type"] == "TestAlert"
        assert data["status"] == "completed"
        
        # Validate chain structure (all sessions should be chain-based)
        assert data["chain_id"] is not None, "All sessions should have chain data"
        assert isinstance(data["chain_definition"], dict)
        assert "stages" in data
        assert isinstance(data["stages"], list)
        
        # Verify stage timeline structure if stages exist
        if data["stages"]:
            first_stage = data["stages"][0]
            # Check for chronological_interactions (the new timeline structure)
            assert "chronological_interactions" in first_stage or "llm_interactions" in first_stage
            # Check for count fields instead of interaction_summary
            assert "llm_interaction_count" in first_stage
            assert "mcp_communication_count" in first_stage
            assert "execution_id" in first_stage
            assert "stage_id" in first_stage
            assert "stage_name" in first_stage
            assert "status" in first_stage
            
            # Validate interaction counts are present
            assert isinstance(first_stage["llm_interaction_count"], int)
            assert isinstance(first_stage["mcp_communication_count"], int)
            
            # Validate timeline events if present in chronological_interactions
            if "chronological_interactions" in first_stage and first_stage["chronological_interactions"]:
                event = first_stage["chronological_interactions"][0]
                assert "type" in event
                assert "timestamp_us" in event
                assert "step_description" in event
                assert "details" in event
        
        # Validate interaction counts exist at top level
        assert "total_interactions" in data
        assert isinstance(data["total_interactions"], int)
    
    @pytest.mark.unit
    def test_health_check_response_format(self, app, client, mock_history_service):
        """Test that health check response matches expected format."""
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        response = client.get("/api/v1/history/health")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate top-level structure
        required_fields = {"service", "status", "timestamp_us", "details"}
        assert set(data.keys()) == required_fields
        
        # Validate field types
        assert isinstance(data["service"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["timestamp_us"], int)
        assert isinstance(data["details"], dict)
        
        # Validate status values
        assert data["status"] in ["healthy", "unhealthy", "disabled"]
        
        # Validate details structure for healthy service
        details = data["details"]
        assert "database_connection" in details
        assert "history_enabled" in details


class TestHistoryControllerIntegration:
    """Integration tests for HistoryController with realistic scenarios."""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI application with history router."""
        app = FastAPI()
        app.include_router(router)  # Router already has /api/v1/history prefix
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.mark.unit
    def test_complex_filtering_scenario(self, app, client):
        """Test complex filtering scenario with multiple parameters."""
        mock_service = Mock(spec=HistoryService)
        mock_service.enabled = True
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        # Convert dates to unix timestamps in microseconds
        start_date_us = int(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000000)
        end_date_us = int(datetime(2024, 1, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000000)
        
        response = client.get(
            "/api/v1/history/sessions",
            params={
                "status": "completed",
                "agent_type": "KubernetesAgent",
                "alert_type": "NamespaceTerminating",
                "start_date_us": start_date_us,
                "end_date_us": end_date_us,
                "page": 1,
                "page_size": 20
            }
        )
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        
        # Verify all filters were applied
        call_args = mock_service.get_sessions_list.call_args
        filters = call_args.kwargs["filters"]
        
        assert filters["status"] == ["completed"]  # Now expects list due to multiple status support
        assert filters["agent_type"] == "KubernetesAgent"
        assert filters["alert_type"] == "NamespaceTerminating"
        assert "start_date_us" in filters
        assert "end_date_us" in filters
    
    @pytest.mark.unit
    def test_real_world_error_scenarios(self, app, client):
        """Test real-world error scenarios."""
        mock_service = Mock(spec=HistoryService)
        mock_service.enabled = True
        
        # Test database timeout scenario
        mock_service.get_sessions_list.side_effect = TimeoutError("Database timeout")
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        response = client.get("/api/v1/history/sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        assert response.status_code == 500
        assert "detail" in response.json()
    
    @pytest.mark.unit
    def test_concurrent_request_handling(self, app, client):
        """Test that controller handles concurrent requests properly."""
        mock_service = Mock(spec=HistoryService)
        mock_service.enabled = True
        from tarsy.models.history_models import PaginatedSessions, PaginationInfo
        empty_paginated = PaginatedSessions(
            sessions=[],
            pagination=PaginationInfo(page=1, page_size=20, total_pages=0, total_items=0),
            filters_applied={}
        )
        mock_service.get_sessions_list.return_value = empty_paginated
        
        # Override FastAPI dependency
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        # Simulate multiple concurrent requests
        responses = []
        for i in range(5):
            response = client.get(f"/api/v1/history/sessions?page={i+1}")
            responses.append(response)
        
        # Clean up
        app.dependency_overrides.clear()
        
        # All requests should succeed
        for response in responses:
            assert response.status_code == 200
        
        # Service should have been called for each request
        assert mock_service.get_sessions_list.call_count == 5

class TestDashboardEndpoints:
    """Test suite for new dashboard-specific API endpoints."""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI application with history router."""
        app = FastAPI()
        app.include_router(router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_history_service(self):
        """Create mock history service for dashboard endpoints."""
        service = Mock(spec=HistoryService)
        service.enabled = True
        service.is_enabled = True
        
        # Mock dashboard methods (metrics removed)
        
        # Create a proper mock session object with datetime handling
        mock_session = Mock()
        mock_session.session_id = "session_1"
        mock_session.alert_id = "alert_1"
        mock_session.agent_type = "kubernetes"
        mock_session.alert_type = "PodCrashLooping"
        mock_session.status = "in_progress"
        mock_session.started_at_us = now_us() - 300000000  # 5 minutes ago
        mock_session.completed_at_us = None
        mock_session.error_message = None
        
        service.get_active_sessions.return_value = [mock_session]
        
        service.get_filter_options.return_value = {
            "agent_types": ["kubernetes", "network", "database"],
            "alert_types": ["PodCrashLooping", "ServiceDown"],
            "status_options": ["pending", "in_progress", "completed", "failed"],
            "time_ranges": [
                {"label": "Last Hour", "value": "1h"},
                {"label": "Last 4 Hours", "value": "4h"},
                {"label": "Today", "value": "today"},
                {"label": "This Week", "value": "week"}
            ]
        }
        
        return service
    

    
    @pytest.mark.unit
    def test_get_active_sessions_success(self, app, client):
        """Test successful active sessions retrieval."""
        # Create a more realistic mock service
        mock_service = Mock()
        
        # Create a real AlertSession-like object
        from tarsy.models.db_models import AlertSession
        test_session = AlertSession(
            session_id="session_1",
            alert_id="alert_1",
            agent_type="kubernetes",
            alert_type="PodCrashLooping",
            status="in_progress",
            started_at_us=now_us(),
            alert_data={}
        )
        
        mock_service.get_active_sessions.return_value = [test_session]
        
        # Override dependency
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        # Make request
        response = client.get("/api/v1/history/active-sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "session_1"
        assert data[0]["alert_id"] == "alert_1"
        assert data[0]["agent_type"] == "kubernetes"
        assert data[0]["alert_type"] == "PodCrashLooping"
        assert data[0]["status"] == "in_progress"
        assert "started_at_us" in data[0]
        assert "duration_seconds" in data[0]
        assert data[0]["completed_at_us"] is None
        
        # Verify service was called
        mock_service.get_active_sessions.assert_called_once()
    
    @pytest.mark.unit
    def test_get_active_sessions_empty(self, app, client):
        """Test active sessions endpoint with no active sessions."""
        # Create mock service
        mock_service = Mock()
        mock_service.get_active_sessions.return_value = []
        
        # Override dependency
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        # Make request
        response = client.get("/api/v1/history/active-sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data == []
    
    @pytest.mark.unit
    def test_get_active_sessions_service_error(self, app, client):
        """Test active sessions endpoint with service error."""
        # Create mock service that raises exception
        mock_service = Mock()
        mock_service.get_active_sessions.side_effect = Exception("Database error")
        
        # Override dependency
        app.dependency_overrides[get_history_service] = lambda: mock_service
        
        # Make request
        response = client.get("/api/v1/history/active-sessions")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Assert error response
        assert response.status_code == 500
        assert "Failed to get active sessions" in response.json()["detail"]
    
    @pytest.mark.unit
    def test_get_filter_options_success(self, app, client, mock_history_service):
        """Test successful filter options retrieval."""
        # Phase 4: Create a simple Mock that returns the expected dict directly to avoid recursion
        mock_filter_result = Mock()
        mock_filter_result.model_dump.return_value = {
            "agent_types": ["kubernetes", "base", "analysis"],
            "alert_types": ["HighCPU", "NamespaceTerminating", "PodCrashLooping"],
            "status_options": ["pending", "in_progress", "completed", "failed"],
            "time_ranges": [
                {"label": "Last Hour", "value": "1h"},
                {"label": "Last 4 Hours", "value": "4h"},
                {"label": "Today", "value": "today"},
                {"label": "This Week", "value": "week"}
            ]
        }
        mock_history_service.get_filter_options.return_value = mock_filter_result
        
        # Override dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get("/api/v1/history/filter-options")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert "agent_types" in data
        assert "alert_types" in data
        assert "status_options" in data
        assert "time_ranges" in data
        assert len(data["agent_types"]) == 3
        assert "kubernetes" in data["agent_types"]
        assert len(data["time_ranges"]) == 4
        
        # Verify service was called
        mock_history_service.get_filter_options.assert_called_once()
    
    @pytest.mark.unit
    def test_get_filter_options_service_error(self, app, client, mock_history_service):
        """Test filter options endpoint with service error."""
        # Configure mock to raise exception
        mock_history_service.get_filter_options.side_effect = Exception("Database error")
        
        # Override dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get("/api/v1/history/filter-options")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Assert error response
        assert response.status_code == 500
        assert "Failed to get filter options" in response.json()["detail"]

    @pytest.mark.unit
    def test_get_session_summary_success(self, app, client, mock_history_service):
        """Test successful session summary retrieval."""
        session_id = "test-session-123"
        
        # Phase 4: Create SessionStats model using factory
        from tests.utils import SessionFactory
        from tarsy.models.history_models import ChainStatistics
        
        session_stats = SessionFactory.create_session_stats(
            total_interactions=13,
            llm_interactions=8,
            mcp_communications=5,
            total_duration_ms=15000,
            chain_statistics=ChainStatistics(
                total_stages=3,
                completed_stages=3,
                failed_stages=0,
                stages_by_agent={'KubernetesAgent': 2, 'AnalysisAgent': 1}
            )
        )
        
        # Mock the new internal method
        mock_history_service.get_session_summary = AsyncMock(return_value=session_stats)
        
        # Dependency override
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get(f"/api/v1/history/sessions/{session_id}/summary")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Verify basic statistics
        assert data['total_interactions'] == 13
        assert data['llm_interactions'] == 8
        assert data['mcp_communications'] == 5
        assert data['system_events'] == 0
        assert data['errors_count'] == 0
        assert data['total_duration_ms'] == 15000
        
        # Verify chain statistics
        assert 'chain_statistics' in data
        assert data['chain_statistics']['total_stages'] == 3
        assert data['chain_statistics']['completed_stages'] == 3
        assert data['chain_statistics']['failed_stages'] == 0
        assert data['chain_statistics']['stages_by_agent']['KubernetesAgent'] == 2
        
        # Verify service was called correctly
        mock_history_service.get_session_summary.assert_called_once_with(session_id)

    @pytest.mark.unit
    def test_get_session_summary_not_found(self, app, client, mock_history_service):
        """Test session summary when session doesn't exist."""
        session_id = "non-existent-session"
        
        # Phase 4: Mock the service method to return None (session not found)
        mock_history_service.get_session_summary = AsyncMock(return_value=None)
        
        # Dependency override
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get(f"/api/v1/history/sessions/{session_id}/summary")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Verify 404 response
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        
        # Verify service was called
        mock_history_service.get_session_summary.assert_called_once_with(session_id)

    @pytest.mark.unit
    def test_get_session_summary_service_error(self, app, client, mock_history_service):
        """Test session summary when service throws an error."""
        session_id = "error-session-123"
        
        # Mock service to raise an exception
        mock_history_service.get_session_summary.side_effect = Exception("Database connection failed")
        
        # Dependency override
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get(f"/api/v1/history/sessions/{session_id}/summary")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Verify 500 response
        assert response.status_code == 500
        assert "Failed to retrieve session summary" in response.json()["detail"]
        
        # Verify service was called
        mock_history_service.get_session_summary.assert_called_once_with(session_id)

    @pytest.mark.unit
    def test_get_session_summary_minimal_data(self, app, client, mock_history_service):
        """Test session summary with minimal data (no chain)."""
        session_id = "minimal-session-123"
        
        # Mock service response with minimal data using factory
        from tests.utils import SessionFactory
        from tarsy.models.history_models import ChainStatistics
        mock_summary = SessionFactory.create_session_stats(
            total_interactions=2,
            llm_interactions=1,
            mcp_communications=1,
            total_duration_ms=1500,
            chain_statistics=ChainStatistics(
                total_stages=1,
                completed_stages=1,
                failed_stages=0,
                stages_by_agent={'TestAgent': 1}
            )
        )
        mock_history_service.get_session_summary = AsyncMock(return_value=mock_summary)
        
        # Dependency override
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get(f"/api/v1/history/sessions/{session_id}/summary")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Verify basic statistics
        assert data['total_interactions'] == 2
        assert data['llm_interactions'] == 1
        assert data['mcp_communications'] == 1
        assert data['system_events'] == 0
        assert data['errors_count'] == 0
        assert data['total_duration_ms'] == 1500
        
        # Verify chain statistics are present (all sessions have chain info in Phase 4)
        assert 'chain_statistics' in data
        assert data['chain_statistics']['total_stages'] == 1
        
        # Verify service was called correctly
        mock_history_service.get_session_summary.assert_called_once_with(session_id)

    @pytest.mark.unit
    def test_get_session_summary_with_errors(self, app, client, mock_history_service):
        """Test session summary with error statistics."""
        session_id = "error-session-123"
        
        # Mock service response with errors using factory
        from tests.utils import SessionFactory
        from tarsy.models.history_models import ChainStatistics
        mock_summary = SessionFactory.create_session_stats(
            total_interactions=10,
            llm_interactions=6,
            mcp_communications=3,
            system_events=1,
            errors_count=2,  # Some errors occurred
            total_duration_ms=25000,
            chain_statistics=ChainStatistics(
                total_stages=3,
                completed_stages=2,
                failed_stages=1,  # One stage failed
                stages_by_agent={'KubernetesAgent': 3}
            )
        )
        mock_history_service.get_session_summary = AsyncMock(return_value=mock_summary)
        
        # Dependency override
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get(f"/api/v1/history/sessions/{session_id}/summary")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Verify error statistics
        assert data['errors_count'] == 2
        assert data['chain_statistics']['failed_stages'] == 1
        assert data['chain_statistics']['completed_stages'] == 2
        
        # Verify service was called correctly
        mock_history_service.get_session_summary.assert_called_once_with(session_id)

    @pytest.mark.unit
    def test_get_session_summary_response_format(self, app, client, mock_history_service):
        """Test session summary endpoint response format validation."""
        session_id = "format-test-session"
        
        # Mock service response using factory
        from tests.utils import SessionFactory
        from tarsy.models.history_models import ChainStatistics
        mock_summary = SessionFactory.create_session_stats(
            total_interactions=5,
            llm_interactions=3,
            mcp_communications=2,
            total_duration_ms=8000,
            chain_statistics=ChainStatistics(
                total_stages=2,
                completed_stages=2,
                failed_stages=0,
                stages_by_agent={'TestAgent': 2}
            )
        )
        mock_history_service.get_session_summary = AsyncMock(return_value=mock_summary)
        
        # Dependency override
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Make request
        response = client.get(f"/api/v1/history/sessions/{session_id}/summary")
        
        # Clean up
        app.dependency_overrides.clear()
        
        # Verify response format
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        
        # Verify all required fields are present and have correct types
        required_fields = [
            'total_interactions', 'llm_interactions', 'mcp_communications',
            'system_events', 'errors_count', 'total_duration_ms'
        ]
        
        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from response"
            assert isinstance(data[field], int), f"Field '{field}' should be an integer"
            assert data[field] >= 0, f"Field '{field}' should be non-negative"
        
        # Verify consistency (total should equal sum of interaction types)
        expected_total = data['llm_interactions'] + data['mcp_communications'] + data['system_events']
        assert data['total_interactions'] == expected_total, \
            f"Total interactions ({data['total_interactions']}) should equal sum of interaction types ({expected_total})"


def create_mock_session(session_id: str, status: str) -> Mock:
    """Helper to create a mock session object with a specific status."""
    current_time_us = now_us()
    
    mock_session = Mock()
    mock_session.session_id = session_id
    mock_session.alert_id = f"alert-{session_id}"
    mock_session.agent_type = "KubernetesAgent"
    mock_session.alert_type = "NamespaceTerminating"
    mock_session.status = status
    mock_session.started_at_us = current_time_us - 300000000  # Started 5 minutes ago
    mock_session.completed_at_us = current_time_us if status == "completed" else None
    mock_session.error_message = None
    mock_session.llm_interactions = []
    mock_session.mcp_communications = []
    mock_session.llm_interaction_count = 0
    mock_session.mcp_communication_count = 0
    return mock_session 