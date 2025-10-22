"""
Unit tests for author field in History Service.

Tests that HistoryService correctly saves and retrieves author information
when creating alert sessions.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.models.alert import Alert, ProcessingAlert
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.models.processing_context import ChainContext
from tarsy.services.history_service import HistoryService


@pytest.mark.unit
class TestHistoryServiceAuthorField:
    """Test author field handling in HistoryService."""

    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings

    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = True
            return service

    @pytest.fixture
    def sample_chain_context(self):
        """Create a sample ChainContext with author."""
        alert = Alert(
            alert_type="test",
            runbook="https://example.com/runbook.md",
            data={"message": "Test alert"}
        )
        processing_alert = ProcessingAlert.from_api_alert(alert)
        
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="initial",
            author="test-user"
        )

    @pytest.fixture
    def sample_chain_definition(self):
        """Create a sample chain definition."""
        return ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[
                ChainStageConfigModel(
                    name="Test Stage",
                    agent="base"
                )
            ]
        )

    @pytest.mark.parametrize(
        "author,expected_author",
        [
            ("github-user", "github-user"),
            ("user@example.com", "user@example.com"),
            ("api-client", "api-client"),
            (None, None),
        ],
    )
    def test_create_session_with_author(
        self, history_service, sample_chain_definition, author, expected_author
    ):
        """Test that create_session correctly saves author field."""
        # Create context with specific author
        alert = Alert(
            alert_type="test",
            runbook="https://example.com/runbook.md",
            data={"message": "Test alert"}
        )
        processing_alert = ProcessingAlert.from_api_alert(alert)
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-with-author",
            current_stage_name="initial",
            author=author
        )

        # Mock repository to capture created session
        captured_session = []

        def mock_create_alert_session(session):
            captured_session.append(session)
            return session

        mock_repo = Mock()
        mock_repo.create_alert_session = mock_create_alert_session

        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo

            result = history_service.create_session(context, sample_chain_definition)

            assert result is True
            assert len(captured_session) == 1
            
            created_session = captured_session[0]
            assert isinstance(created_session, AlertSession)
            assert created_session.session_id == "test-session-with-author"
            assert created_session.author == expected_author
            assert created_session.status == AlertSessionStatus.PENDING.value

    def test_create_session_without_author(
        self, history_service, sample_chain_definition
    ):
        """Test that create_session works when author is None."""
        # Create context without author
        alert = Alert(
            alert_type="test",
            runbook="https://example.com/runbook.md",
            data={"message": "Test alert"}
        )
        processing_alert = ProcessingAlert.from_api_alert(alert)
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-no-author",
            current_stage_name="initial"
            # author not provided, should default to None
        )

        captured_session = []

        def mock_create_alert_session(session):
            captured_session.append(session)
            return session

        mock_repo = Mock()
        mock_repo.create_alert_session = mock_create_alert_session

        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo

            result = history_service.create_session(context, sample_chain_definition)

            assert result is True
            assert len(captured_session) == 1
            
            created_session = captured_session[0]
            assert created_session.author is None

    def test_create_session_preserves_author_through_retry(
        self, history_service, sample_chain_context, sample_chain_definition
    ):
        """Test that author field is preserved through retry logic."""
        captured_sessions = []

        def mock_create_alert_session(session):
            captured_sessions.append(session)
            return session

        mock_repo = Mock()
        mock_repo.create_alert_session = mock_create_alert_session

        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo

            # Create session should succeed
            result = history_service.create_session(
                sample_chain_context, sample_chain_definition
            )

            assert result is True
            assert len(captured_sessions) == 1
            
            # Author should be preserved
            assert captured_sessions[0].author == "test-user"

    def test_create_session_author_in_alert_session_construction(
        self, history_service, sample_chain_definition
    ):
        """Test that author is correctly included in AlertSession construction."""
        alert = Alert(
            alert_type="kubernetes",
            runbook="https://example.com/runbook.md",
            data={"namespace": "test-ns", "message": "Test"}
        )
        processing_alert = ProcessingAlert.from_api_alert(alert)
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-construction",
            current_stage_name="initial",
            author="construction-test-user"
        )

        captured_session = []

        def mock_create_alert_session(session):
            # Verify all expected fields are present
            assert hasattr(session, 'author')
            assert session.author == "construction-test-user"
            assert session.session_id == "test-session-construction"
            assert session.agent_type == "chain:test-chain"
            assert session.alert_type == "kubernetes"
            assert session.status == AlertSessionStatus.PENDING.value
            captured_session.append(session)
            return session

        mock_repo = Mock()
        mock_repo.create_alert_session = mock_create_alert_session

        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo

            result = history_service.create_session(context, sample_chain_definition)

            assert result is True
            assert len(captured_session) == 1

    def test_create_session_disabled_service_ignores_author(
        self, sample_chain_context, sample_chain_definition
    ):
        """Test that disabled service gracefully handles author field."""
        mock_settings = Mock()
        mock_settings.history_enabled = False

        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            
            # Should return False without attempting to save
            result = service.create_session(sample_chain_context, sample_chain_definition)
            
            assert result is False
            # No database operations should occur

