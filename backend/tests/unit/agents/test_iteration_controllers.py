"""
Unit tests for iteration controllers.

Tests the different iteration strategy implementations to ensure they behave correctly
and provide the expected processing patterns for agent execution.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.iteration_controllers.react_controller import SimpleReActController
from tarsy.agents.iteration_controllers.react_final_analysis_controller import (
    ReactFinalAnalysisController,
)
from tarsy.agents.iteration_controllers.react_stage_controller import (
    ReactStageController,
)
from tarsy.models.constants import IterationStrategy
from tarsy.models.processing_context import AvailableTools, ChainContext, StageContext
from tarsy.models.unified_interactions import LLMConversation, MessageRole


@pytest.mark.unit
class TestSimpleReActController:
    """Test SimpleReActController implementation."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM client."""
        client = Mock()
        
        async def mock_generate_response(conversation, session_id, stage_execution_id=None, **kwargs):
            # Create a new conversation with the assistant response added
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final Answer: Analysis complete")
            return updated_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_generate_response)
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_standard_react_prompt.return_value = "ReAct prompt"
        builder.get_enhanced_react_system_message.return_value = "You are an AI assistant that analyzes alerts using the ReAct pattern."
        builder.parse_react_response.return_value = {
            'thought': 'Need to analyze the alert',
            'action': 'test-tool',
            'action_input': 'param=value',
            'is_complete': True,
            'final_answer': 'Analysis complete'
        }
        builder.convert_action_to_tool_call.return_value = {
            "server": "test-server",
            "tool": "test-tool",
            "parameters": {"param": "value"},
            "reason": "test"
        }
        builder.format_observation.return_value = "Tool executed successfully"
        builder.get_react_error_continuation.return_value = ["Error occurred, continuing analysis..."]
        builder._flatten_react_history.return_value = ["Thought: Analysis needed", "Action: test-tool", "Observation: Tool executed successfully"]
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for ReAct testing."""
        agent = Mock()
        agent.max_iterations = 3
        # EP-0012: create_prompt_context method removed, using StageContext directly
        agent.execute_mcp_tools = AsyncMock(return_value={
            "test-server": [{"tool": "test-tool", "result": "success"}]
        })
        agent._compose_instructions.return_value = "Composed instructions with MCP server guidance"
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_manager, mock_prompt_builder):
        """Create SimpleReActController instance."""
        return SimpleReActController(mock_llm_manager, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample stage context for ReAct testing."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert", "severity": "high"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        available_tools = AvailableTools(tools=[])
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success(self, controller, sample_context, mock_llm_manager):
        """Test successful ReAct analysis loop with final answer."""
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return last assistant message containing final answer
        assert result == "Final Answer: Analysis complete"
        
        # Verify LLM was called
        mock_llm_manager.generate_response.assert_called()
        
        # Verify system message contains ReAct instructions
        conversation_arg = mock_llm_manager.generate_response.call_args.kwargs['conversation']
        system_message = conversation_arg.messages[0]
        assert "ReAct" in system_message.content
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test ReAct analysis loop with missing agent reference."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "test-pod", "namespace": "default"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        available_tools = AvailableTools(tools=[])
        context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=None
        )
        
        with pytest.raises(ValueError, match="Agent reference is required in context"):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_action_execution(
        self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder
    ):
        """Test ReAct loop that executes an action before completing."""
        # Mock LLM responses in ReAct format for the parser to understand
        react_responses = [
            "Thought: Need to get more info\nAction: test-server.test-tool\nAction Input: param=value",
            "Thought: Now I have enough info\nFinal Answer: Complete analysis"
        ]
        
        call_count = 0
        async def mock_generate_response_with_sequence(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            response = react_responses[call_count] if call_count < len(react_responses) else react_responses[-1]
            updated_conversation.append_assistant_message(response)
            call_count += 1
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_response_with_sequence
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return last assistant message containing final answer
        assert result == "Thought: Now I have enough info\nFinal Answer: Complete analysis"
        
        # Verify tool was executed
        mock_agent.execute_mcp_tools.assert_called_once()
        
        # Verify multiple LLM calls for iterations
        assert mock_llm_manager.generate_response.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_max_iterations_with_successful_last_interaction(
        self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder
    ):
        """Test ReAct loop that reaches maximum iterations with successful last interaction - should pause."""
        from tarsy.agents.exceptions import SessionPaused
        
        mock_agent.max_iterations = 1  # Force max iterations quickly
        
        # Mock LLM to return incomplete responses (no Final Answer) to force max iterations
        async def mock_generate_response_incomplete(conversation, session_id, stage_execution_id=None, **kwargs):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Thought: Still thinking...")  # No Final Answer
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_response_incomplete
        
        # Should raise SessionPaused when reaching max iterations with successful last interaction
        with pytest.raises(SessionPaused) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        # Verify the exception details
        assert exc_info.value.iteration == 1
        assert exc_info.value.conversation is not None
        assert "Session paused at maximum iterations" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_max_iterations_with_failed_last_interaction(
        self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder
    ):
        """Test ReAct loop that reaches maximum iterations with failed last interaction (NEW BEHAVIOR)."""
        from tarsy.agents.exceptions import MaxIterationsFailureError
        
        mock_agent.max_iterations = 2  # Set max iterations
        
        # Mock LLM to fail on all attempts
        mock_llm_manager.generate_response.side_effect = Exception("LLM connection failed")
        
        # Should raise MaxIterationsFailureError (new failure detection behavior)
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        assert "Stage failed: reached maximum iterations (2) and last LLM interaction failed" in str(error)
        assert error.max_iterations == 2
        
        # Verify all iterations were attempted
        assert mock_llm_manager.generate_response.call_count == 2
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_tool_execution_error(
        self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder
    ):
        """Test ReAct loop with tool execution error."""
        # Mock tool execution to fail
        mock_agent.execute_mcp_tools.side_effect = Exception("Tool execution failed")
        
        # Mock LLM responses in ReAct format
        react_responses = [
            "Thought: Need to use tool\nAction: test-server.test-tool\nAction Input: param=value",
            "Thought: Tool failed but continuing\nFinal Answer: Analysis with error"
        ]
        
        call_count = 0
        async def mock_generate_response_with_error(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            response = react_responses[call_count] if call_count < len(react_responses) else react_responses[-1]
            updated_conversation.append_assistant_message(response)
            call_count += 1
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_response_with_error
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return last assistant message containing final answer
        assert result == "Thought: Tool failed but continuing\nFinal Answer: Analysis with error"
        
        # Verify tool execution was attempted
        mock_agent.execute_mcp_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_malformed_response_kept_with_specific_feedback(
        self, controller, sample_context, mock_agent, mock_llm_manager
    ):
        """Test that malformed responses are kept in context with specific error feedback."""
        mock_agent.max_iterations = 3
        
        # Mock LLM responses: first malformed (thought only), then valid
        react_responses = [
            "Thought: I need to check the pods but I forgot the format",  # Malformed - no Action or Final Answer
            "Thought: Let me fix my format\nFinal Answer: Analysis complete"  # Valid
        ]
        
        call_count = 0
        conversations_seen = []
        
        async def mock_generate_response_track_conversation(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            # Track the conversation to verify malformed message is kept
            conversations_seen.append([m.content for m in conversation.messages])
            
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            response = react_responses[call_count] if call_count < len(react_responses) else react_responses[-1]
            updated_conversation.append_assistant_message(response)
            call_count += 1
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_response_track_conversation
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should complete with final answer
        assert "Final Answer: Analysis complete" in result
        
        # Verify two LLM calls (first malformed, second valid)
        assert mock_llm_manager.generate_response.call_count == 2
        
        # Verify second call's conversation contains:
        # 1. The malformed assistant message (not deleted)
        # 2. Error feedback as observation
        if len(conversations_seen) >= 2:
            second_call_messages = conversations_seen[1]
            
            # The malformed message should be present (assistant message kept)
            malformed_present = any(
                "I need to check the pods but I forgot the format" in msg 
                for msg in second_call_messages
            )
            assert malformed_present, "Malformed assistant message should be kept in conversation"
            
            # Error feedback should be present (contains FORMAT ERROR)
            feedback_present = any(
                "FORMAT ERROR" in msg 
                for msg in second_call_messages
            )
            assert feedback_present, "Specific error feedback should be added to conversation"


@pytest.mark.unit
class TestReactFinalAnalysisController:
    """Test ReactFinalAnalysisController implementation."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM client."""
        client = Mock()
        
        async def mock_generate_response(conversation, session_id, stage_execution_id=None, **kwargs):
            # Create a new conversation with the assistant response added
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Comprehensive final analysis complete")
            return updated_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_generate_response)
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_final_analysis_prompt.return_value = "Final analysis prompt"
        # Final analysis doesn't use enhanced ReAct system message anymore
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for final analysis testing."""
        agent = Mock()
        # EP-0012: create_prompt_context method removed, using StageContext directly
        agent.get_current_stage_execution_id.return_value = "stage-exec-123"
        agent.get_general_instructions.return_value = "## General SRE Agent Instructions\nYou are an expert SRE..."
        agent.custom_instructions.return_value = "Custom agent instructions here"
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_manager, mock_prompt_builder):
        """Create ReactFinalAnalysisController instance."""
        return ReactFinalAnalysisController(mock_llm_manager, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample stage context for final analysis testing."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert", "severity": "high"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        available_tools = AvailableTools(tools=[])
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
    
    def test_needs_mcp_tools(self, controller):
        """Test that ReactFinalAnalysisController doesn't need MCP tools."""
        assert controller.needs_mcp_tools() is False
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success(self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder):
        """Test successful final analysis execution."""
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Comprehensive final analysis complete"
        
        # EP-0012: Prompt context creation now handled by StageContext and prompt builders
        # No separate create_prompt_context method in clean implementation
        # EP-0012: StageContext provides context data directly, no manual context creation needed
        
        # Verify prompt building was called
        mock_prompt_builder.build_final_analysis_prompt.assert_called_once()
        
        # Verify LLM was called with correct conversation
        mock_llm_manager.generate_response.assert_called_once()
        call_args = mock_llm_manager.generate_response.call_args[0]
        conversation = call_args[0]
        assert len(conversation.messages) == 2
        assert conversation.messages[0].role == MessageRole.SYSTEM
        assert "General SRE Agent Instructions" in conversation.messages[0].content
        assert conversation.messages[1].role == MessageRole.USER
        assert conversation.messages[1].content == "Final analysis prompt"
        
        # Verify session_id and stage execution id passed correctly
        assert call_args[1] == sample_context.session_id
        assert call_args[2] == "stage-exec-123"
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test final analysis loop with missing agent reference."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "test-pod", "namespace": "default"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        available_tools = AvailableTools(tools=[])
        context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=None
        )
        
        # Should not raise error, agent is used but validated internally
        with pytest.raises(AttributeError):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_previous_stage_data(self, controller, sample_context, mock_agent, mock_llm_manager):
        """Test final analysis execution (previous stage data handled at chain level)."""        
        result = await controller.execute_analysis_loop(sample_context)
        
        assert result == "Comprehensive final analysis complete"
        
        # EP-0012: Context creation handled by StageContext directly
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_minimal_context(self, controller, mock_agent, mock_llm_manager, mock_prompt_builder):
        """Test final analysis with minimal context."""
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
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        available_tools = AvailableTools(tools=[])
        context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        result = await controller.execute_analysis_loop(context)
        
        assert result == "Comprehensive final analysis complete"
        
        # EP-0012: Context creation handled by StageContext and prompt builders directly
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_llm_failure(self, controller, sample_context, mock_llm_manager):
        """Test final analysis when LLM call fails (NEW BEHAVIOR - MaxIterationsFailureError)."""
        from tarsy.agents.exceptions import MaxIterationsFailureError
        
        mock_llm_manager.generate_response.side_effect = Exception("LLM service unavailable")
        
        # Should now raise MaxIterationsFailureError instead of regular Exception
        with pytest.raises(MaxIterationsFailureError) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        error = exc_info.value
        assert "Final analysis stage failed: LLM service unavailable" in str(error)
        assert error.max_iterations == 1  # Final analysis has only 1 attempt
        assert error.context["stage_type"] == "final_analysis"

