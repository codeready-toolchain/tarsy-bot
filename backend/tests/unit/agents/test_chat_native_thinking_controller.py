"""
Unit tests for ChatNativeThinkingController.

Tests the native thinking iteration controller for chat conversations,
which builds initial conversation with historical context from completed
investigations.
"""
from unittest.mock import MagicMock, Mock, patch

import pytest

from tarsy.agents.iteration_controllers.chat_native_thinking_controller import (
    ChatNativeThinkingController,
)
from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType
from tarsy.models.processing_context import (
    AvailableTools,
    ChainContext,
    ChatMessageContext,
    StageContext,
)
from tarsy.models.unified_interactions import MessageRole


@pytest.mark.unit
class TestChatNativeThinkingControllerInit:
    """Tests for ChatNativeThinkingController initialization."""
    
    @pytest.fixture
    def mock_google_config(self) -> Mock:
        """Create mock Google/Gemini LLM config."""
        config = Mock(spec=LLMProviderConfig)
        config.type = LLMProviderType.GOOGLE
        config.model = "gemini-2.5-pro"
        config.get_native_tool_status.return_value = True
        return config
    
    @pytest.fixture
    def mock_llm_client_google(self, mock_google_config: Mock) -> Mock:
        """Create mock LLM client with Google provider."""
        client = Mock()
        client.config = mock_google_config
        client.provider_name = "test-gemini"
        return client
    
    @pytest.fixture
    def mock_llm_manager_google(self, mock_llm_client_google: Mock) -> Mock:
        """Create mock LLM manager that returns Google client."""
        manager = Mock()
        manager.get_client.return_value = mock_llm_client_google
        return manager
    
    @pytest.fixture
    def mock_prompt_builder(self) -> Mock:
        """Create mock prompt builder."""
        builder = Mock()
        builder.get_native_thinking_system_message.return_value = (
            "You are an SRE agent answering follow-up questions."
        )
        builder.build_chat_user_message.return_value = (
            "Based on the investigation, here is the user's question: What was the root cause?"
        )
        return builder
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_init_creates_controller(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager_google: Mock,
        mock_prompt_builder: Mock
    ) -> None:
        """Test that ChatNativeThinkingController initializes correctly."""
        controller = ChatNativeThinkingController(
            mock_llm_manager_google, 
            mock_prompt_builder
        )
        
        assert controller.llm_manager == mock_llm_manager_google
        assert controller.prompt_builder == mock_prompt_builder
        # Native client created via parent class
        mock_native_client_cls.assert_called_once()
        
    def test_init_with_non_google_provider_raises(
        self,
        mock_prompt_builder: Mock
    ) -> None:
        """Test initialization fails with non-Google provider."""
        non_google_config = Mock(spec=LLMProviderConfig)
        non_google_config.type = LLMProviderType.OPENAI
        non_google_config.model = "gpt-4"
        
        non_google_client = Mock()
        non_google_client.config = non_google_config
        
        manager = Mock()
        manager.get_client.return_value = non_google_client
        
        with pytest.raises(ValueError, match="requires Google/Gemini provider"):
            ChatNativeThinkingController(manager, mock_prompt_builder)


