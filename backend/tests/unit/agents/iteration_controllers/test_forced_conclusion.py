"""
Unit tests for forced conclusion at max iterations.

Tests the forced conclusion behavior when agents reach iteration limits,
including configuration-based triggering and chat context override.
"""

from unittest.mock import AsyncMock, Mock, patch
import pytest

from tarsy.agents.iteration_controllers.react_base_controller import ReactController
from tarsy.agents.iteration_controllers.native_thinking_controller import NativeThinkingController
from tarsy.models.processing_context import StageContext, ChainContext, AvailableTools
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.models.constants import LLMInteractionType


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


class TestNativeThinkingController(NativeThinkingController):
    """Concrete implementation of NativeThinkingController for testing."""
    
    def build_initial_conversation(self, context: StageContext) -> LLMConversation:
        """Build test conversation."""
        return LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Test question")
            ]
        )


@pytest.mark.unit
class TestForcedConclusionConfiguration:
    """Test forced conclusion configuration behavior."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM manager."""
        manager = AsyncMock()
        
        # Mock generate_response to return incomplete responses (no Final Answer)
        async def mock_generate_incomplete(conversation, session_id, stage_execution_id=None, **kwargs):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Thought: Still investigating...")
            return updated_conversation
        
        manager.generate_response = AsyncMock(side_effect=mock_generate_incomplete)
        return manager
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_standard_react_prompt.return_value = "ReAct prompt"
        builder.get_enhanced_react_system_message.return_value = "You are an AI assistant."
        builder.parse_react_response.return_value = {
            'thought': 'Investigating',
            'action': None,
            'action_input': None,
            'is_complete': False,
            'final_answer': None
        }
        builder.build_react_forced_conclusion_prompt.return_value = "Please conclude now."
        builder.build_native_thinking_forced_conclusion_prompt.return_value = "Please conclude now."
        return builder
    
    @pytest.fixture
    def sample_context(self):
        """Create sample context without chat context."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        mock_agent = Mock()
        mock_agent.max_iterations = 2
        mock_agent.get_current_stage_execution_id.return_value = "stage-123"
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        # Ensure no chat context
        chain_context.chat_context = None
        
        available_tools = AvailableTools(tools=[])
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
    
    @pytest.mark.asyncio
    async def test_force_conclusion_when_setting_enabled(
        self, mock_llm_manager, mock_prompt_builder, sample_context
    ):
        """Test that forced conclusion is triggered when setting is enabled."""
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Configure agent with forced conclusion enabled
        sample_context.agent.get_force_conclusion = Mock(return_value=True)
        
        # Mock the final conclusion LLM call
        original_generate = mock_llm_manager.generate_response.side_effect
        
        call_count = 0
        async def mock_generate_with_conclusion(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Check if this is the forced conclusion call
            interaction_type = kwargs.get('interaction_type')
            if interaction_type == LLMInteractionType.FORCED_CONCLUSION.value:
                updated_conversation = LLMConversation(messages=conversation.messages.copy())
                updated_conversation.append_assistant_message("Based on available data, here's my conclusion...")
                return updated_conversation
            else:
                # Regular incomplete response
                return await original_generate(conversation, session_id, stage_execution_id, **kwargs)
        
        mock_llm_manager.generate_response.side_effect = mock_generate_with_conclusion
        
        # Execute should return forced conclusion
        result = await controller.execute_analysis_loop(sample_context)
        
        # Verify forced conclusion interaction was invoked exactly once
        forced_conclusion_calls = [
            call for call in mock_llm_manager.generate_response.call_args_list
            if call.kwargs.get('interaction_type') == LLMInteractionType.FORCED_CONCLUSION.value
        ]
        assert len(forced_conclusion_calls) == 1, "Expected exactly one forced conclusion call"
        
        # Verify result is non-empty (any content is acceptable)
        assert result and len(result) > 0
    
    @pytest.mark.asyncio
    async def test_pause_when_setting_disabled(
        self, mock_llm_manager, mock_prompt_builder, sample_context
    ):
        """Test that SessionPaused is raised when setting is disabled."""
        from tarsy.agents.exceptions import SessionPaused
        
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Configure agent with forced conclusion disabled
        sample_context.agent.get_force_conclusion = Mock(return_value=False)
        
        # Should raise SessionPaused
        with pytest.raises(SessionPaused) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        # Verify exception details
        assert exc_info.value.iteration == 2
        assert exc_info.value.recoverable is True
    
    @pytest.mark.asyncio
    async def test_always_force_conclusion_for_chats(
        self, mock_llm_manager, mock_prompt_builder
    ):
        """Test that chats always force conclusion regardless of setting."""
        from tarsy.models.processing_context import ChatMessageContext
        from tarsy.utils.timestamp import now_us
        
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Create context WITH chat context
        mock_agent = Mock()
        mock_agent.max_iterations = 2
        mock_agent.get_current_stage_execution_id.return_value = "stage-123"
        
        from tarsy.models.alert import ProcessingAlert
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        # Set chat context
        chain_context.chat_context = ChatMessageContext(
            chat_id="chat-123",
            user_question="Follow-up question",
            conversation_history="Previous conversation"
        )
        
        available_tools = AvailableTools(tools=[])
        chat_context_obj = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        # Configure agent with forced conclusion DISABLED (but chats should still force conclusion)
        mock_agent.get_force_conclusion = Mock(return_value=False)
        
        # Mock the final conclusion LLM call
        original_generate = mock_llm_manager.generate_response.side_effect
        
        async def mock_generate_with_conclusion(conversation, session_id, stage_execution_id=None, **kwargs):
            interaction_type = kwargs.get('interaction_type')
            if interaction_type == LLMInteractionType.FORCED_CONCLUSION.value:
                updated_conversation = LLMConversation(messages=conversation.messages.copy())
                updated_conversation.append_assistant_message("Chat conclusion based on available data...")
                return updated_conversation
            else:
                return await original_generate(conversation, session_id, stage_execution_id, **kwargs)
        
        mock_llm_manager.generate_response.side_effect = mock_generate_with_conclusion
        
        # Execute should return forced conclusion even with setting disabled
        result = await controller.execute_analysis_loop(chat_context_obj)
        
        # Verify forced conclusion was invoked (not SessionPaused exception)
        forced_conclusion_calls = [
            call for call in mock_llm_manager.generate_response.call_args_list
            if call.kwargs.get('interaction_type') == LLMInteractionType.FORCED_CONCLUSION.value
        ]
        assert len(forced_conclusion_calls) == 1, "Expected exactly one forced conclusion call for chat context"
        
        # Verify result is non-empty (any content is acceptable)
        assert result and len(result) > 0


@pytest.mark.unit
class TestForcedConclusionExecution:
    """Test forced conclusion execution behavior."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM manager."""
        manager = AsyncMock()
        
        async def mock_generate_incomplete(conversation, session_id, stage_execution_id=None, **kwargs):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Thought: Still investigating...")
            return updated_conversation
        
        manager.generate_response = AsyncMock(side_effect=mock_generate_incomplete)
        return manager
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_standard_react_prompt.return_value = "ReAct prompt"
        builder.get_enhanced_react_system_message.return_value = "You are an AI assistant."
        builder.parse_react_response.return_value = {
            'thought': 'Investigating',
            'action': None,
            'action_input': None,
            'is_complete': False,
            'final_answer': None
        }
        builder.build_react_forced_conclusion_prompt.return_value = "Please conclude with available data."
        return builder
    
    @pytest.fixture
    def sample_context(self):
        """Create sample context."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        mock_agent = Mock()
        mock_agent.max_iterations = 1
        mock_agent.get_current_stage_execution_id.return_value = "stage-456"
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        chain_context.chat_context = None
        
        available_tools = AvailableTools(tools=[])
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
    
    @pytest.mark.asyncio
    async def test_forced_conclusion_with_successful_llm_response(
        self, mock_llm_manager, mock_prompt_builder, sample_context
    ):
        """Test forced conclusion successfully generates conclusion."""
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Configure agent with forced conclusion enabled
        sample_context.agent.get_force_conclusion = Mock(return_value=True)
        
        # Mock conclusion call
        call_count = 0
        async def mock_generate_with_conclusion(conversation, session_id, stage_execution_id=None, **kwargs):
            nonlocal call_count
            call_count += 1
            
            interaction_type = kwargs.get('interaction_type')
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            
            if interaction_type == LLMInteractionType.FORCED_CONCLUSION.value:
                updated_conversation.append_assistant_message(
                    "Based on the investigation so far, here is my conclusion: The alert indicates a potential issue."
                )
            else:
                updated_conversation.append_assistant_message("Thought: Investigating...")
            
            return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_with_conclusion
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Verify forced conclusion was invoked exactly once
        forced_conclusion_calls = [
            call for call in mock_llm_manager.generate_response.call_args_list
            if call.kwargs.get('interaction_type') == LLMInteractionType.FORCED_CONCLUSION.value
        ]
        assert len(forced_conclusion_calls) == 1, "Expected exactly one forced conclusion call"
        
        # Verify result is non-empty (any content is acceptable)
        assert result and len(result) > 0
    
    @pytest.mark.asyncio
    async def test_forced_conclusion_with_llm_timeout(
        self, mock_llm_manager, mock_prompt_builder, sample_context
    ):
        """Test graceful degradation when forced conclusion LLM call times out."""
        import asyncio
        
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Configure agent with forced conclusion enabled
        sample_context.agent.get_force_conclusion = Mock(return_value=True)
        
        # Mock settings with short timeout
        with patch('tarsy.config.settings.get_settings') as mock_settings:
            settings_mock = Mock()
            settings_mock.llm_iteration_timeout = 0.1  # Very short timeout
            mock_settings.return_value = settings_mock
            
            # Mock LLM to timeout on conclusion call
            async def mock_generate_with_timeout(conversation, session_id, stage_execution_id=None, **kwargs):
                interaction_type = kwargs.get('interaction_type')
                if interaction_type == LLMInteractionType.FORCED_CONCLUSION.value:
                    await asyncio.sleep(1)  # Longer than timeout
                    return LLMConversation(messages=conversation.messages.copy())
                else:
                    updated_conversation = LLMConversation(messages=conversation.messages.copy())
                    updated_conversation.append_assistant_message("Thought: Investigating...")
                    return updated_conversation
            
            mock_llm_manager.generate_response.side_effect = mock_generate_with_timeout
            
            result = await controller.execute_analysis_loop(sample_context)
            
            # Verify forced conclusion was attempted (even though it timed out)
            forced_conclusion_calls = [
                call for call in mock_llm_manager.generate_response.call_args_list
                if call.kwargs.get('interaction_type') == LLMInteractionType.FORCED_CONCLUSION.value
            ]
            assert len(forced_conclusion_calls) == 1, "Expected forced conclusion call to be attempted"
            
            # Verify fallback message is present (checking for graceful degradation)
            assert result and len(result) > 0, "Expected non-empty fallback message"
    
    @pytest.mark.asyncio
    async def test_forced_conclusion_with_llm_error(
        self, mock_llm_manager, mock_prompt_builder, sample_context
    ):
        """Test graceful degradation when forced conclusion LLM call fails."""
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Configure agent with forced conclusion enabled
        sample_context.agent.get_force_conclusion = Mock(return_value=True)
        
        # Mock LLM to fail on conclusion call
        async def mock_generate_with_error(conversation, session_id, stage_execution_id=None, **kwargs):
            interaction_type = kwargs.get('interaction_type')
            if interaction_type == LLMInteractionType.FORCED_CONCLUSION.value:
                raise Exception("LLM API error")
            else:
                updated_conversation = LLMConversation(messages=conversation.messages.copy())
                updated_conversation.append_assistant_message("Thought: Investigating...")
                return updated_conversation
        
        mock_llm_manager.generate_response.side_effect = mock_generate_with_error
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Verify forced conclusion was attempted (even though it errored)
        forced_conclusion_calls = [
            call for call in mock_llm_manager.generate_response.call_args_list
            if call.kwargs.get('interaction_type') == LLMInteractionType.FORCED_CONCLUSION.value
        ]
        assert len(forced_conclusion_calls) == 1, "Expected forced conclusion call to be attempted"
        
        # Verify fallback message is present (checking for graceful degradation)
        assert result and len(result) > 0, "Expected non-empty fallback message"


@pytest.mark.unit
class TestPromptDifferences:
    """Test ReAct vs Native Thinking prompt differences."""
    
    @pytest.mark.asyncio
    async def test_react_forced_conclusion_prompt(self):
        """Test ReAct controller uses ReAct-specific prompt."""
        mock_llm_manager = AsyncMock()
        mock_prompt_builder = Mock()
        mock_prompt_builder.build_react_forced_conclusion_prompt.return_value = "ReAct conclusion prompt"
        
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Call the method directly
        prompt = controller._get_forced_conclusion_prompt(5)
        
        # Verify ReAct-specific method was called
        mock_prompt_builder.build_react_forced_conclusion_prompt.assert_called_once_with(5)
        assert prompt == "ReAct conclusion prompt"
    
    @pytest.mark.asyncio
    async def test_native_thinking_forced_conclusion_prompt(self):
        """Test Native Thinking controller uses Native Thinking-specific prompt."""
        mock_llm_manager = AsyncMock()
        mock_prompt_builder = Mock()
        mock_prompt_builder.build_native_thinking_forced_conclusion_prompt.return_value = "Native thinking conclusion prompt"
        mock_prompt_builder.get_native_thinking_system_message.return_value = "System message"
        mock_prompt_builder.build_native_thinking_initial_question.return_value = "Question"
        
        controller = TestNativeThinkingController(mock_llm_manager, mock_prompt_builder)
        
        # Call the method directly
        prompt = controller._get_forced_conclusion_prompt(5)
        
        # Verify Native Thinking-specific method was called
        mock_prompt_builder.build_native_thinking_forced_conclusion_prompt.assert_called_once_with(5)
        assert prompt == "Native thinking conclusion prompt"


@pytest.mark.unit
class TestProviderConsistency:
    """Test that LLM provider is consistent between investigation and forced conclusion."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM manager that tracks provider parameter."""
        manager = AsyncMock()
        
        async def mock_generate(conversation, session_id, stage_execution_id=None, **kwargs):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            interaction_type = kwargs.get('interaction_type')
            
            if interaction_type == LLMInteractionType.FORCED_CONCLUSION.value:
                updated_conversation.append_assistant_message("Forced conclusion response")
            else:
                updated_conversation.append_assistant_message("Thought: Investigating...")
            
            return updated_conversation
        
        manager.generate_response = AsyncMock(side_effect=mock_generate)
        return manager
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.build_standard_react_prompt.return_value = "ReAct prompt"
        builder.get_enhanced_react_system_message.return_value = "You are an AI assistant."
        builder.build_react_forced_conclusion_prompt.return_value = "Please conclude now."
        return builder
    
    @pytest.fixture
    def sample_context(self):
        """Create sample context."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        mock_agent = Mock()
        mock_agent.max_iterations = 1
        mock_agent.get_current_stage_execution_id.return_value = "stage-789"
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"alert": "TestAlert"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        chain_context.chat_context = None
        
        available_tools = AvailableTools(tools=[])
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
    
    @pytest.mark.asyncio
    async def test_forced_conclusion_uses_same_provider_as_investigation(
        self, mock_llm_manager, mock_prompt_builder, sample_context
    ):
        """Test that forced conclusion uses the same LLM provider as the investigation loop."""
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Set a specific LLM provider
        test_provider = "test-provider-gpt4"
        controller.set_llm_provider(test_provider)
        
        # Configure agent with forced conclusion enabled
        sample_context.agent.get_force_conclusion = Mock(return_value=True)
        
        # Execute analysis loop (will reach max iterations and force conclusion)
        await controller.execute_analysis_loop(sample_context)
        
        # Get all calls to generate_response
        calls = mock_llm_manager.generate_response.call_args_list
        
        # Should have at least 2 calls: 1 investigation + 1 forced conclusion
        assert len(calls) >= 2
        
        # Extract provider parameter from each call
        providers_used = [call.kwargs.get('provider') for call in calls]
        
        # All calls should use the same provider
        assert all(p == test_provider for p in providers_used), \
            f"Expected all calls to use provider '{test_provider}', but got: {providers_used}"
        
        # Verify the forced conclusion call specifically
        forced_conclusion_calls = [
            call for call in calls 
            if call.kwargs.get('interaction_type') == LLMInteractionType.FORCED_CONCLUSION.value
        ]
        assert len(forced_conclusion_calls) == 1, "Should have exactly one forced conclusion call"
        assert forced_conclusion_calls[0].kwargs.get('provider') == test_provider, \
            f"Forced conclusion should use provider '{test_provider}'"
    
    @pytest.mark.asyncio
    async def test_forced_conclusion_respects_none_provider(
        self, mock_llm_manager, mock_prompt_builder, sample_context
    ):
        """Test that forced conclusion respects None provider (uses global default)."""
        controller = TestReactController(mock_llm_manager, mock_prompt_builder)
        
        # Explicitly set provider to None (use global default)
        controller.set_llm_provider(None)
        
        # Configure agent with forced conclusion enabled
        sample_context.agent.get_force_conclusion = Mock(return_value=True)
        
        # Execute analysis loop
        await controller.execute_analysis_loop(sample_context)
        
        # Get all calls to generate_response
        calls = mock_llm_manager.generate_response.call_args_list
        
        # All calls should have provider=None
        providers_used = [call.kwargs.get('provider') for call in calls]
        assert all(p is None for p in providers_used), \
            f"Expected all calls to use provider=None (global default), but got: {providers_used}"
