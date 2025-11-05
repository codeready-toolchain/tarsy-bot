"""
Unit tests for author field in ChainContext model.

Tests that ChainContext correctly accepts, stores, and propagates
author information through the processing pipeline.
"""

import pytest

from tarsy.models.alert import Alert, ProcessingAlert
from tarsy.models.processing_context import ChainContext


@pytest.mark.unit
class TestChainContextAuthorField:
    """Test author field handling in ChainContext."""

    @pytest.fixture
    def sample_alert(self):
        """Create a sample alert for testing."""
        return Alert(
            alert_type="test",
            runbook="https://example.com/runbook.md",
            data={"message": "Test alert"}
        )

    @pytest.fixture
    def processing_alert(self, sample_alert):
        """Create a ProcessingAlert from sample alert."""
        return ProcessingAlert.from_api_alert(sample_alert, default_alert_type="kubernetes")

    @pytest.mark.parametrize(
        "author,expected_author",
        [
            ("github-user", "github-user"),
            ("user@example.com", "user@example.com"),
            ("api-client", "api-client"),
            (None, None),
        ],
    )
    def test_from_processing_alert_with_author(
        self, processing_alert, author, expected_author
    ):
        """Test that from_processing_alert correctly sets author field."""
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="initial",
            author=author
        )

        assert context.author == expected_author
        assert context.session_id == "test-session-123"
        assert context.current_stage_name == "initial"
        assert context.processing_alert == processing_alert

    def test_from_processing_alert_without_author_parameter(
        self, processing_alert
    ):
        """Test that from_processing_alert works without author parameter."""
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="initial"
        )

        # Author should default to None when not provided
        assert context.author is None
        assert context.session_id == "test-session-123"

    def test_chain_context_direct_instantiation_with_author(
        self, processing_alert
    ):
        """Test ChainContext can be directly instantiated with author field."""
        context = ChainContext(
            processing_alert=processing_alert,
            session_id="test-session-456",
            current_stage_name="analysis",
            author="test-user"
        )

        assert context.author == "test-user"
        assert context.session_id == "test-session-456"
        assert context.current_stage_name == "analysis"

    def test_chain_context_author_field_is_optional(
        self, processing_alert
    ):
        """Test that author field is optional in ChainContext."""
        # Should not raise error when author is omitted
        context = ChainContext(
            processing_alert=processing_alert,
            session_id="test-session-789",
            current_stage_name="initial"
        )

        assert context.author is None

    def test_chain_context_author_can_be_none(
        self, processing_alert
    ):
        """Test that author can be explicitly set to None."""
        context = ChainContext(
            processing_alert=processing_alert,
            session_id="test-session-000",
            current_stage_name="initial",
            author=None
        )

        assert context.author is None

    def test_chain_context_author_field_persists(
        self, processing_alert
    ):
        """Test that author field persists through context operations."""
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-111",
            current_stage_name="initial",
            author="persistent-user"
        )

        # Add stage results and set chain context
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            stage_description="Test stage",
            timestamp_us=now_us(),
            result_summary="Test result"
        )
        
        context.add_stage_result("stage1", result)
        context.set_chain_context("test-chain", "stage2")

        # Author should still be present after context operations
        assert context.author == "persistent-user"

    def test_chain_context_author_with_special_characters(
        self, processing_alert
    ):
        """Test author field handles special characters."""
        special_authors = [
            "user@domain.com",
            "user-name",
            "user.name",
            "user_123",
            "user+tag@example.com",
        ]

        for author in special_authors:
            context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id=f"test-session-{hash(author)}",
                current_stage_name="initial",
                author=author
            )

            assert context.author == author

    def test_chain_context_author_with_long_value(
        self, processing_alert
    ):
        """Test author field handles long usernames."""
        long_author = "a" * 255  # Maximum expected length
        
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-long",
            current_stage_name="initial",
            author=long_author
        )

        assert context.author == long_author
        assert len(context.author) == 255

