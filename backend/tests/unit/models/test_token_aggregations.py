"""
Unit tests for token usage aggregation functionality added in EP-0009.

Tests the computed fields in DetailedStage and SessionStats models that
aggregate token usage from LLM interactions.
"""

import pytest

from tarsy.models.constants import StageStatus
from tarsy.models.history_models import (
    ChainStatistics,
    DetailedStage,
    LLMTimelineEvent,
    SessionStats,
)
from tarsy.models.unified_interactions import (
    LLMConversation,
    LLMInteraction,
    LLMMessage,
    MessageRole,
)


@pytest.mark.unit
class TestDetailedStageTokenAggregations:
    """Test stage-level token aggregation computed fields."""
    
    def create_llm_timeline_event(self, input_tokens=None, output_tokens=None, total_tokens=None, 
                                   event_id=None, step_description="Test LLM call"):
        """Helper to create LLM timeline event with token data."""
        # Create a basic conversation for the interaction
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Test response")
        ])
        
        # Create LLM interaction with token data
        interaction = LLMInteraction(
            session_id="test-session",
            stage_execution_id="test-stage",
            model_name="gpt-4",
            conversation=conversation,
            duration_ms=1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens
        )
        
        # Create timeline event
        event_id_str = event_id or f"event-{id(interaction)}"  # Use id() instead of hash()
        timeline_event = LLMTimelineEvent(
            id=event_id_str,  # Required field
            event_id=event_id_str,  # Also required
            timestamp_us=1640995200000000,
            step_description=step_description,
            duration_ms=1000,
            stage_execution_id="test-stage",
            details=interaction
        )
        
        return timeline_event
    
    def test_stage_input_tokens_with_single_interaction(self):
        """Test stage input tokens calculation with single LLM interaction."""
        # Arrange
        llm_event = self.create_llm_timeline_event(input_tokens=120, output_tokens=45, total_tokens=165)
        
        stage = DetailedStage(
            execution_id="stage-123",
            session_id="session-456",
            stage_id="analysis",
            stage_index=0,
            stage_name="Analysis Stage",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event],
            mcp_communications=[]
        )
        
        # Act & Assert
        assert stage.stage_input_tokens == 120
        assert stage.stage_output_tokens == 45
        assert stage.stage_total_tokens == 165
    
    def test_stage_token_aggregation_multiple_interactions(self):
        """Test token aggregation with multiple LLM interactions."""
        # Arrange
        llm_event1 = self.create_llm_timeline_event(input_tokens=100, output_tokens=30, total_tokens=130, event_id="event-1")
        llm_event2 = self.create_llm_timeline_event(input_tokens=80, output_tokens=25, total_tokens=105, event_id="event-2")
        llm_event3 = self.create_llm_timeline_event(input_tokens=50, output_tokens=15, total_tokens=65, event_id="event-3")
        
        stage = DetailedStage(
            execution_id="stage-123",
            session_id="session-456", 
            stage_id="analysis",
            stage_index=0,
            stage_name="Analysis Stage",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event1, llm_event2, llm_event3],
            mcp_communications=[]
        )
        
        # Act & Assert
        assert stage.stage_input_tokens == 230  # 100 + 80 + 50
        assert stage.stage_output_tokens == 70  # 30 + 25 + 15  
        assert stage.stage_total_tokens == 300  # 130 + 105 + 65
    
    def test_stage_token_aggregation_mixed_interactions(self):
        """Test token aggregation when some interactions have token data and others don't."""
        # Arrange
        llm_event_with_tokens = self.create_llm_timeline_event(input_tokens=100, output_tokens=30, total_tokens=130, event_id="event-with")
        llm_event_without_tokens = self.create_llm_timeline_event(input_tokens=None, output_tokens=None, total_tokens=None, event_id="event-without")
        llm_event_partial_tokens = self.create_llm_timeline_event(input_tokens=80, output_tokens=None, total_tokens=80, event_id="event-partial")
        
        stage = DetailedStage(
            execution_id="stage-123",
            session_id="session-456",
            stage_id="analysis", 
            stage_index=0,
            stage_name="Analysis Stage",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event_with_tokens, llm_event_without_tokens, llm_event_partial_tokens],
            mcp_communications=[]
        )
        
        # Act & Assert
        assert stage.stage_input_tokens == 180  # 100 + 0 + 80 (None values treated as 0)
        assert stage.stage_output_tokens == 30   # 30 + 0 + 0
        assert stage.stage_total_tokens == 210   # 130 + 0 + 80
    
    def test_stage_token_aggregation_no_llm_interactions(self):
        """Test token aggregation returns None when no LLM interactions."""
        # Arrange
        stage = DetailedStage(
            execution_id="stage-123",
            session_id="session-456",
            stage_id="mcp-only",
            stage_index=0, 
            stage_name="MCP Only Stage",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[],  # No LLM interactions
            mcp_communications=[]
        )
        
        # Act & Assert
        assert stage.stage_input_tokens is None
        assert stage.stage_output_tokens is None
        assert stage.stage_total_tokens is None
    
    def test_stage_token_aggregation_zero_tokens(self):
        """Test that zero token totals return None for cleaner display."""
        # Arrange
        llm_event = self.create_llm_timeline_event(input_tokens=0, output_tokens=0, total_tokens=0)
        
        stage = DetailedStage(
            execution_id="stage-123",
            session_id="session-456",
            stage_id="analysis",
            stage_index=0,
            stage_name="Analysis Stage", 
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event],
            mcp_communications=[]
        )
        
        # Act & Assert - Zero totals should return None
        assert stage.stage_input_tokens is None
        assert stage.stage_output_tokens is None
        assert stage.stage_total_tokens is None