@pytest.mark.unit
class TestReactStageController:
    """Test ReactStageController implementation."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM client."""
        client = Mock()
        
        async def mock_generate_response(conversation, session_id, stage_execution_id=None, **kwargs):
            # Create a new conversation with the assistant response added
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Thought: Need to analyze partially\nFinal Answer: Partial analysis complete")
            return updated_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_generate_response)
        return client
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_stage_analysis_react_prompt.return_value = "Stage analysis ReAct prompt"
        builder.get_enhanced_react_system_message.return_value = "You are an agent doing partial analysis using ReAct."
        builder.parse_react_response.return_value = {
            'thought': 'Need to analyze partially',
            'action': 'analysis-tool',
            'action_input': 'param=value',
            'is_complete': True,
            'final_answer': 'Partial analysis complete'
        }
        builder.convert_action_to_tool_call.return_value = {
            "server": "analysis-server",
            "tool": "analysis-tool",
            "parameters": {"param": "value"},
            "reason": "partial analysis"
        }
        builder.format_observation.return_value = "Tool executed successfully for analysis"
        builder.get_react_continuation_prompt.return_value = ["Please continue with analysis..."]
        builder.get_react_error_continuation.return_value = ["Error occurred, continue analysis..."]
        builder._flatten_react_history.return_value = ["Thought: Need analysis", "Action: analysis-tool", "Observation: Analysis done"]
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for partial analysis testing."""
        agent = Mock()
        agent.max_iterations = 3
        # EP-0012: create_prompt_context method removed, using StageContext directly
        agent.get_current_stage_execution_id.return_value = "stage-exec-789"
        agent.execute_mcp_tools = AsyncMock(return_value={
            "analysis-server": [{"tool": "analysis-tool", "result": "analysis data"}]
        })
        agent.merge_mcp_data = Mock(return_value={"merged": "analysis_data"})
        agent._compose_instructions.return_value = "Composed instructions with MCP server guidance"
        return agent
    
    @pytest.fixture
    def controller(self, mock_llm_manager, mock_prompt_builder):
        """Create ReactStageController instance."""
        return ReactStageController(mock_llm_manager, mock_prompt_builder)
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample stage context for partial analysis testing."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert", "severity": "high"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-789",
            current_stage_name="analysis"
        )
        available_tools = AvailableTools(tools=[])
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
    
    def test_needs_mcp_tools(self, controller):
        """Test that ReactStageController needs MCP tools."""
        assert controller.needs_mcp_tools() is True
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_success_immediate_completion(self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder):
        """Test successful partial analysis that completes immediately."""
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return full ReAct history for partial analysis
        assert "Thought: Need to analyze partially" in result
        assert "Final Answer: Partial analysis complete" in result
        
        # EP-0012: Agent context creation handled by StageContext directly
        
        # Verify prompt building
        mock_prompt_builder.build_stage_analysis_react_prompt.assert_called_once()
        
        # Verify LLM call
        mock_llm_manager.generate_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_no_agent(self, controller):
        """Test partial analysis loop with missing agent reference."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "test-pod", "namespace": "default"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        available_tools = AvailableTools(tools=[])
        context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=None
        )
        
        with pytest.raises(ValueError, match="Agent reference is required in context"):
            await controller.execute_analysis_loop(context)
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_tool_execution(self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder):
        """Test partial analysis loop that executes tools before completing."""
        # Mock LLM responses in ReAct format for the parser to understand
        react_responses = [
            "Thought: Need to analyze with tools\nAction: test-server.analysis-tool\nAction Input: param=value",
            "Thought: Analysis completed successfully\nFinal Answer: Comprehensive partial analysis"
        ]
        
        call_count = 0
        async def mock_generate_response_with_sequence(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            response = react_responses[call_count] if call_count < len(react_responses) else react_responses[-1]
            updated_conversation.append_assistant_message(response)
            call_count += 1
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_response_with_sequence
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return last assistant message containing final answer
        assert result == "Thought: Analysis completed successfully\nFinal Answer: Comprehensive partial analysis"
        
        # Verify tool was executed
        mock_agent.execute_mcp_tools.assert_called_once()
        
        # Verify multiple LLM calls
        assert mock_llm_manager.generate_response.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_max_iterations_with_fallback(self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder):
        """Test partial analysis loop that reaches maximum iterations - should pause."""
        from tarsy.agents.exceptions import SessionPaused
        
        mock_agent.max_iterations = 1  # Force quick max iterations
        
        # Mock responses that return LLMConversation objects
        call_count = 0
        async def mock_generate_response_incomplete(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Thought: Still analyzing...")  # No Final Answer
            call_count += 1
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_response_incomplete
        
        # Should raise SessionPaused when reaching max iterations
        with pytest.raises(SessionPaused) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        # Verify the exception details
        assert exc_info.value.iteration == 1
        assert exc_info.value.conversation is not None
        assert "Session paused at maximum iterations" in str(exc_info.value)
        
        # Should have attempted the ReAct analysis 
        assert mock_llm_manager.generate_response.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_fallback_failure(self, controller, sample_context, mock_agent, mock_llm_manager, mock_prompt_builder):
        """Test partial analysis loop that reaches max iterations - should pause."""
        from tarsy.agents.exceptions import SessionPaused
        
        mock_agent.max_iterations = 1
        
        # Mock LLM to return incomplete responses (no Final Answer) to force max iterations
        async def mock_generate_response_incomplete(conversation, session_id, stage_execution_id=None, **kwargs):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Thought: Still working on analysis...")  # No Final Answer
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_response_incomplete
        
        # Should raise SessionPaused when reaching max iterations
        with pytest.raises(SessionPaused) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        # Verify the exception details
        assert exc_info.value.iteration == 1
        assert exc_info.value.conversation is not None
        assert "Session paused at maximum iterations" in str(exc_info.value)

@pytest.mark.unit
class TestIterationControllerFactory:
    """Test the factory method in BaseAgent for creating iteration controllers."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        return Mock()
    
    @pytest.fixture
    def mock_prompt_builder(self):
        return Mock()
    
    def test_create_react_stage_controller(self, mock_llm_manager, mock_prompt_builder):
        """Test creating ReactStageController."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"

        
        with patch('tarsy.agents.base_agent.get_prompt_builder', return_value=mock_prompt_builder):
            agent = TestAgent(
                llm_manager=mock_llm_manager,
                mcp_client=Mock(),
                mcp_registry=Mock(),
                iteration_strategy=IterationStrategy.REACT_STAGE
            )
            
            assert isinstance(agent._iteration_controller, ReactStageController)
            assert agent.iteration_strategy == IterationStrategy.REACT_STAGE
    
    def test_create_react_iteration_controller(self, mock_llm_manager, mock_prompt_builder):
        """Test creating SimpleReActController."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder', return_value=mock_prompt_builder):
            agent = TestAgent(
                llm_manager=mock_llm_manager,
                mcp_client=Mock(),
                mcp_registry=Mock(),
                iteration_strategy=IterationStrategy.REACT
            )
            
            assert isinstance(agent._iteration_controller, SimpleReActController)
            assert agent.iteration_strategy == IterationStrategy.REACT
    
    def test_create_unknown_iteration_strategy_fails(self, mock_llm_manager, mock_prompt_builder):
        """Test that unknown iteration strategy raises AssertionError via assert_never."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder', return_value=mock_prompt_builder):
            with pytest.raises(AssertionError, match="Expected code to be unreachable"):
                TestAgent(
                    llm_manager=mock_llm_manager,
                    mcp_client=Mock(),
                    mcp_registry=Mock(),
                    iteration_strategy="unknown_strategy"  # Invalid strategy
                )

@pytest.mark.unit
class TestIterationControllerIntegration:
    """Test interaction between different iteration controllers and agents."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create all mock dependencies."""
        return {
            'llm_manager': Mock(),
            'mcp_client': Mock(),
            'mcp_registry': Mock(),
            'prompt_builder': Mock()
        }
    
    def test_react_vs_react_stage_initialization(self, mock_dependencies):
        """Test that different strategies create different controllers."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder', 
                   return_value=mock_dependencies['prompt_builder']):
            # Create agent with REACT strategy
            react_agent = TestAgent(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_client=mock_dependencies['mcp_client'],
                mcp_registry=mock_dependencies['mcp_registry'],
                iteration_strategy=IterationStrategy.REACT
            )
            
            # Create agent with REACT_STAGE strategy  
            react_stage_agent = TestAgent(
                llm_manager=mock_dependencies['llm_manager'],
                mcp_client=mock_dependencies['mcp_client'],
                mcp_registry=mock_dependencies['mcp_registry'],
                iteration_strategy=IterationStrategy.REACT_STAGE
            )
            
            # Verify different controller types
            assert isinstance(react_agent._iteration_controller, SimpleReActController)
            assert isinstance(react_stage_agent._iteration_controller, ReactStageController)
            
            # Verify strategy property works correctly
            assert react_agent.iteration_strategy == IterationStrategy.REACT
            assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE

@pytest.mark.unit
class TestFinalAnswerExtraction:
    """
    Test controller-level final answer extraction functionality.
    
    Note: Detailed ReAct parsing edge cases are tested in test_react_parser.py.
    These tests focus on the controller's integration with ReActParser and fallback behavior.
    """
    
    def test_extract_simple_final_answer(self):
        """Test extraction of simple single-line Final Answer."""
        controller = SimpleReActController(Mock(), Mock())
        
        test_response = """Thought: Analysis complete.

Final Answer: The system is operating normally."""
        
        result = controller._extract_react_final_analysis(test_response)
        
        assert result == "The system is operating normally."
    
    def test_extract_midline_final_answer(self):
        """Test extraction of Final Answer appearing mid-line (bug fix regression test).
        
        This was the original bug: "Final Answer:" appearing after a sentence boundary
        without a newline (e.g., "...action.Final Answer:") was not being extracted.
        """
        controller = SimpleReActController(Mock(), Mock())
        
        test_response = """Thought
Analysis shows critical issues identified.

Ready to provide final analysis.Final Answer:
**Impact**: HIGH

Recommended Actions:
Increase memory limit to 1Gi"""
        
        result = controller._extract_react_final_analysis(test_response)
        
        expected_result = """**Impact**: HIGH

Recommended Actions:
Increase memory limit to 1Gi"""
        
        assert result == expected_result
    
    def test_extract_complex_multi_section_final_answer(self):
        """Test extraction of complex multi-section Final Answer."""
        controller = SimpleReActController(Mock(), Mock())
        
        test_response = """Thought: Comprehensive analysis complete.

Final Answer:
## Summary
The system is experiencing high latency.

## Root Cause
Database queries are not optimized.

## Recommendations
1. Add indexes to frequently queried columns
2. Implement query caching
3. Monitor query performance

## Impact Assessment
- Current: 2000ms average response time
- Expected after fix: 200ms average response time"""
        
        result = controller._extract_react_final_analysis(test_response)
        
        expected_result = """## Summary
The system is experiencing high latency.

## Root Cause
Database queries are not optimized.

## Recommendations
1. Add indexes to frequently queried columns
2. Implement query caching
3. Monitor query performance

## Impact Assessment
- Current: 2000ms average response time
- Expected after fix: 200ms average response time"""
        
        assert result == expected_result
    
    def test_returns_entire_message_when_no_final_answer(self):
        """Test fallback: returns entire message when no Final Answer exists.
        
        When the last assistant message doesn't contain "Final Answer:",
        the method returns the entire message as-is so the user sees
        what the LLM generated (partial progress, incomplete analysis, etc).
        """
        controller = SimpleReActController(Mock(), Mock())
        
        # Various messages without Final Answer
        test_cases = [
            # Case 1: Thought and Action only
            """Thought: Starting work.
Action: do_something
Action Input: param=value""",
            
            # Case 2: Incomplete analysis message
            """Thought: Need more investigation.
Action: check_status
Analysis incomplete: Maximum iterations reached""",
            
            # Case 3: Message with observations (shouldn't happen with new _build_final_result, but test anyway)
            """Thought: Starting investigation.
Action: check_logs
Action Input: pod_name=test-pod"""
        ]
        
        for test_response in test_cases:
            result = controller._extract_react_final_analysis(test_response)
            assert result == test_response, f"Failed for: {test_response[:50]}..."
    
    def test_extract_with_empty_input(self):
        """Test extraction with empty/None input (edge case)."""
        controller = SimpleReActController(Mock(), Mock())
        
        # Empty string
        result = controller._extract_react_final_analysis("")
        assert result == "No analysis generated"
        
        # None should be handled gracefully
        result = controller._extract_react_final_analysis(None)
        assert result == "No analysis generated"


@pytest.mark.unit
class TestNativeToolsOverride:
    """
    Test _get_native_tools_override defensive behavior.
    
    Validates that the method safely handles missing processing_alert, mcp, 
    and native_tools attributes without raising AttributeError.
    """
    
    @pytest.fixture
    def controller(self):
        """Create controller instance for testing."""
        return SimpleReActController(Mock(), Mock())
    
    def test_get_native_tools_override_with_all_fields_present(self, controller):
        """Test extraction when all fields are present."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.mcp_selection_models import (
            MCPSelectionConfig,
            MCPServerSelection,
            NativeToolsConfig,
        )
        from tarsy.utils.timestamp import now_us
        
        # Create ProcessingAlert with full MCP configuration
        native_tools = NativeToolsConfig(
            google_search=True,
            code_execution=False,
            url_context=True
        )
        mcp_config = MCPSelectionConfig(
            servers=[MCPServerSelection(name="test-server")],  # MCPSelectionConfig requires at least 1 server
            native_tools=native_tools
        )
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            alert_data={},
            mcp=mcp_config
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=Mock()
        )
        
        result = controller._get_native_tools_override(stage_context)
        
        assert result is not None
        assert result.google_search is True
        assert result.code_execution is False
        assert result.url_context is True
    
    def test_get_native_tools_override_with_no_native_tools(self, controller):
        """Test extraction when mcp exists but native_tools is None."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.mcp_selection_models import (
            MCPSelectionConfig,
            MCPServerSelection,
        )
        from tarsy.utils.timestamp import now_us
        
        # Create ProcessingAlert with MCP but no native_tools
        mcp_config = MCPSelectionConfig(
            servers=[MCPServerSelection(name="test-server")]  # MCPSelectionConfig requires at least 1 server
            # native_tools defaults to None
        )
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            alert_data={},
            mcp=mcp_config
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=Mock()
        )
        
        result = controller._get_native_tools_override(stage_context)
        
        assert result is None
    
    def test_get_native_tools_override_with_no_mcp(self, controller):
        """Test extraction when processing_alert has no mcp field."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        # Create ProcessingAlert without MCP configuration
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            alert_data={}
            # mcp=None (default)
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        
        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=Mock()
        )
        
        result = controller._get_native_tools_override(stage_context)
        
        assert result is None
    
    def test_get_native_tools_override_with_missing_processing_alert(self, controller):
        """Test extraction when chain_context has no processing_alert (edge case)."""
        # Create a minimal ChainContext-like object without processing_alert
        # This tests the getattr defensive pattern
        class MinimalChainContext:
            """Minimal context for testing edge case."""
            pass
        
        minimal_context = MinimalChainContext()
        
        stage_context = StageContext(
            chain_context=minimal_context,  # type: ignore - intentionally invalid for testing
            available_tools=AvailableTools(tools=[]),
            agent=Mock()
        )
        
        # Should not raise AttributeError - should return None safely
        result = controller._get_native_tools_override(stage_context)
        
        assert result is None
    
    def test_get_native_tools_override_with_invalid_chain_context(self, controller):
        """Test extraction when chain_context itself is None (extreme edge case)."""
        # Create StageContext with None chain_context
        # This tests extreme defensive programming
        stage_context = StageContext(
            chain_context=None,  # type: ignore - intentionally invalid for testing
            available_tools=AvailableTools(tools=[]),
            agent=Mock()
        )
        
        # The defensive code is so good that even with None chain_context,
        # it doesn't raise AttributeError - it returns None gracefully!
        # getattr(None, "processing_alert", None) returns None without error
        result = controller._get_native_tools_override(stage_context)
        assert result is None