"""
Test cases for MaxIterationsFailureError and stage failure detection logic.

Tests the new failure detection functionality that marks stages and sessions as failed
when max iterations is reached with the last interaction failing.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.exceptions import AgentError, MaxIterationsFailureError
from tarsy.agents.iteration_controllers.simple_react_controller import SimpleReActController
from tarsy.agents.iteration_controllers.react_final_analysis_controller import (
    ReactFinalAnalysisController,
)
from tarsy.models.processing_context import AvailableTools, ChainContext, StageContext
from tarsy.models.unified_interactions import LLMConversation


@pytest.mark.unit
class TestMaxIterationsFailureError:
    """Test MaxIterationsFailureError exception class."""
    
    def test_exception_creation(self):
        """Test creating MaxIterationsFailureError with all parameters."""
        error = MaxIterationsFailureError(
            "Test message", 
            max_iterations=10,
            context={"session_id": "test-123"}
        )
        
        assert str(error) == "Test message"
        assert error.max_iterations == 10
        assert error.context["session_id"] == "test-123"
        assert error.recoverable is False  # Should be non-recoverable
        
    def test_exception_inheritance(self):
        """Test that MaxIterationsFailureError inherits from AgentError."""
        error = MaxIterationsFailureError("Test", max_iterations=5)
        
        assert isinstance(error, AgentError)
        assert isinstance(error, Exception)
        
    def test_exception_to_dict(self):
        """Test converting exception to dictionary."""
        error = MaxIterationsFailureError(
            "Test failure", 
            max_iterations=3,
            context={"stage": "test"}
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["error_type"] == "MaxIterationsFailureError"
        assert error_dict["message"] == "Test failure"
        assert error_dict["recoverable"] is False
        assert error_dict["max_iterations"] == 3
        assert error_dict["context"]["stage"] == "test"
        
    def test_exception_caught_as_agent_error(self):
        """Test that MaxIterationsFailureError can be caught as AgentError."""
        error = MaxIterationsFailureError("Test", max_iterations=1)
        
        try:
            raise error
        except AgentError as e:
            assert isinstance(e, MaxIterationsFailureError)
            assert e.max_iterations == 1
        except Exception:
            pytest.fail("Should have been caught as AgentError")


@pytest.mark.unit
class TestReactControllerMaxIterationsFailure:
    """Test ReactController failure detection for max iterations + last interaction failed."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM client that always fails."""
        client = Mock()
        client.generate_response = AsyncMock(side_effect=Exception("LLM connection error"))
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.get_enhanced_react_system_message.return_value = "System message"
        builder.build_standard_react_prompt.return_value = "User prompt"
        builder.build_react_forced_conclusion.return_value = "Please provide your best conclusion based on the available data."
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent."""
        agent = Mock()
        agent.max_iterations = 2  # Low number for testing
        agent.force_conclusion_at_max_iterations = False
        agent.get_force_conclusion.return_value = False
        agent.get_current_stage_execution_id.return_value = "stage-123"
        return agent
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample stage context."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-123",
            current_stage_name="analysis"
        )
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
    
    @pytest.fixture
    def controller(self, mock_llm_manager, mock_prompt_builder):
        """Create ReactController instance."""
        return SimpleReActController(mock_llm_manager, mock_prompt_builder)
    
    @pytest.mark.asyncio
    async def test_max_iterations_with_all_failed_interactions(self, controller, sample_context, mock_llm_manager):
        """Test that MaxIterationsFailureError is raised when max iterations reached with all failed interactions."""
        # Ensure all LLM calls fail
        mock_llm_manager.generate_response.side_effect = Exception("LLM connection error")
        
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        assert "Stage failed: reached maximum iterations (2) and last LLM interaction failed" in str(error)
        assert error.max_iterations == 2
        assert error.context["session_id"] == "session-123"
        assert error.context["stage_execution_id"] == "stage-123"
        
        # Verify LLM was called max_iterations times
        assert mock_llm_manager.generate_response.call_count == 2
    
    @pytest.mark.asyncio
    async def test_max_iterations_with_last_interaction_successful(self, controller, sample_context, mock_llm_manager):
        """Test that SessionPaused is raised when max iterations reached without final answer."""
        from tarsy.agents.exceptions import SessionPaused
        
        # Mock LLM to fail first, then succeed on last attempt
        call_count = 0
        async def mock_generate_with_final_success(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:  # Fail first attempt
                raise Exception("LLM connection error")
            else:  # Succeed on final attempt
                updated_conversation = LLMConversation(messages=conversation.messages.copy())
                updated_conversation.append_assistant_message("Thought: Working now")
                return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_with_final_success
        
        # Ensure chat_context is None so forced conclusion isn't triggered
        sample_context.chain_context.chat_context = None
        
        # Mock settings to disable forced conclusion
        with patch('tarsy.config.settings.get_settings') as mock_settings:
            settings_mock = Mock()
            settings_mock.force_conclusion_at_max_iterations = False
            settings_mock.llm_iteration_timeout = 30
            mock_settings.return_value = settings_mock
            
            # Should raise SessionPaused exception at max iterations
            with pytest.raises(SessionPaused) as exc_info:
                await controller.execute_analysis_loop(sample_context)
        
        assert "maximum iterations" in str(exc_info.value)
        assert exc_info.value.iteration == 2
        assert mock_llm_manager.generate_response.call_count == 2
    
    @pytest.mark.asyncio 
    async def test_successful_completion_before_max_iterations(self, controller, sample_context, mock_llm_manager):
        """Test that successful completion works normally before hitting max iterations."""
        # Mock LLM to succeed with Final Answer
        async def mock_generate_success(conversation, session_id, stage_execution_id=None, **kwargs):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Thought: Analysis complete\nFinal Answer: Success")
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_success
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should complete successfully
        assert "Thought: Analysis complete" in result
        assert "Final Answer: Success" in result
        assert mock_llm_manager.generate_response.call_count == 1  # Only one call needed


@pytest.mark.unit
class TestReactFinalAnalysisControllerFailureDetection:
    """Test ReactFinalAnalysisController failure detection for any LLM errors."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM client."""
        return Mock()
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_final_analysis_prompt.return_value = "Final analysis prompt"
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent."""
        agent = Mock()
        agent.get_current_stage_execution_id.return_value = "stage-456"
        agent.get_general_instructions.return_value = "General instructions"
        agent.custom_instructions.return_value = "Custom instructions"
        return agent
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample stage context."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-456",
            current_stage_name="final-diagnosis"
        )
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
    
    @pytest.fixture
    def controller(self, mock_llm_manager, mock_prompt_builder):
        """Create ReactFinalAnalysisController instance."""
        return ReactFinalAnalysisController(mock_llm_manager, mock_prompt_builder)
    
    @pytest.mark.asyncio
    async def test_llm_exception_raises_max_iterations_failure(self, controller, sample_context, mock_llm_manager):
        """Test that any LLM exception raises MaxIterationsFailureError."""
        mock_llm_manager.generate_response = AsyncMock(side_effect=Exception("LLM service unavailable"))
        
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        assert "Final analysis stage failed: LLM service unavailable" in str(error)
        assert error.max_iterations == 1  # Final analysis has only 1 attempt
        assert error.context["session_id"] == "session-456"
        assert error.context["stage_execution_id"] == "stage-456"
        assert error.context["stage_type"] == "final_analysis"
        assert error.context["original_error"] == "LLM service unavailable"
    
    @pytest.mark.asyncio
    async def test_no_response_raises_max_iterations_failure(self, controller, sample_context, mock_llm_manager):
        """Test that no LLM response raises MaxIterationsFailureError."""
        # Mock LLM to return conversation with no assistant message
        async def mock_generate_no_response(conversation, session_id, stage_execution_id=None, **kwargs):
            return LLMConversation(messages=conversation.messages.copy())  # No assistant message added
        
        mock_llm_manager.generate_response = AsyncMock(side_effect=mock_generate_no_response)
        
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        assert "Final analysis stage failed: LLM returned no response" in str(error)
        assert error.max_iterations == 1
        assert error.context["stage_type"] == "final_analysis"
    
    @pytest.mark.asyncio
    async def test_successful_response_returns_content(self, controller, sample_context, mock_llm_manager):
        """Test that successful LLM response returns content normally."""
        # Mock successful LLM response
        async def mock_generate_success(conversation, session_id, stage_execution_id=None, **kwargs):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final analysis complete")
            return updated_conversation
        
        mock_llm_manager.generate_response = AsyncMock(side_effect=mock_generate_success)
        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Final analysis complete"
    
    @pytest.mark.asyncio
    async def test_max_iterations_failure_error_re_raised(self, controller, sample_context, mock_llm_manager):
        """Test that MaxIterationsFailureError from LLM client is re-raised as-is."""
        original_error = MaxIterationsFailureError("Original error", max_iterations=5)
        mock_llm_manager.generate_response = AsyncMock(side_effect=original_error)
        
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        # Should be the same exact error object
        assert exc_info.value is original_error
        assert exc_info.value.max_iterations == 5


@pytest.mark.unit
class TestEnhancedErrorMessagePropagation:
    """Test that underlying LLM errors are surfaced in stage failure messages."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM manager."""
        return Mock()
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.get_enhanced_react_system_message.return_value = "System message"
        builder.build_standard_react_prompt.return_value = "User prompt"
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent."""
        agent = Mock()
        agent.max_iterations = 2
        agent.force_conclusion_at_max_iterations = False
        agent.get_force_conclusion.return_value = False
        agent.get_current_stage_execution_id.return_value = "stage-enhanced-test"
        agent.get_native_system_instructions.return_value = "System instructions"
        agent.get_general_instructions.return_value = "General instructions"
        agent.custom_instructions.return_value = "Custom instructions"
        agent.get_parallel_execution_metadata.return_value = None
        return agent
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample stage context."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-enhanced-test",
            current_stage_name="analysis"
        )
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "llm_error_message,expected_in_error",
        [
            (
                "gemini-2.5-flash API error: No generation chunks were returned | Details: Type=ValueError | Message=No generation chunks were returned",
                "Last error: gemini-2.5-flash API error: No generation chunks were returned"
            ),
            (
                "Rate limit exceeded: 429 Too Many Requests",
                "Last error: Rate limit exceeded: 429 Too Many Requests"
            ),
            (
                "LLM service unavailable: 503 Service Unavailable",
                "Last error: LLM service unavailable: 503 Service Unavailable"
            ),
        ],
    )
    async def test_react_controller_includes_llm_error_in_stage_failure(
        self, 
        mock_llm_manager, 
        mock_prompt_builder, 
        sample_context, 
        llm_error_message: str,
        expected_in_error: str
    ):
        """Test that ReAct controller includes underlying LLM error in MaxIterationsFailureError message."""
        controller = SimpleReActController(mock_llm_manager, mock_prompt_builder)
        
        # Mock LLM to fail with specific error message
        mock_llm_manager.generate_response.side_effect = Exception(llm_error_message)
        
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        error_msg = str(error)
        
        # Verify the generic part is present
        assert "Stage failed: reached maximum iterations (2) and last LLM interaction failed" in error_msg
        
        # Verify the underlying error is included
        assert expected_in_error in error_msg
        assert llm_error_message in error_msg
        
        # Verify error metadata
        assert error.max_iterations == 2
        assert error.context["session_id"] == "session-enhanced-test"
    
    @pytest.mark.asyncio
    async def test_react_controller_backward_compatibility_without_error_message(
        self,
        mock_llm_manager,
        mock_prompt_builder,
        sample_context
    ):
        """Test that ReAct controller handles cases where error message is not captured (backward compatibility)."""
        controller = SimpleReActController(mock_llm_manager, mock_prompt_builder)
        
        # This shouldn't happen in practice, but ensures backward compatibility
        mock_llm_manager.generate_response.side_effect = Exception()
        
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        error_msg = str(error)
        
        # Should still have the generic message
        assert "Stage failed: reached maximum iterations (2) and last LLM interaction failed" in error_msg
        
        # Should not crash even without detailed error message
        assert error.max_iterations == 2
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "last_error_message,expected_error_format",
        [
            (
                "gemini-2.5-flash API error: No generation chunks were returned",
                "Stage failed: reached maximum iterations (5) and last LLM interaction failed. Last error: gemini-2.5-flash API error: No generation chunks were returned"
            ),
            (
                "Native thinking API error: Request quota exceeded",
                "Stage failed: reached maximum iterations (5) and last LLM interaction failed. Last error: Native thinking API error: Request quota exceeded"
            ),
            (
                None,
                "Stage failed: reached maximum iterations (5) and last LLM interaction failed"
            ),
        ],
    )
    async def test_base_controller_raise_max_iterations_exception_with_error_message(
        self,
        sample_context,
        last_error_message: str | None,
        expected_error_format: str
    ):
        """Test that _raise_max_iterations_exception includes underlying error when provided."""
        from tarsy.agents.iteration_controllers.base_controller import IterationController
        from tarsy.models.unified_interactions import LLMConversation
        
        # Create a minimal concrete implementation for testing
        class TestController(IterationController):
            def needs_mcp_tools(self) -> bool:
                return False
            
            async def execute_analysis_loop(self, context):
                pass
            
            def _get_forced_conclusion_prompt(self, iteration: int) -> str:
                return "Please conclude"
        
        from tarsy.models.unified_interactions import LLMMessage, MessageRole
        
        controller = TestController()
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="system"),
            LLMMessage(role=MessageRole.USER, content="test")
        ])
        
        # Test that the method raises MaxIterationsFailureError with the expected message
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            controller._raise_max_iterations_exception(
                max_iterations=5,
                last_interaction_failed=True,
                conversation=conversation,
                context=sample_context,
                logger=None,
                last_error_message=last_error_message
            )
        
        error = exc_info.value
        assert str(error) == expected_error_format
        assert error.max_iterations == 5
    
    @pytest.mark.asyncio
    async def test_error_message_preserved_across_iterations(
        self,
        mock_llm_manager,
        mock_prompt_builder,
        sample_context
    ):
        """Test that error message from the LAST failed iteration is captured, not earlier ones."""
        controller = SimpleReActController(mock_llm_manager, mock_prompt_builder)
        
        # First iteration fails with one error, second fails with different error
        call_count = 0
        async def mock_generate_with_different_errors(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First iteration error: transient network issue")
            else:
                raise Exception("Second iteration error: API rate limit")
        
        mock_llm_manager.generate_response.side_effect = mock_generate_with_different_errors
        
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        error_msg = str(error)
        
        # Should contain the LAST error (second iteration), not the first
        assert "Last error: Second iteration error: API rate limit" in error_msg
        assert "First iteration error" not in error_msg
