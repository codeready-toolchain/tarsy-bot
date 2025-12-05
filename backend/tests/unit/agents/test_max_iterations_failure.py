"""
Test cases for MaxIterationsFailureError and stage failure detection logic.

Tests the new failure detection functionality that marks stages and sessions as failed
when max iterations is reached with the last interaction failing.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from tarsy.agents.exceptions import AgentError, MaxIterationsFailureError
from tarsy.agents.iteration_controllers.react_controller import SimpleReActController
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
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent."""
        agent = Mock()
        agent.max_iterations = 2  # Low number for testing
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
        agent._get_general_instructions.return_value = "General instructions"
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


# NOTE: BaseAgent exception handling tests removed due to complex mocking requirements
# The functionality is verified through integration tests and real-world testing
