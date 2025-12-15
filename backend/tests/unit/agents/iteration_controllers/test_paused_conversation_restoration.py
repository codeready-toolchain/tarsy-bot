"""Test paused conversation restoration for parallel agents."""

import pytest
from unittest.mock import Mock

from tarsy.agents.iteration_controllers.react_stage_controller import ReactStageController
from tarsy.models.processing_context import ChainContext, StageContext, AvailableTools
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import StageStatus
from tarsy.models.alert import ProcessingAlert


@pytest.fixture
def mock_agent():
    """Create mock agent with execution ID."""
    agent = Mock()
    agent.get_current_stage_execution_id.return_value = "exec-123"
    agent.max_iterations = 5
    return agent


@pytest.fixture
def chain_context():
    """Create basic chain context."""
    alert = ProcessingAlert(
        alert_type="test",
        severity="warning",
        timestamp=0,
        environment="test",
        alert_data={}
    )
    return ChainContext.from_processing_alert(
        processing_alert=alert,
        session_id="session-1",
        current_stage_name="test-stage"
    )


@pytest.fixture
def paused_conversation():
    """Create a paused conversation."""
    return LLMConversation(
        messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="User message"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Assistant response"),
        ]
    )


def test_restore_paused_conversation_with_execution_id_key(
    mock_agent, 
    chain_context, 
    paused_conversation
):
    """Test that paused conversation is correctly restored using execution_id as key."""
    # Setup paused result
    paused_result = AgentExecutionResult(
        status=StageStatus.PAUSED,
        agent_name="TestAgent",
        stage_name="test-stage",
        timestamp_us=0,
        result_summary="Paused",
        paused_conversation_state=paused_conversation.model_dump()
    )
    
    # Store with execution_id as key (simulating parallel agent resume)
    # This is how parallel_stage_executor stores paused states
    execution_id = "exec-123"
    chain_context.add_stage_result(execution_id, paused_result)
    
    # Create stage context
    stage_context = StageContext(
        chain_context=chain_context,
        available_tools=AvailableTools(),
        agent=mock_agent
    )
    
    # Create controller and restore
    controller = ReactStageController(Mock(), Mock())
    restored = controller._restore_paused_conversation(stage_context)
    
    # Verify restoration
    assert restored is not None
    assert len(restored.messages) == 3
    assert restored.messages[0].role == MessageRole.SYSTEM
    assert restored.messages[1].content == "User message"
    assert restored.messages[2].content == "Assistant response"


def test_restore_returns_none_when_execution_id_not_stored(
    mock_agent, 
    chain_context, 
    paused_conversation
):
    """Test that restoration returns None when execution_id key is not in context."""
    # Setup: Don't store anything in context
    # (Simulates trying to resume when no paused state exists)
    
    # Create stage context with agent that has execution_id
    stage_context = StageContext(
        chain_context=chain_context,
        available_tools=AvailableTools(),
        agent=mock_agent  # Has execution_id "exec-123"
    )
    
    # Create controller and restore
    controller = ReactStageController(Mock(), Mock())
    restored = controller._restore_paused_conversation(stage_context)
    
    # Should return None because execution_id key not found
    assert restored is None


def test_restore_paused_conversation_no_execution_id_returns_none(
    chain_context, 
    paused_conversation
):
    """Test that restoration returns None when agent has no execution ID (defensive check)."""
    # Setup agent without execution ID (should never happen in production)
    agent = Mock()
    agent.get_current_stage_execution_id.return_value = None
    agent.max_iterations = 5
    
    # Setup paused result
    paused_result = AgentExecutionResult(
        status=StageStatus.PAUSED,
        agent_name="TestAgent",
        stage_name="test-stage",
        timestamp_us=0,
        result_summary="Paused",
        paused_conversation_state=paused_conversation.model_dump()
    )
    
    # Store with stage_name key (old behavior)
    chain_context.add_stage_result("test-stage", paused_result)
    
    # Create stage context
    stage_context = StageContext(
        chain_context=chain_context,
        available_tools=AvailableTools(),
        agent=agent
    )
    
    # Create controller and restore
    controller = ReactStageController(Mock(), Mock())
    restored = controller._restore_paused_conversation(stage_context)
    
    # Should return None since execution_id is not set
    assert restored is None


def test_no_restoration_when_not_paused(mock_agent, chain_context):
    """Test that no restoration occurs when stage is not paused."""
    # Create completed result (not paused)
    completed_result = AgentExecutionResult(
        status=StageStatus.COMPLETED,
        agent_name="TestAgent",
        stage_name="test-stage",
        timestamp_us=0,
        result_summary="Completed"
    )
    
    chain_context.add_stage_result("test-stage", completed_result)
    
    stage_context = StageContext(
        chain_context=chain_context,
        available_tools=AvailableTools(),
        agent=mock_agent
    )
    
    controller = ReactStageController(Mock(), Mock())
    restored = controller._restore_paused_conversation(stage_context)
    
    assert restored is None


def test_only_uses_execution_id_ignores_stage_name(
    mock_agent, 
    chain_context, 
    paused_conversation
):
    """Test that restoration ONLY uses execution_id, ignoring stage_name keys."""
    # Create two different paused conversations
    stage_name_conversation = LLMConversation(
        messages=[LLMMessage(role=MessageRole.SYSTEM, content="Stage name key")]
    )
    execution_id_conversation = LLMConversation(
        messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="Execution ID key"),
            LLMMessage(role=MessageRole.USER, content="Execution ID user"),
        ]
    )
    
    # Store both
    stage_name_result = AgentExecutionResult(
        status=StageStatus.PAUSED,
        agent_name="TestAgent",
        stage_name="test-stage",
        timestamp_us=0,
        result_summary="Stage name",
        paused_conversation_state=stage_name_conversation.model_dump()
    )
    execution_id_result = AgentExecutionResult(
        status=StageStatus.PAUSED,
        agent_name="TestAgent",
        stage_name="test-stage",
        timestamp_us=0,
        result_summary="Execution ID",
        paused_conversation_state=execution_id_conversation.model_dump()
    )
    
    # Store with both keys (to verify execution_id is used exclusively)
    chain_context.add_stage_result("test-stage", stage_name_result)
    chain_context.add_stage_result("exec-123", execution_id_result)
    
    stage_context = StageContext(
        chain_context=chain_context,
        available_tools=AvailableTools(),
        agent=mock_agent
    )
    
    controller = ReactStageController(Mock(), Mock())
    restored = controller._restore_paused_conversation(stage_context)
    
    # Should get execution_id conversation (2 messages), NOT stage_name (1 message)
    # Verifies that we use execution_id exclusively
    assert restored is not None
    assert len(restored.messages) == 2
    assert restored.messages[0].content == "Execution ID key"