@pytest.mark.unit  
class TestSessionStatsTokenAggregations:
    """Test session-level token aggregation in SessionStats model."""
    
    def test_session_stats_with_token_data(self):
        """Test SessionStats creation with token usage data."""
        # Arrange
        chain_stats = ChainStatistics(
            total_stages=3,
            completed_stages=3,
            failed_stages=0,
            stages_by_agent={"TestAgent": 3}
        )
        
        # Act
        session_stats = SessionStats(
            total_interactions=5,
            llm_interactions=3,
            mcp_communications=2,
            errors_count=0,
            total_duration_ms=5000,
            session_input_tokens=300,
            session_output_tokens=120,
            session_total_tokens=420,
            chain_statistics=chain_stats
        )
        
        # Assert
        assert session_stats.session_input_tokens == 300
        assert session_stats.session_output_tokens == 120  
        assert session_stats.session_total_tokens == 420
    
    def test_session_stats_with_zero_token_data(self):
        """Test SessionStats with zero token values."""
        # Arrange
        chain_stats = ChainStatistics(
            total_stages=1,
            completed_stages=1,
            failed_stages=0,
            stages_by_agent={"TestAgent": 1}
        )
        
        # Act
        session_stats = SessionStats(
            total_interactions=2,
            llm_interactions=0,  # No LLM interactions
            mcp_communications=2,
            errors_count=0,
            total_duration_ms=1000,
            session_input_tokens=0,  # Zero token values
            session_output_tokens=0,
            session_total_tokens=0,
            chain_statistics=chain_stats
        )
        
        # Assert
        assert session_stats.session_input_tokens == 0
        assert session_stats.session_output_tokens == 0
        assert session_stats.session_total_tokens == 0