@pytest.mark.unit
class TestChatNativeThinkingControllerBuildInitialConversation:
    """Tests for _build_initial_conversation method."""
    
    @pytest.fixture
    def mock_google_config(self) -> Mock:
        """Create mock Google/Gemini LLM config."""
        config = Mock(spec=LLMProviderConfig)
        config.type = LLMProviderType.GOOGLE
        config.model = "gemini-2.5-pro"
        config.get_native_tool_status.return_value = True
        return config
    
    @pytest.fixture
    def mock_llm_manager(self, mock_google_config: Mock) -> Mock:
        """Create mock LLM manager."""
        client = Mock()
        client.config = mock_google_config
        client.provider_name = "gemini"
        manager = Mock()
        manager.get_client.return_value = client
        return manager
    
    @pytest.fixture
    def mock_prompt_builder(self) -> Mock:
        """Create mock prompt builder."""
        builder = Mock()
        builder.get_native_thinking_system_message.return_value = (
            "You are an expert SRE assistant with access to investigation tools."
        )
        builder.build_chat_user_message.return_value = (
            "## Investigation Summary\n\nPod crashed due to OOM.\n\n"
            "## User Question\n\nWhat should we do next?"
        )
        return builder
    
    @pytest.fixture
    def mock_agent(self) -> Mock:
        """Create mock agent."""
        agent = Mock()
        agent._compose_instructions.return_value = "Agent instructions for SRE work."
        agent.max_iterations = 5
        agent.get_current_stage_execution_id.return_value = "stage-123"
        return agent
    
    @pytest.fixture
    def context_with_chat(self, mock_agent: Mock) -> StageContext:
        """Create StageContext with chat_context populated."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "test-pod", "namespace": "default"}
        )
        
        # Create ChainContext with chat_context
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="chat"
        )
        
        # Add chat context
        chain_context.chat_context = ChatMessageContext(
            conversation_history="Previous investigation found pod crashed due to OOM.",
            user_question="What should we do next?",
            chat_id="chat-456"
        )
        
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
    
    @pytest.fixture
    def context_without_chat(self, mock_agent: Mock) -> StageContext:
        """Create StageContext without chat_context."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="staging",
            alert_data={"message": "Test alert"}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-no-chat",
            current_stage_name="investigation"
        )
        # Note: chat_context is None by default
        
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=mock_agent
        )
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_build_initial_conversation_with_chat_context(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock,
        mock_prompt_builder: Mock,
        context_with_chat: StageContext
    ) -> None:
        """Test building initial conversation with valid chat context."""
        controller = ChatNativeThinkingController(
            mock_llm_manager,
            mock_prompt_builder
        )
        
        conversation = controller._build_initial_conversation(context_with_chat)
        
        # Should have system and user messages
        assert len(conversation.messages) == 2
        
        # First message is system
        assert conversation.messages[0].role == MessageRole.SYSTEM
        assert "expert SRE assistant" in conversation.messages[0].content
        
        # Second message is user with chat context
        assert conversation.messages[1].role == MessageRole.USER
        assert "Investigation Summary" in conversation.messages[1].content
        assert "User Question" in conversation.messages[1].content
        
        # Verify prompt builder was called with correct args
        mock_prompt_builder.get_native_thinking_system_message.assert_called_once()
        mock_prompt_builder.build_chat_user_message.assert_called_once_with(
            investigation_context="Previous investigation found pod crashed due to OOM.",
            user_question="What should we do next?"
        )
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_build_initial_conversation_without_chat_context_raises(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock,
        mock_prompt_builder: Mock,
        context_without_chat: StageContext
    ) -> None:
        """Test that missing chat context raises ValueError."""
        controller = ChatNativeThinkingController(
            mock_llm_manager,
            mock_prompt_builder
        )
        
        with pytest.raises(ValueError, match="Chat context missing"):
            controller._build_initial_conversation(context_without_chat)
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_build_initial_conversation_uses_agent_instructions(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock,
        mock_prompt_builder: Mock,
        context_with_chat: StageContext
    ) -> None:
        """Test that agent instructions are passed to prompt builder."""
        controller = ChatNativeThinkingController(
            mock_llm_manager,
            mock_prompt_builder
        )
        
        controller._build_initial_conversation(context_with_chat)
        
        # Verify agent's _compose_instructions was called
        context_with_chat.agent._compose_instructions.assert_called_once()
        
        # Verify prompt builder received the instructions
        call_args = mock_prompt_builder.get_native_thinking_system_message.call_args
        assert call_args[0][0] == "Agent instructions for SRE work."
        assert "follow-up questions" in call_args[0][1]


