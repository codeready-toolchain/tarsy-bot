"""
Unit tests for NativeThinkingController.

Tests the Gemini-specific native thinking iteration controller that uses
native function calling instead of text-based ReAct parsing.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.iteration_controllers.native_thinking_controller import (
    NativeThinkingController,
)
from tarsy.integrations.llm.gemini_client import (
    NativeThinkingResponse,
    NativeThinkingToolCall,
)
from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType
from tarsy.models.processing_context import (
    AvailableTools,
    ChainContext,
    StageContext,
    ToolWithServer,
)
from tarsy.models.unified_interactions import LLMConversation


@pytest.mark.unit
class TestNativeThinkingController:
    """Test NativeThinkingController implementation."""
    
    @pytest.fixture
    def mock_google_config(self):
        """Create mock Google/Gemini LLM config."""
        config = Mock(spec=LLMProviderConfig)
        config.type = LLMProviderType.GOOGLE
        config.model = "gemini-3.0-pro"
        config.get_native_tool_status.return_value = True
        return config
    
    @pytest.fixture
    def mock_non_google_config(self):
        """Create mock non-Google LLM config."""
        config = Mock(spec=LLMProviderConfig)
        config.type = LLMProviderType.OPENAI
        config.model = "gpt-4"
        return config
    
    @pytest.fixture
    def mock_llm_client_google(self, mock_google_config):
        """Create mock LLM client with Google provider."""
        client = Mock()
        client.config = mock_google_config
        return client
    
    @pytest.fixture
    def mock_llm_manager_google(self, mock_llm_client_google):
        """Create mock LLM manager that returns Google client and native thinking client."""
        manager = Mock()
        manager.get_client.return_value = mock_llm_client_google
        # Mock get_native_thinking_client to return a valid native thinking client
        mock_native_client = Mock()
        manager.get_native_thinking_client.return_value = mock_native_client
        return manager
    
    @pytest.fixture
    def mock_llm_client_non_google(self, mock_non_google_config):
        """Create mock LLM client with non-Google provider."""
        client = Mock()
        client.config = mock_non_google_config
        return client
    
    @pytest.fixture
    def mock_llm_manager_non_google(self, mock_llm_client_non_google):
        """Create mock LLM manager that returns non-Google client."""
        manager = Mock()
        manager.get_client.return_value = mock_llm_client_non_google
        # Non-Google provider returns None for native thinking client
        manager.get_native_thinking_client.return_value = None
        return manager
    
    @pytest.fixture
    def mock_prompt_builder(self):
        """Create mock prompt builder."""
        builder = Mock()
        builder.get_native_thinking_system_message.return_value = (
            "You are an SRE agent analyzing incidents."
        )
        builder.build_native_thinking_prompt.return_value = (
            "Analyze this alert and provide recommendations."
        )
        return builder
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for testing."""
        agent = Mock()
        agent.max_iterations = 5
        agent.get_current_stage_execution_id.return_value = "stage-exec-123"
        agent.execute_mcp_tools = AsyncMock(return_value={
            "kubernetes-server": [{"tool": "resources_get", "result": {"status": "Running"}}]
        })
        agent._compose_instructions.return_value = "Agent instructions"
        return agent
    
    @pytest.fixture
    def sample_context(self, mock_agent):
        """Create sample stage context."""
        from mcp.types import Tool

        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "test-pod", "namespace": "default"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="investigation"
        )
        
        # Create mock MCP tools
        mock_tool = Tool(
            name="resources_get",
            description="Get Kubernetes resources",
            inputSchema={"type": "object", "properties": {"namespace": {"type": "string"}}}
        )
        available_tools = AvailableTools(tools=[
            ToolWithServer(server="kubernetes-server", tool=mock_tool)
        ])
        
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
    
    def test_init_with_google_provider(self, mock_llm_manager_google, mock_prompt_builder):
        """Test controller initialization with Google provider succeeds."""
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        assert controller.llm_manager == mock_llm_manager_google
        assert controller.prompt_builder == mock_prompt_builder
    
    def test_init_with_non_google_provider_raises(self, mock_llm_manager_non_google, mock_prompt_builder):
        """Test controller initialization with non-Google provider raises ValueError."""
        with pytest.raises(ValueError, match="requires Google/Gemini provider"):
            NativeThinkingController(mock_llm_manager_non_google, mock_prompt_builder)
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_needs_mcp_tools_returns_true(self, mock_native_client_cls, mock_llm_manager_google, mock_prompt_builder):
        """Test that controller indicates it needs MCP tools."""
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        assert controller.needs_mcp_tools() is True
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_final_answer(
        self, mock_llm_manager_google, mock_prompt_builder, sample_context
    ):
        """Test successful analysis loop with final answer."""
        # Setup mock native client via LLM manager
        mock_native_client = mock_llm_manager_google.get_native_thinking_client.return_value
        
        async def mock_generate(conversation, session_id, mcp_tools, **kwargs):
            return NativeThinkingResponse(
                content="Analysis complete. Root cause identified.",
                conversation=conversation,
                thinking_content="Let me analyze this alert...",
                tool_calls=[],
                thought_signature="encrypted_signature_123",
                is_final=True
            )
        
        mock_native_client.generate = AsyncMock(side_effect=mock_generate)
        
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return the content from the response
        assert "Analysis complete" in result
        
        # Verify generate was called
        mock_native_client.generate.assert_called_once()
        
        # Verify MCP tools were passed
        call_args = mock_native_client.generate.call_args
        assert len(call_args.kwargs['mcp_tools']) == 1
        assert call_args.kwargs['thinking_level'] == "high"
    
    @pytest.mark.asyncio
    async def test_execute_analysis_loop_with_tool_calls(
        self, mock_llm_manager_google, mock_prompt_builder, sample_context
    ):
        """Test analysis loop with tool calls followed by final answer."""
        # Setup mock native client via LLM manager
        mock_native_client = mock_llm_manager_google.get_native_thinking_client.return_value
        
        # First response has tool calls
        response_with_tool = NativeThinkingResponse(
            content="I need to check the pod status.",
            conversation=LLMConversation(messages=[
                {"role": "system", "content": "System"},
                {"role": "user", "content": "Analyze"},
                {"role": "assistant", "content": "I need to check the pod status."}
            ]),
            thinking_content="Analyzing the alert...",
            tool_calls=[
                NativeThinkingToolCall(
                    server="kubernetes-server",
                    tool="resources_get",
                    parameters={"namespace": "default"}
                )
            ],
            thought_signature="sig_1",
            is_final=False
        )
        
        # Second response is final
        response_final = NativeThinkingResponse(
            content="Root cause: Memory limit exceeded.",
            conversation=LLMConversation(messages=[
                {"role": "system", "content": "System"},
                {"role": "user", "content": "Analyze"},
                {"role": "assistant", "content": "I need to check the pod status."},
                {"role": "user", "content": "Tool Result: status=Running"},
                {"role": "assistant", "content": "Root cause: Memory limit exceeded."}
            ]),
            thinking_content="Based on the data...",
            tool_calls=[],
            thought_signature="sig_2",
            is_final=True
        )
        
        mock_native_client.generate = AsyncMock(
            side_effect=[response_with_tool, response_final]
        )
        
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        result = await controller.execute_analysis_loop(sample_context)
        
        # Should return final content
        assert "Root cause" in result
        
        # Should have called LLM twice on the native client
        assert mock_native_client.generate.call_count == 2
        
        # Should have executed tools
        sample_context.agent.execute_mcp_tools.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    async def test_execute_analysis_loop_no_agent_raises(
        self, mock_native_client_cls, mock_llm_manager_google, mock_prompt_builder
    ):
        """Test that missing agent reference raises ValueError."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "test"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        context = StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=None
        )
        
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        with pytest.raises(ValueError, match="Agent reference is required"):
            await controller.execute_analysis_loop(context)
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_extract_final_analysis(self, mock_native_client_cls, mock_llm_manager_google, mock_prompt_builder, sample_context):
        """Test final analysis extraction returns content as-is."""
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        result = controller.extract_final_analysis(
            "Root cause: Pod crashed due to OOM.",
            sample_context
        )
        
        assert result == "Root cause: Pod crashed due to OOM."
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_extract_final_analysis_empty(self, mock_native_client_cls, mock_llm_manager_google, mock_prompt_builder, sample_context):
        """Test final analysis extraction with empty content."""
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        result = controller.extract_final_analysis("", sample_context)
        
        assert result == "No analysis generated"
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_create_result_summary(self, mock_native_client_cls, mock_llm_manager_google, mock_prompt_builder, sample_context):
        """Test result summary creation."""
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        result = controller.create_result_summary(
            "Analysis content here.",
            sample_context
        )
        
        assert "## Analysis Result" in result
        assert "Analysis content here." in result
    
    @pytest.mark.asyncio
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.get_settings')
    async def test_consecutive_tool_timeouts_fail_immediately(
        self, mock_get_settings, mock_llm_manager_google, mock_prompt_builder, mock_agent, sample_context
    ):
        """Test that 2 consecutive tool timeouts cause immediate failure."""
        # Setup
        mock_settings = Mock()
        mock_settings.llm_iteration_timeout = 210
        mock_get_settings.return_value = mock_settings
        
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        # Mock native client
        mock_native_client = Mock()
        
        # Create responses that will trigger tool calls
        def create_tool_response(idx):
            response = Mock(spec=['has_tool_calls', 'tool_calls', 'is_final', 'thinking_content',
                                 'thought_signature', 'conversation', 'content'])
            response.has_tool_calls = True
            response.is_final = False
            response.thinking_content = f"Thinking {idx}"
            response.thought_signature = f"sig{idx}".encode()
            response.conversation = Mock(spec=['messages', 'append_observation'])
            response.conversation.messages = []
            response.content = f"Using tool {idx}"
            
            tool_call = Mock()
            tool_call.server = "kubernetes"
            tool_call.tool = f"tool_{idx}"
            tool_call.parameters = {}
            response.tool_calls = [tool_call]
            return response
        
        # Create multiple responses (more than we'll need)
        responses = [create_tool_response(i) for i in range(5)]
        mock_native_client.generate = AsyncMock(side_effect=responses)
        mock_llm_manager_google.get_native_thinking_client.return_value = mock_native_client
        
        # Mock agent's execute_mcp_tools to raise timeout errors consistently
        async def timeout_tool(*args, **kwargs):
            raise TimeoutError("Tool call exceeded 70s timeout")
        
        mock_agent.execute_mcp_tools = AsyncMock(side_effect=timeout_tool)
        sample_context.agent = mock_agent
        
        # Execute and verify it fails after 2 consecutive timeouts
        with pytest.raises(Exception) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        assert "consecutive tool timeout failures" in str(exc_info.value).lower()
        
        # Verify we made exactly 2 LLM calls (one for each timeout, then stopped immediately)
        assert mock_native_client.generate.call_count == 2
    
    @pytest.mark.asyncio
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.get_settings')
    async def test_timeout_counter_resets_on_non_timeout_error(
        self, mock_get_settings, mock_llm_manager_google, mock_prompt_builder, mock_agent, sample_context
    ):
        """Test that consecutive timeout counter resets on non-timeout errors."""
        # Setup
        mock_settings = Mock()
        mock_settings.llm_iteration_timeout = 210
        mock_get_settings.return_value = mock_settings
        
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        # Mock native client
        mock_native_client = Mock()
        
        # Create enough responses for the test scenario
        responses = []
        for i in range(10):
            response = Mock(spec=['has_tool_calls', 'tool_calls', 'is_final', 'thinking_content',
                                 'thought_signature', 'conversation', 'content'])
            response.has_tool_calls = True
            response.is_final = False
            response.thinking_content = f"Thinking {i}"
            response.thought_signature = f"sig{i}".encode()
            response.conversation = Mock(spec=['messages', 'append_observation'])
            response.conversation.messages = []
            response.content = f"Using tool {i}"
            
            tool_call = Mock()
            tool_call.server = "kubernetes"
            tool_call.tool = f"tool_{i}"
            tool_call.parameters = {}
            response.tool_calls = [tool_call]
            responses.append(response)
        
        mock_native_client.generate = AsyncMock(side_effect=responses)
        mock_llm_manager_google.get_native_thinking_client.return_value = mock_native_client
        
        # Mock tool execution: timeout, non-timeout error (resets), timeout, timeout (fails)
        call_count = [0]
        
        async def varying_tool_results(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise TimeoutError("First timeout")
            elif call_count[0] == 2:
                # Different error type resets the counter (don't use word "timeout" in message!)
                raise ValueError("Different error type resets counter")
            elif call_count[0] == 3:
                raise TimeoutError("Third call first after reset")
            elif call_count[0] == 4:
                raise TimeoutError("Fourth call second consecutive should fail")
            else:
                return {"kubernetes": [{"tool": "test", "result": "success"}]}
        
        mock_agent.execute_mcp_tools = AsyncMock(side_effect=varying_tool_results)
        sample_context.agent = mock_agent
        
        # This should fail on the 4th call (2nd consecutive timeout after counter reset)
        with pytest.raises(Exception) as exc_info:
            await controller.execute_analysis_loop(sample_context)
        
        assert "consecutive tool timeout failures" in str(exc_info.value).lower()
        # Should have stopped after 4th tool call (4 LLM calls)
        assert mock_native_client.generate.call_count == 4