@pytest.mark.unit
class TestTokenAggregationIntegration:
    """Test integration between different levels of token aggregation."""
    
    def test_stage_to_session_token_aggregation_flow(self):
        """Test that stage token aggregations can be summed for session totals."""
        # Helper to create timeline events
        def create_event(input_tokens, output_tokens, total_tokens, event_id):
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="Test question"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Test response")
            ])
            
            interaction = LLMInteraction(
                session_id="test-session",
                stage_execution_id="test-stage",
                model_name="gpt-4",
                conversation=conversation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens
            )
            
            return LLMTimelineEvent(
                id=event_id,
                event_id=event_id,
                timestamp_us=1640995200000000,
                step_description="Test LLM call",
                duration_ms=1000,
                stage_execution_id="test-stage",
                details=interaction
            )
        
        # Arrange - Create multiple events with different token usage
        llm_event1 = create_event(100, 30, 130, "event-1")
        llm_event2 = create_event(150, 45, 195, "event-2")
        llm_event3 = create_event(80, 25, 105, "event-3")
        
        stage1 = DetailedStage(
            execution_id="stage-1",
            session_id="session-456",
            stage_id="analysis",
            stage_index=0,
            stage_name="Analysis",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event1, llm_event2],  # Two interactions
            mcp_communications=[]
        )
        
        stage2 = DetailedStage(
            execution_id="stage-2", 
            session_id="session-456",
            stage_id="action",
            stage_index=1,
            stage_name="Action",
            agent="TestAgent", 
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event3],  # One interaction
            mcp_communications=[]
        )
        
        # Act - Calculate stage totals
        stage1_input = stage1.stage_input_tokens
        stage1_output = stage1.stage_output_tokens  
        stage1_total = stage1.stage_total_tokens
        
        stage2_input = stage2.stage_input_tokens
        stage2_output = stage2.stage_output_tokens
        stage2_total = stage2.stage_total_tokens
        
        # Calculate session totals (simulating HistoryService logic)
        session_input_total = stage1_input + stage2_input
        session_output_total = stage1_output + stage2_output
        session_total_total = stage1_total + stage2_total
        
        # Assert stage calculations
        assert stage1_input == 250    # 100 + 150
        assert stage1_output == 75    # 30 + 45
        assert stage1_total == 325    # 130 + 195
        
        assert stage2_input == 80     # Single interaction
        assert stage2_output == 25
        assert stage2_total == 105
        
        # Assert session aggregation
        assert session_input_total == 330   # 250 + 80
        assert session_output_total == 100  # 75 + 25
        assert session_total_total == 430   # 325 + 105
    
    def test_mixed_stage_token_aggregation(self):
        """Test aggregation with stages that have different token availability."""
        # Helper to create timeline events
        def create_event(input_tokens, output_tokens, total_tokens, event_id):
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="Test question"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Test response")
            ])
            
            interaction = LLMInteraction(
                session_id="test-session",
                stage_execution_id="test-stage",
                model_name="gpt-4",
                conversation=conversation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens
            )
            
            return LLMTimelineEvent(
                id=event_id,
                event_id=event_id,
                timestamp_us=1640995200000000,
                step_description="Test LLM call", 
                duration_ms=1000,
                stage_execution_id="test-stage",
                details=interaction
            )
        
        # Arrange - One stage with tokens, one without
        llm_event_with_tokens = create_event(200, 60, 260, "event-with")
        llm_event_without_tokens = create_event(None, None, None, "event-without")
        
        stage_with_tokens = DetailedStage(
            execution_id="stage-1",
            session_id="session-456",
            stage_id="analysis",
            stage_index=0,
            stage_name="Analysis",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event_with_tokens],
            mcp_communications=[]
        )
        
        stage_without_tokens = DetailedStage(
            execution_id="stage-2",
            session_id="session-456", 
            stage_id="mcp-only",
            stage_index=1,
            stage_name="MCP Only",
            agent="TestAgent",
            status=StageStatus.COMPLETED,
            llm_interactions=[llm_event_without_tokens],  # Interaction without token data
            mcp_communications=[]
        )
        
        # Act
        stage1_tokens = stage_with_tokens.stage_total_tokens
        stage2_tokens = stage_without_tokens.stage_total_tokens
        
        # Calculate session total (simulating HistoryService logic)
        session_total = 0
        for stage_tokens in [stage1_tokens, stage2_tokens]:
            if stage_tokens:
                session_total += stage_tokens
        
        # Assert
        assert stage1_tokens == 260
        assert stage2_tokens is None  # No valid token data
        assert session_total == 260   # Only includes stage with token data
