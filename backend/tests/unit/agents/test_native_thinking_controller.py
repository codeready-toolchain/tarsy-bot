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
from tarsy.models.constants import IterationStrategy
from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType
from tarsy.models.processing_context import AvailableTools, ChainContext, StageContext, ToolWithServer
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
        """Create mock LLM manager that returns Google client."""
        manager = Mock()
        manager.get_client.return_value = mock_llm_client_google
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
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        from mcp.types import Tool
        
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
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_init_with_google_provider(self, mock_native_client_cls, mock_llm_manager_google, mock_llm_client_google, mock_prompt_builder):
        """Test controller initialization with Google provider succeeds."""
        controller = NativeThinkingController(mock_llm_manager_google, mock_prompt_builder)
        
        assert controller.llm_manager == mock_llm_manager_google
        assert controller._native_client == mock_native_client_cls.return_value
        assert controller.prompt_builder == mock_prompt_builder
        # Verify native client was created with correct config
        mock_native_client_cls.assert_called_once_with(
            mock_llm_client_google.config,
            provider_name=mock_llm_client_google.provider_name
        )
    
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
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    async def test_execute_analysis_loop_final_answer(
        self, mock_native_client_cls, mock_llm_manager_google, mock_llm_client_google, mock_prompt_builder, sample_context
    ):
        """Test successful analysis loop with final answer."""
        # Setup mock for the native thinking client
        mock_native_client = Mock()
        mock_native_client_cls.return_value = mock_native_client
        
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
        
        # Verify native thinking client was created with correct config
        mock_native_client_cls.assert_called_once_with(
            mock_llm_client_google.config,
            provider_name=mock_llm_client_google.provider_name
        )
        
        # Verify generate was called
        mock_native_client.generate.assert_called_once()
        
        # Verify MCP tools were passed
        call_args = mock_native_client.generate.call_args
        assert len(call_args.kwargs['mcp_tools']) == 1
        assert call_args.kwargs['thinking_level'] == "high"
    
    @pytest.mark.asyncio
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    async def test_execute_analysis_loop_with_tool_calls(
        self, mock_native_client_cls, mock_llm_manager_google, mock_llm_client_google, mock_prompt_builder, sample_context
    ):
        """Test analysis loop with tool calls followed by final answer."""
        # Setup mock for the native thinking client
        mock_native_client = Mock()
        mock_native_client_cls.return_value = mock_native_client
        
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