@pytest.mark.unit
class TestChatNativeThinkingControllerExtractFinalAnalysis:
    """Tests for extract_final_analysis method."""
    
    @pytest.fixture
    def mock_google_config(self) -> Mock:
        """Create mock Google/Gemini LLM config."""
        config = Mock(spec=LLMProviderConfig)
        config.type = LLMProviderType.GOOGLE
        config.model = "gemini-2.5-pro"
        config.get_native_tool_status.return_value = True
        return config
    
    @pytest.fixture
    def mock_llm_manager(self, mock_google_config: Mock) -> Mock:
        """Create mock LLM manager."""
        client = Mock()
        client.config = mock_google_config
        client.provider_name = "gemini"
        manager = Mock()
        manager.get_client.return_value = client
        return manager
    
    @pytest.fixture
    def mock_prompt_builder(self) -> Mock:
        """Create mock prompt builder."""
        return Mock()
    
    @pytest.fixture
    def sample_context(self) -> StageContext:
        """Create a sample context for testing."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="info",
            timestamp=now_us(),
            environment="test",
            alert_data={}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="chat"
        )
        
        return StageContext(
            chain_context=chain_context,
            available_tools=AvailableTools(tools=[]),
            agent=None
        )
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_extract_final_analysis_returns_content(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock,
        mock_prompt_builder: Mock,
        sample_context: StageContext
    ) -> None:
        """Test that extract_final_analysis returns the analysis result as-is."""
        controller = ChatNativeThinkingController(
            mock_llm_manager,
            mock_prompt_builder
        )
        
        analysis = "The root cause was memory exhaustion. Increase pod memory limits."
        
        result = controller.extract_final_analysis(analysis, sample_context)
        
        assert result == analysis
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_extract_final_analysis_empty_returns_default(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock,
        mock_prompt_builder: Mock,
        sample_context: StageContext
    ) -> None:
        """Test that empty analysis result returns default message."""
        controller = ChatNativeThinkingController(
            mock_llm_manager,
            mock_prompt_builder
        )
        
        result = controller.extract_final_analysis("", sample_context)
        
        assert result == "No response generated"
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_extract_final_analysis_none_returns_default(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock,
        mock_prompt_builder: Mock,
        sample_context: StageContext
    ) -> None:
        """Test that None analysis result returns default message."""
        controller = ChatNativeThinkingController(
            mock_llm_manager,
            mock_prompt_builder
        )
        
        # Simulating falsy input
        result = controller.extract_final_analysis(None, sample_context)  # type: ignore
        
        assert result == "No response generated"
    
    @pytest.mark.parametrize(
        "analysis_result,expected_output",
        [
            ("Simple response", "Simple response"),
            ("Multi\nline\nresponse", "Multi\nline\nresponse"),
            ("  Whitespace preserved  ", "  Whitespace preserved  "),
            ("Special chars: <>&\"'", "Special chars: <>&\"'"),
        ],
    )
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_extract_final_analysis_preserves_content(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock,
        mock_prompt_builder: Mock,
        sample_context: StageContext,
        analysis_result: str,
        expected_output: str
    ) -> None:
        """Test that various content types are preserved correctly."""
        controller = ChatNativeThinkingController(
            mock_llm_manager,
            mock_prompt_builder
        )
        
        result = controller.extract_final_analysis(analysis_result, sample_context)
        
        assert result == expected_output


@pytest.mark.unit
class TestChatNativeThinkingControllerNeedsMcpTools:
    """Tests for needs_mcp_tools method."""
    
    @pytest.fixture
    def mock_google_config(self) -> Mock:
        """Create mock Google/Gemini LLM config."""
        config = Mock(spec=LLMProviderConfig)
        config.type = LLMProviderType.GOOGLE
        config.model = "gemini-2.5-pro"
        config.get_native_tool_status.return_value = True
        return config
    
    @pytest.fixture
    def mock_llm_manager(self, mock_google_config: Mock) -> Mock:
        """Create mock LLM manager."""
        client = Mock()
        client.config = mock_google_config
        client.provider_name = "gemini"
        manager = Mock()
        manager.get_client.return_value = client
        return manager
    
    @patch('tarsy.agents.iteration_controllers.native_thinking_controller.GeminiNativeThinkingClient')
    def test_needs_mcp_tools_returns_true(
        self,
        mock_native_client_cls: MagicMock,
        mock_llm_manager: Mock
    ) -> None:
        """Test that controller indicates it needs MCP tools."""
        controller = ChatNativeThinkingController(mock_llm_manager, Mock())
        
        assert controller.needs_mcp_tools() is True

