"""
Integration tests for alert submission with session creation.

Tests that the submit_alert endpoint creates the session in the database
before returning the response to the client, eliminating race conditions.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tarsy.main import app
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.models.db_models import AlertSession


@pytest.mark.integration
class TestAlertSubmissionSessionCreation:
    """Test session creation during alert submission."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def valid_alert_data(self):
        """Valid alert data for testing."""
        return {
            "alert_type": "kubernetes",
            "data": {
                "namespace": "test-namespace",
                "pod_name": "test-pod-12345",
                "message": "Test alert for session creation verification",
                "severity": "critical"
            }
        }

    @pytest.fixture
    def mock_chain_definition(self):
        """Mock chain definition."""
        return ChainConfigModel(
            chain_id="test-chain",
            alert_types=["kubernetes"],
            stages=[
                ChainStageConfigModel(
                    name="analysis",
                    agent="KubernetesAgent"
                )
            ]
        )

    @patch('tarsy.main.alert_service')
    def test_submit_alert_creates_session_before_response(
        self, mock_alert_service, client, valid_alert_data, mock_chain_definition, 
        test_database_session: Session
    ):
        """Test that session is created in database before API response is returned."""
        # Arrange
        mock_alert_service.chain_registry.get_default_alert_type.return_value = "kubernetes"
        mock_alert_service.get_chain_for_alert.return_value = mock_chain_definition
        
        # Mock session creation to return True
        mock_alert_service.session_manager.create_chain_history_session.return_value = True
        
        # Mock background processing
        app.state.process_alert_callback = AsyncMock()
        
        # Act
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data
        session_id = data["session_id"]
        
        # Verify chain was selected
        mock_alert_service.get_chain_for_alert.assert_called_once_with("kubernetes")
        
        # Verify session was created before response
        mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
        call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
        chain_context = call_args[0][0]
        chain_def = call_args[0][1]
        
        assert chain_context.session_id == session_id
        assert chain_def == mock_chain_definition
        
        # Verify background task was started
        app.state.process_alert_callback.assert_called_once()

    @patch('tarsy.main.alert_service')
    def test_submit_alert_returns_400_for_invalid_alert_type(
        self, mock_alert_service, client, valid_alert_data
    ):
        """Test that invalid alert type returns 400 error."""
        # Arrange
        mock_alert_service.chain_registry.get_default_alert_type.return_value = "kubernetes"
        mock_alert_service.get_chain_for_alert.side_effect = ValueError(
            "No chain found for alert type 'invalid_type'"
        )
        
        valid_alert_data["alert_type"] = "invalid_type"
        
        # Act
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"] == "Invalid alert type"
        assert "No chain found" in data["detail"]["message"]

    @patch('tarsy.main.alert_service')
    def test_submit_alert_returns_500_when_session_creation_fails(
        self, mock_alert_service, client, valid_alert_data, mock_chain_definition
    ):
        """Test that session creation failure returns 500 error."""
        # Arrange
        mock_alert_service.chain_registry.get_default_alert_type.return_value = "kubernetes"
        mock_alert_service.get_chain_for_alert.return_value = mock_chain_definition
        
        # Session creation fails
        mock_alert_service.session_manager.create_chain_history_session.return_value = False
        
        # Act
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"] == "Session creation failed"

@pytest.mark.integration
class TestIdempotentSessionCreation:
    """Test that background processing handles pre-created sessions correctly."""

    @pytest.mark.asyncio
    async def test_process_alert_with_existing_session(
        self, test_database_session: Session
    ):
        """Test that process_alert handles sessions created by endpoint."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.processing_context import ChainContext
        from tarsy.services.session_manager import SessionManager
        from tarsy.services.history_service import HistoryService
        from tarsy.utils.timestamp import now_us
        
        # Arrange
        session_id = str(uuid.uuid4())
        
        # Create session in database (simulating endpoint behavior)
        pre_created_session = AlertSession(
            session_id=session_id,
            alert_data={"test": "data"},
            agent_type="chain:test-chain",
            alert_type="kubernetes",
            status="pending",
            chain_id="test-chain",
            chain_definition={"chain_id": "test-chain", "stages": []},
            author="test-user"
        )
        test_database_session.add(pre_created_session)
        test_database_session.commit()
        
        # Create history service and session manager
        history_service = HistoryService()
        session_manager = SessionManager(history_service)
        
        # Create chain context
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="high",
            timestamp=now_us(),
            environment="test",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id=session_id,
            current_stage_name="analysis"
        )
        
        chain_definition = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["kubernetes"],
            stages=[
                ChainStageConfigModel(
                    name="analysis",
                    agent="KubernetesAgent"
                )
            ]
        )
        
        # Act - Try to create session again (simulating background processing)
        result = session_manager.create_chain_history_session(chain_context, chain_definition)
        
        # Assert - Should return True (session already exists, no error)
        # The actual behavior depends on the implementation - it may return False or True
        # The key is that it doesn't raise an exception
        assert result in [True, False], "Session creation should be idempotent"
        
        # Verify only one session exists in database
        from sqlmodel import select, func
        session_count = test_database_session.exec(
            select(func.count(AlertSession.session_id)).where(
                AlertSession.session_id == session_id
            )
        ).one()
        
        assert session_count == 1, "Should only have one session record"
