"""
Unit tests for SessionPaused exception.

Tests the control flow exception used for pause/resume functionality.
"""

import pytest

from tarsy.agents.exceptions import SessionPaused, AgentError


class TestSessionPausedException:
    """Test suite for SessionPaused exception."""
    
    @pytest.mark.unit
    def test_session_paused_is_agent_error(self) -> None:
        """Test that SessionPaused is a subclass of AgentError."""
        exception = SessionPaused(
            message="Session paused at max iterations",
            iteration=30
        )
        assert isinstance(exception, AgentError)
    
    @pytest.mark.unit
    def test_session_paused_is_recoverable(self) -> None:
        """Test that SessionPaused is marked as recoverable."""
        exception = SessionPaused(
            message="Session paused at max iterations",
            iteration=30
        )
        assert exception.recoverable is True
    
    @pytest.mark.unit
    def test_session_paused_stores_iteration(self) -> None:
        """Test that SessionPaused stores the iteration count."""
        exception = SessionPaused(
            message="Session paused at max iterations",
            iteration=30
        )
        assert exception.iteration == 30
    
    @pytest.mark.unit
    def test_session_paused_stores_message(self) -> None:
        """Test that SessionPaused stores the message."""
        message = "Session paused at max iterations"
        exception = SessionPaused(
            message=message,
            iteration=30
        )
        assert str(exception) == message
    
    @pytest.mark.unit
    def test_session_paused_with_context(self) -> None:
        """Test that SessionPaused can store additional context."""
        context = {
            "stage_id": "initial-analysis",
            "agent": "kubernetes"
        }
        exception = SessionPaused(
            message="Session paused at max iterations",
            iteration=30,
            context=context
        )
        assert exception.context == context
    
    @pytest.mark.unit
    def test_session_paused_with_conversation(self) -> None:
        """Test that SessionPaused can store conversation state."""
        conversation = {"messages": ["message1", "message2"]}
        exception = SessionPaused(
            message="Session paused at max iterations",
            iteration=30,
            conversation=conversation
        )
        assert exception.conversation == conversation
    
    @pytest.mark.unit
    def test_session_paused_to_dict(self) -> None:
        """Test that SessionPaused converts to dictionary correctly."""
        context = {"stage_id": "initial-analysis"}
        exception = SessionPaused(
            message="Session paused at max iterations",
            iteration=30,
            context=context
        )
        
        result = exception.to_dict()
        
        assert result["error_type"] == "SessionPaused"
        assert result["message"] == "Session paused at max iterations"
        assert result["iteration"] == 30
        assert result["context"] == context
        assert result["recoverable"] is True
        assert "conversation" not in result
    
    @pytest.mark.unit
    def test_session_paused_without_context(self) -> None:
        """Test that SessionPaused works without context."""
        exception = SessionPaused(
            message="Session paused",
            iteration=15
        )
        assert exception.context == {}
        assert exception.iteration == 15

