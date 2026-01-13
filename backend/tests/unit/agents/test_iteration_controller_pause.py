"""
Unit tests for iteration controller pause detection.

Tests the logic that detects when max iterations is reached
and raises SessionPaused exception.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tarsy.agents.exceptions import MaxIterationsFailureError, SessionPaused
from tarsy.agents.iteration_controllers.react_base_controller import ReactController
from tarsy.models.processing_context import StageContext
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


class TestReactController(ReactController):
    """Concrete implementation of ReactController for testing."""
    
    def build_initial_conversation(self, context: StageContext) -> LLMConversation:
        """Build test conversation."""
        return LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Test question")
            ]
        )


@pytest.mark.unit
class TestIterationControllerPauseDetection:
    """Test suite for iteration controller pause detection."""
    
    @pytest.mark.asyncio
    async def test_pause_at_max_iterations_with_successful_interaction(self) -> None:
        """Test that SessionPaused is raised when max iterations reached with successful last interaction."""
        # Create mock LLM client that successfully generates responses but never returns Final Answer
        mock_llm_manager = AsyncMock()
        
        async def mock_generate(*args, **kwargs):
            # Always return success but no Final Answer to trigger pause
            return LLMConversation(
                messages=[
                    LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                    LLMMessage(role=MessageRole.USER, content="Question"),
                    LLMMessage(role=MessageRole.ASSISTANT, content="Thought: Analyzing")
                ]
            )
        
        mock_llm_manager.generate_response = mock_generate
        
        # Create controller
        mock_prompt_builder = MagicMock()
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Create mock context with agent
        mock_agent = MagicMock()
        mock_agent.max_iterations = 2  # Set low for testing
        mock_agent.get_current_stage_execution_id.return_value = "test-stage-id"
        
        mock_chain_context = MagicMock()
        mock_chain_context.stage_outputs = {}
        mock_chain_context.chat_context = None
        
        context = MagicMock(spec=StageContext)
        context.agent = mock_agent
        context.stage_name = "test-stage"
        context.session_id = "test-session"
        context.chain_context = mock_chain_context
        context.available_tools = MagicMock()
        context.available_tools.tools = []
        
        # Mock settings with forced conclusion disabled
        with patch('tarsy.agents.iteration_controllers.react_base_controller.get_settings') as mock_settings:
            settings_mock = MagicMock()
            settings_mock.llm_iteration_timeout = 30
            settings_mock.force_conclusion_at_max_iterations = False
            mock_settings.return_value = settings_mock
            
            # Also need to mock in base_controller where the check happens
            # Also need to patch settings in base_controller where the check happens
            with patch('tarsy.config.settings.get_settings', return_value=settings_mock):
                # Execute should raise SessionPaused
                with pytest.raises(SessionPaused) as exc_info:
                    await controller.execute_analysis_loop(context)
        
        # Verify exception details
        assert exc_info.value.iteration == 2
        assert exc_info.value.recoverable is True
        assert exc_info.value.conversation is not None
    
    @pytest.mark.asyncio
    async def test_failure_at_max_iterations_with_failed_interaction(self) -> None:
        """Test that MaxIterationsFailureError is raised when last interaction failed."""
        # Create mock LLM client that fails
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_response = AsyncMock(side_effect=Exception("LLM error"))
        
        # Create controller
        mock_prompt_builder = MagicMock()
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Create mock context
        mock_agent = MagicMock()
        mock_agent.max_iterations = 1  # Set very low for testing
        mock_agent.get_current_stage_execution_id.return_value = "test-stage-id"
        
        mock_chain_context = MagicMock()
        mock_chain_context.stage_outputs = {}
        mock_chain_context.chat_context = None
        
        context = MagicMock(spec=StageContext)
        context.agent = mock_agent
        context.stage_name = "test-stage"
        context.session_id = "test-session"
        context.chain_context = mock_chain_context
        context.available_tools = MagicMock()
        context.available_tools.tools = []
        
        # Mock settings
        with patch('tarsy.agents.iteration_controllers.react_base_controller.get_settings') as mock_settings:
            settings_mock = MagicMock()
            settings_mock.llm_iteration_timeout = 30
            mock_settings.return_value = settings_mock
            
            # Execute should raise MaxIterationsFailureError
            with pytest.raises(MaxIterationsFailureError) as exc_info:
                await controller.execute_analysis_loop(context)
        
        # Verify it's a failure, not a pause
        assert exc_info.value.max_iterations == 1
        assert exc_info.value.recoverable is False
    
    @pytest.mark.asyncio
    async def test_pause_preserves_conversation_history(self) -> None:
        """Test that SessionPaused exception includes conversation history."""
        # Create mock LLM client with responses
        mock_llm_manager = AsyncMock()
        
        async def mock_generate(*args, **kwargs):
            # Always return success but no Final Answer
            return LLMConversation(
                messages=[
                    LLMMessage(role=MessageRole.SYSTEM, content="System"),
                    LLMMessage(role=MessageRole.USER, content="Question"),
                    LLMMessage(role=MessageRole.ASSISTANT, content="Thought: Analyzing")
                ]
            )
        
        mock_llm_manager.generate_response = mock_generate
        
        # Create controller
        mock_prompt_builder = MagicMock()
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Create context
        mock_agent = MagicMock()
        mock_agent.max_iterations = 3
        mock_agent.get_current_stage_execution_id.return_value = "test-stage-id"
        
        mock_chain_context = MagicMock()
        mock_chain_context.stage_outputs = {}
        mock_chain_context.chat_context = None
        
        context = MagicMock(spec=StageContext)
        context.agent = mock_agent
        context.stage_name = "test-stage"
        context.session_id = "test-session"
        context.chain_context = mock_chain_context
        context.available_tools = MagicMock()
        context.available_tools.tools = []
        
        with patch('tarsy.agents.iteration_controllers.react_base_controller.get_settings') as mock_settings:
            settings_mock = MagicMock()
            settings_mock.llm_iteration_timeout = 30
            settings_mock.force_conclusion_at_max_iterations = False
            mock_settings.return_value = settings_mock
            
            with patch('tarsy.config.settings.get_settings', return_value=settings_mock):
                with pytest.raises(SessionPaused) as exc_info:
                    await controller.execute_analysis_loop(context)
        
        # Verify conversation is preserved
        assert exc_info.value.conversation is not None
        assert len(exc_info.value.conversation.messages) >= 2
    
    @pytest.mark.asyncio
    async def test_resume_from_paused_state(self) -> None:
        """Test that controller can resume from paused conversation state."""
        # Create mock LLM client
        mock_llm_manager = AsyncMock()
        
        # Return final answer on resume
        final_conv = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Question"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Final Answer: Completed")
            ]
        )
        mock_llm_manager.generate_response = AsyncMock(return_value=final_conv)
        
        # Create controller
        mock_prompt_builder = MagicMock()
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Create context with paused conversation state
        paused_conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Question"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Thought: Analyzing...")
            ]
        )
        
        mock_agent = MagicMock()
        mock_agent.max_iterations = 50
        mock_agent.get_current_stage_execution_id.return_value = "test-stage-id"
        
        mock_stage_result = MagicMock()
        mock_stage_result.status = "paused"
        mock_stage_result.paused_conversation_state = paused_conversation.model_dump()
        
        mock_chain_context = MagicMock()
        mock_chain_context.stage_outputs = {
            "test-stage": mock_stage_result
        }
        
        context = MagicMock(spec=StageContext)
        context.agent = mock_agent
        context.stage_name = "test-stage"
        context.session_id = "test-session"
        context.chain_context = mock_chain_context
        context.available_tools = MagicMock()
        context.available_tools.tools = []
        
        with patch('tarsy.agents.iteration_controllers.react_base_controller.get_settings') as mock_settings:
            settings_mock = MagicMock()
            settings_mock.llm_iteration_timeout = 30
            mock_settings.return_value = settings_mock
            
            # Execute should complete (not pause again)
            result = await controller.execute_analysis_loop(context)
        
        # Verify completed
        assert "Completed" in result
    
    @pytest.mark.asyncio
    async def test_pause_context_includes_session_info(self) -> None:
        """Test that SessionPaused exception context includes session information."""
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_response = AsyncMock(
            return_value=LLMConversation(
                messages=[
                    LLMMessage(role=MessageRole.SYSTEM, content="System"),
                    LLMMessage(role=MessageRole.ASSISTANT, content="Test")
                ]
            )
        )
        
        mock_prompt_builder = MagicMock()
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        mock_agent = MagicMock()
        mock_agent.max_iterations = 1
        mock_agent.get_current_stage_execution_id.return_value = "stage-123"
        
        mock_chain_context = MagicMock()
        mock_chain_context.stage_outputs = {}
        mock_chain_context.chat_context = None
        
        context = MagicMock(spec=StageContext)
        context.agent = mock_agent
        context.stage_name = "analysis"
        context.session_id = "session-456"
        context.chain_context = mock_chain_context
        context.available_tools = MagicMock()
        context.available_tools.tools = []
        
        with patch('tarsy.agents.iteration_controllers.react_base_controller.get_settings') as mock_settings:
            settings_mock = MagicMock()
            settings_mock.llm_iteration_timeout = 30
            settings_mock.force_conclusion_at_max_iterations = False
            mock_settings.return_value = settings_mock
            
            with patch('tarsy.config.settings.get_settings', return_value=settings_mock):
                with pytest.raises(SessionPaused) as exc_info:
                    await controller.execute_analysis_loop(context)
        
        # Verify context information
        assert exc_info.value.context["session_id"] == "session-456"
        assert exc_info.value.context["stage_execution_id"] == "stage-123"
        assert exc_info.value.context["stage_name"] == "analysis"

