"""
Unit tests for optional metadata fields in History Service.

Tests that HistoryService correctly saves and retrieves optional metadata
(author, runbook_url) when creating alert sessions.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.models.alert import Alert, ProcessingAlert
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.models.processing_context import ChainContext
from tarsy.services.history_service import HistoryService


@pytest.mark.unit
class TestHistoryServiceOptionalMetadata:
    """Test optional metadata fields (author, runbook_url) handling in HistoryService."""

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
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
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
        "author,runbook,expected_author,expected_runbook",
        [
            ("github-user", "https://example.com/runbook.md", "github-user", "https://example.com/runbook.md"),
            ("user@example.com", "https://github.com/company/runbooks/k8s.md", "user@example.com", "https://github.com/company/runbooks/k8s.md"),
            ("api-client", None, "api-client", None),
            (None, "https://internal-wiki/runbook", None, "https://internal-wiki/runbook"),
            (None, None, None, None),
        ],
    )
    def test_create_session_with_optional_metadata(
        self, history_service, sample_chain_definition, author, runbook, expected_author, expected_runbook
    ):
        """Test that create_session correctly saves optional metadata fields (author and runbook_url)."""
        # Create context with specific author and runbook
        alert = Alert(
            alert_type="test",
            runbook=runbook,
            data={"message": "Test alert"}
        )
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-with-metadata",
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
            assert created_session.session_id == "test-session-with-metadata"
            assert created_session.author == expected_author
            assert created_session.runbook_url == expected_runbook
            assert created_session.status == AlertSessionStatus.PENDING.value

    def test_create_session_without_optional_metadata(
        self, history_service, sample_chain_definition
    ):
        """Test that create_session works when optional metadata (author, runbook_url) are None."""
        # Create context without author or runbook
        alert = Alert(
            alert_type="test",
            data={"message": "Test alert"}
            # No runbook provided
        )
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-no-metadata",
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
            assert created_session.runbook_url is None

    def test_create_session_preserves_metadata_through_retry(
        self, history_service, sample_chain_definition
    ):
        """Test that optional metadata fields are preserved through retry logic."""
        # Create context with both author and runbook
        alert = Alert(
            alert_type="test",
            runbook="https://example.com/runbook-preserved.md",
            data={"message": "Test alert"}
        )
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-preserved",
            current_stage_name="initial",
            author="test-user"
        )
        
        captured_sessions = []

        def mock_create_alert_session(session):
            captured_sessions.append(session)
            return session

        mock_repo = Mock()
        mock_repo.create_alert_session = mock_create_alert_session

        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo

            # Create session should succeed
            result = history_service.create_session(context, sample_chain_definition)

            assert result is True
            assert len(captured_sessions) == 1
            
            # Both author and runbook_url should be preserved
            assert captured_sessions[0].author == "test-user"
            assert captured_sessions[0].runbook_url == "https://example.com/runbook-preserved.md"

    def test_create_session_metadata_in_alert_session_construction(
        self, history_service, sample_chain_definition
    ):
        """Test that optional metadata fields are correctly included in AlertSession construction."""
        alert = Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/k8s-runbooks/troubleshooting.md",
            data={"namespace": "test-ns", "message": "Test"}
        )
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-construction",
            current_stage_name="initial",
            author="construction-test-user"
        )

        captured_session = []

        def mock_create_alert_session(session):
            # Verify all expected fields including optional metadata are present
            assert hasattr(session, 'author')
            assert hasattr(session, 'runbook_url')
            assert session.author == "construction-test-user"
            assert session.runbook_url == "https://github.com/company/k8s-runbooks/troubleshooting.md"
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

