"""
Unit tests for GeminiNativeThinkingClient.

Tests the native thinking and function calling capabilities for Gemini models.
"""

from typing import AsyncIterator, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types as google_genai_types
from mcp.types import Tool

from tarsy.integrations.llm.gemini_client import (
    GeminiNativeThinkingClient,
    NativeThinkingResponse,
    NativeThinkingToolCall,
)
from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType
from tarsy.models.mcp_selection_models import NativeToolsConfig
from tarsy.models.processing_context import ToolWithServer
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


async def mock_stream_response(response: MagicMock) -> AsyncIterator[MagicMock]:
    """
    Convert a mock response to an async iterator for streaming simulation.

    The streaming API yields the entire response as a single chunk for test simplicity.
    """
    yield response


@pytest.mark.unit
class TestNativeThinkingToolCall:
    """Tests for NativeThinkingToolCall dataclass."""

    def test_default_parameters_is_empty_dict(self) -> None:
        """Test that default parameters is an empty dictionary."""
        tool_call = NativeThinkingToolCall(server="test", tool="test_tool")

        assert tool_call.parameters == {}

    def test_with_parameters(self) -> None:
        """Test creating tool call with parameters."""
        params = {"namespace": "default", "limit": 10}
        tool_call = NativeThinkingToolCall(
            server="kubernetes", tool="get_pods", parameters=params
        )

        assert tool_call.server == "kubernetes"
        assert tool_call.tool == "get_pods"
        assert tool_call.parameters == params


@pytest.mark.unit
class TestNativeThinkingResponse:
    """Tests for NativeThinkingResponse dataclass."""

    @pytest.fixture
    def sample_conversation(self) -> LLMConversation:
        """Create a sample conversation for testing."""
        return LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are an assistant."),
                LLMMessage(role=MessageRole.USER, content="Analyze this alert."),
            ]
        )

    def test_has_tool_calls_true_when_tools_present(
        self, sample_conversation: LLMConversation
    ) -> None:
        """Test has_tool_calls returns True when tool_calls list is not empty."""
        response = NativeThinkingResponse(
            content="I need to check the status.",
            conversation=sample_conversation,
            tool_calls=[
                NativeThinkingToolCall(server="k8s", tool="get_pods", parameters={})
            ],
        )

        assert response.has_tool_calls is True

    def test_has_tool_calls_false_when_empty(
        self, sample_conversation: LLMConversation
    ) -> None:
        """Test has_tool_calls returns False when tool_calls list is empty."""
        response = NativeThinkingResponse(
            content="Analysis complete.",
            conversation=sample_conversation,
            tool_calls=[],
        )

        assert response.has_tool_calls is False

    def test_defaults(self, sample_conversation: LLMConversation) -> None:
        """Test default values for optional fields."""
        response = NativeThinkingResponse(
            content="Test content", conversation=sample_conversation
        )

        assert response.thinking_content is None
        assert response.tool_calls == []
        assert response.thought_signature is None
        assert response.is_final is False


@pytest.mark.unit
class TestGeminiNativeThinkingClientInit:
    """Tests for GeminiNativeThinkingClient initialization."""

    @patch('tarsy.integrations.llm.gemini_client.genai.Client')
    def test_init_with_google_provider_succeeds(self, mock_genai_client: MagicMock) -> None:
        """Test that initialization with Google provider succeeds."""
        config = LLMProviderConfig(
            type=LLMProviderType.GOOGLE,
            model="gemini-2.5-pro",
            api_key_env="GOOGLE_API_KEY",
            api_key="test-api-key",
            temperature=0.7,
        )

        client = GeminiNativeThinkingClient(config, provider_name="custom-provider")

        assert client.config == config
        assert client.model == "gemini-2.5-pro"
        assert client.temperature == 0.7
        assert client.provider_name == "custom-provider"

    @patch('tarsy.integrations.llm.gemini_client.genai.Client')
    def test_init_without_provider_name_uses_model(self, mock_genai_client: MagicMock) -> None:
        """Test that provider_name defaults to model name when not specified."""
        config = LLMProviderConfig(
            type=LLMProviderType.GOOGLE,
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            api_key="test-api-key",
        )

        client = GeminiNativeThinkingClient(config)

        assert client.provider_name == "gemini-2.5-flash"

    def test_init_with_non_google_provider_raises_valueerror(self) -> None:
        """Test that initialization with non-Google provider raises ValueError."""
        config = LLMProviderConfig(
            type=LLMProviderType.OPENAI,
            model="gpt-4",
            api_key_env="OPENAI_API_KEY",
            api_key="test-api-key",
        )

        with pytest.raises(ValueError, match="requires Google provider"):
            GeminiNativeThinkingClient(config)

    @pytest.mark.parametrize(
        "provider_type,api_key_env,expected_error",
        [
            (
                LLMProviderType.OPENAI,
                "OPENAI_API_KEY",
                "requires Google provider, got openai",
            ),
            (LLMProviderType.XAI, "XAI_API_KEY", "requires Google provider, got xai"),
        ],
    )
    def test_init_rejects_non_google_providers(
        self, provider_type: LLMProviderType, api_key_env: str, expected_error: str
    ) -> None:
        """Test that all non-Google provider types are rejected."""
        config = LLMProviderConfig(
            type=provider_type,
            model="some-model",
            api_key_env=api_key_env,
            api_key="test-key",
        )

        with pytest.raises(ValueError, match=expected_error):
            GeminiNativeThinkingClient(config)


@pytest.mark.unit
class TestGeminiNativeThinkingClientParseFunctionName:
    """Tests for _parse_function_name method."""

    @pytest.fixture
    def client(self) -> GeminiNativeThinkingClient:
        """Create a GeminiNativeThinkingClient for testing."""
        with patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-pro",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-key",
            )
            return GeminiNativeThinkingClient(config)

    @pytest.mark.parametrize(
        "func_name,expected_server,expected_tool",
        [
            ("kubernetes__get_pods", "kubernetes", "get_pods"),
            ("db__query_select", "db", "query_select"),
            ("server__tool__with__underscores", "server", "tool__with__underscores"),
            ("a__b", "a", "b"),
        ],
    )
    def test_parse_valid_function_names(
        self,
        client: GeminiNativeThinkingClient,
        func_name: str,
        expected_server: str,
        expected_tool: str,
    ) -> None:
        """Test parsing valid function names with double underscore separator."""
        server, tool = client._parse_function_name(func_name)

        assert server == expected_server
        assert tool == expected_tool

    @pytest.mark.parametrize(
        "invalid_func_name",
        [
            "no_separator",
            "single_underscore",
            "",
            "nounderscores",
        ],
    )
    def test_parse_invalid_function_name_raises_valueerror(
        self, client: GeminiNativeThinkingClient, invalid_func_name: str
    ) -> None:
        """Test that invalid function names (without __) raise ValueError."""
        with pytest.raises(ValueError, match="Invalid function name format"):
            client._parse_function_name(invalid_func_name)


@pytest.mark.unit
class TestGeminiNativeThinkingClientConvertMCPTools:
    """Tests for _convert_mcp_tools_to_functions method."""

    @pytest.fixture
    def client(self) -> GeminiNativeThinkingClient:
        """Create a GeminiNativeThinkingClient for testing."""
        with patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-pro",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-key",
            )
            return GeminiNativeThinkingClient(config)

    @pytest.fixture
    def sample_mcp_tools(self) -> List[ToolWithServer]:
        """Create sample MCP tools for testing."""
        tool1 = Tool(
            name="get_pods",
            description="Get Kubernetes pods",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "label_selector": {"type": "string"},
                },
                "required": ["namespace"],
            },
        )

        tool2 = Tool(
            name="query",
            description="Execute database query",
            inputSchema={"type": "object", "properties": {"sql": {"type": "string"}}},
        )

        return [
            ToolWithServer(server="kubernetes", tool=tool1),
            ToolWithServer(server="database", tool=tool2),
        ]

    def test_convert_mcp_tools_creates_function_declarations(
        self, client: GeminiNativeThinkingClient, sample_mcp_tools: List[ToolWithServer]
    ) -> None:
        """Test that MCP tools are converted to Google FunctionDeclarations."""
        functions = client._convert_mcp_tools_to_functions(sample_mcp_tools)

        assert len(functions) == 2

        # Check first function
        assert functions[0].name == "kubernetes__get_pods"
        assert functions[0].description == "Get Kubernetes pods"

        # Check second function
        assert functions[1].name == "database__query"
        assert functions[1].description == "Execute database query"

    def test_convert_empty_tools_list(self, client: GeminiNativeThinkingClient) -> None:
        """Test converting empty tools list returns empty list."""
        functions = client._convert_mcp_tools_to_functions([])

        assert functions == []

    def test_convert_tool_without_description_uses_default(
        self, client: GeminiNativeThinkingClient
    ) -> None:
        """Test that tools without description get a default description."""
        tool = Tool(
            name="mystery_tool", inputSchema={"type": "object", "properties": {}}
        )
        tools = [ToolWithServer(server="myserver", tool=tool)]

        functions = client._convert_mcp_tools_to_functions(tools)

        assert len(functions) == 1
        assert "mystery_tool" in functions[0].description
        assert "myserver" in functions[0].description

    def test_convert_tool_with_empty_input_schema(
        self, client: GeminiNativeThinkingClient
    ) -> None:
        """Test that tools with minimal inputSchema are handled correctly."""
        tool = Tool(
            name="simple_tool",
            description="A simple tool",
            inputSchema={"type": "object", "properties": {}},
        )
        tools = [ToolWithServer(server="simple", tool=tool)]

        functions = client._convert_mcp_tools_to_functions(tools)

        assert len(functions) == 1
        assert functions[0].name == "simple__simple_tool"


@pytest.mark.unit
class TestGeminiNativeThinkingClientConvertConversation:
    """Tests for _convert_conversation_to_native_format method."""

    @pytest.fixture
    def client(self) -> GeminiNativeThinkingClient:
        """Create a GeminiNativeThinkingClient for testing."""
        with patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-pro",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-key",
            )
            return GeminiNativeThinkingClient(config)

    def test_convert_system_message(self, client: GeminiNativeThinkingClient) -> None:
        """Test that SYSTEM messages are converted to user role with prefix."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are an SRE agent.")
            ]
        )

        contents = client._convert_conversation_to_native_format(conversation)

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert "[System Instructions]" in contents[0].parts[0].text
        assert "You are an SRE agent." in contents[0].parts[0].text

    def test_convert_user_message(self, client: GeminiNativeThinkingClient) -> None:
        """Test that USER messages are converted correctly."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System prompt."),
                LLMMessage(role=MessageRole.USER, content="Analyze this alert."),
            ]
        )

        contents = client._convert_conversation_to_native_format(conversation)

        assert len(contents) == 2
        # Second content is the user message
        assert contents[1].role == "user"
        assert contents[1].parts[0].text == "Analyze this alert."

    def test_convert_assistant_message(
        self, client: GeminiNativeThinkingClient
    ) -> None:
        """Test that ASSISTANT messages are converted to model role."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System prompt."),
                LLMMessage(role=MessageRole.ASSISTANT, content="I will investigate."),
            ]
        )

        contents = client._convert_conversation_to_native_format(conversation)

        assert len(contents) == 2
        # Second content is the assistant message (converted to model)
        assert contents[1].role == "model"
        assert contents[1].parts[0].text == "I will investigate."

    def test_convert_full_conversation(
        self, client: GeminiNativeThinkingClient
    ) -> None:
        """Test converting a full multi-turn conversation."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are an SRE agent."),
                LLMMessage(role=MessageRole.USER, content="What's the pod status?"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Let me check."),
                LLMMessage(role=MessageRole.USER, content="Tool result: Running"),
            ]
        )

        contents = client._convert_conversation_to_native_format(conversation)

        assert len(contents) == 4
        assert contents[0].role == "user"  # System -> user
        assert contents[1].role == "user"
        assert contents[2].role == "model"  # Assistant -> model
        assert contents[3].role == "user"

    def test_convert_minimal_conversation(
        self, client: GeminiNativeThinkingClient
    ) -> None:
        """Test converting a minimal conversation with just system message."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are an assistant.")
            ]
        )

        contents = client._convert_conversation_to_native_format(conversation)

        assert len(contents) == 1
        assert contents[0].role == "user"  # System converted to user with prefix
        assert "[System Instructions]" in contents[0].parts[0].text


@pytest.mark.unit
class TestGeminiNativeThinkingClientGenerate:
    """Tests for the generate method with mocked Google SDK."""

    @pytest.fixture
    def client(self) -> GeminiNativeThinkingClient:
        """Create a GeminiNativeThinkingClient for testing."""
        with patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-pro",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-key",
                temperature=0.5,
            )
            return GeminiNativeThinkingClient(config, provider_name="test-provider")

    @pytest.fixture
    def sample_conversation(self) -> LLMConversation:
        """Create a sample conversation for testing."""
        return LLMConversation(
            messages=[
                LLMMessage(
                    role=MessageRole.SYSTEM, content="You are an SRE assistant."
                ),
                LLMMessage(role=MessageRole.USER, content="Analyze pod crash."),
            ]
        )

    @pytest.fixture
    def sample_mcp_tools(self) -> List[ToolWithServer]:
        """Create sample MCP tools."""
        tool = Tool(
            name="get_pods",
            description="Get pod status",
            inputSchema={"type": "object", "properties": {"ns": {"type": "string"}}},
        )
        return [ToolWithServer(server="k8s", tool=tool)]

    @pytest.fixture
    def mock_response_final(self) -> MagicMock:
        """Create a mock final response (no tool calls)."""
        response = MagicMock()

        # Set up candidate with content parts
        part = MagicMock()
        part.thought = False
        part.text = "Analysis complete. The pod crashed due to OOM."
        part.thought_signature = b"test_signature"

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response.candidates = [candidate]
        response.function_calls = []

        # Set up usage metadata
        usage = MagicMock()
        usage.prompt_token_count = 100
        usage.candidates_token_count = 50
        usage.total_token_count = 150
        response.usage_metadata = usage

        return response

    @pytest.fixture
    def mock_response_with_thinking(self) -> MagicMock:
        """Create a mock response with thinking content."""
        response = MagicMock()

        # Thinking part
        thinking_part = MagicMock()
        thinking_part.thought = True
        thinking_part.text = "Let me analyze the pod crash..."
        thinking_part.thought_signature = None

        # Response part
        response_part = MagicMock()
        response_part.thought = False
        response_part.text = "The pod is crashing."
        response_part.thought_signature = b"sig123"

        content = MagicMock()
        content.parts = [thinking_part, response_part]

        candidate = MagicMock()
        candidate.content = content

        response.candidates = [candidate]
        response.function_calls = []
        response.usage_metadata = None

        return response

    @pytest.fixture
    def mock_response_with_tool_calls(self) -> MagicMock:
        """Create a mock response with function calls."""
        response = MagicMock()

        # Response part
        part = MagicMock()
        part.thought = False
        part.text = "I need to check pod status."
        part.thought_signature = None

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response.candidates = [candidate]

        # Function call
        fc = MagicMock()
        fc.name = "k8s__get_pods"
        fc.args = {"ns": "default"}
        response.function_calls = [fc]
        response.usage_metadata = None

        return response

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_final_response_no_tools(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
        mock_response_final: MagicMock,
    ) -> None:
        """Test generating a final response without tool calls."""
        # Setup mocks - use streaming API
        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=mock_stream_response(mock_response_final)
        )
        client._native_client = mock_native_client

        # Mock the context manager
        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        result = await client.generate(
            conversation=sample_conversation,
            session_id="test-session",
            mcp_tools=[],
        )

        assert result.is_final is True
        assert "Analysis complete" in result.content
        assert result.has_tool_calls is False
        assert result.thought_signature == b"test_signature"

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_with_thinking_content(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
        mock_response_with_thinking: MagicMock,
    ) -> None:
        """Test that thinking content is captured from response."""
        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=mock_stream_response(mock_response_with_thinking)
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        result = await client.generate(
            conversation=sample_conversation, session_id="test-session", mcp_tools=[]
        )

        assert result.thinking_content is not None
        assert "Let me analyze" in result.thinking_content
        assert "The pod is crashing" in result.content

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_with_tool_calls(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
        sample_mcp_tools: List[ToolWithServer],
        mock_response_with_tool_calls: MagicMock,
    ) -> None:
        """Test extracting tool calls from response."""
        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=mock_stream_response(mock_response_with_tool_calls)
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        result = await client.generate(
            conversation=sample_conversation,
            session_id="test-session",
            mcp_tools=sample_mcp_tools,
        )

        assert result.is_final is False
        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].server == "k8s"
        assert result.tool_calls[0].tool == "get_pods"
        assert result.tool_calls[0].parameters == {"ns": "default"}

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_timeout_raises_timeout_error(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that timeout during generation raises TimeoutError."""
        import asyncio

        async def slow_stream(*args, **kwargs):
            """Async generator that delays before yielding."""
            await asyncio.sleep(10)  # Longer than timeout
            yield MagicMock()

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=slow_stream()
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        with pytest.raises(TimeoutError, match="timed out"):
            await client.generate(
                conversation=sample_conversation,
                session_id="test-session",
                mcp_tools=[],
                timeout_seconds=0.1,  # Very short timeout
            )

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_with_native_tools_override(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
        mock_response_final: MagicMock,
    ) -> None:
        """Test that native_tools_override is applied correctly."""
        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=mock_stream_response(mock_response_final)
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        override = NativeToolsConfig(
            google_search=True, code_execution=False, url_context=True
        )

        result = await client.generate(
            conversation=sample_conversation,
            session_id="test-session",
            mcp_tools=[],
            native_tools_override=override,
        )

        # Verify the call was made (override is applied internally)
        assert result is not None
        mock_native_client.aio.models.generate_content_stream.assert_called_once()

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_with_thought_signature_continuity(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
        mock_response_final: MagicMock,
    ) -> None:
        """Test that thought_signature is passed for reasoning continuity."""
        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=mock_stream_response(mock_response_final)
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        previous_signature = b"previous_thought_signature"

        result = await client.generate(
            conversation=sample_conversation,
            session_id="test-session",
            mcp_tools=[],
            thought_signature=previous_signature,
        )

        assert result is not None
        # The call was made - signature handling is internal
        mock_native_client.aio.models.generate_content_stream.assert_called_once()

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock)
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_handles_empty_response(
        self,
        mock_context: MagicMock,
        mock_sleep: AsyncMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test handling response with no candidates (retries and injects error message)."""
        empty_response = MagicMock()
        empty_response.candidates = []
        empty_response.function_calls = None
        empty_response.usage_metadata = None

        async def empty_stream():
            yield empty_response

        mock_native_client = MagicMock()
        # Return empty response for all 4 attempts (1 + 3 retries)
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            side_effect=[empty_stream() for _ in range(4)]
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        result = await client.generate(
            conversation=sample_conversation, session_id="test-session", mcp_tools=[]
        )

        # Should inject error message after retries
        assert "LLM Response Error" in result.content
        assert "empty responses after 4 attempts" in result.content
        assert result.is_final is True  # No tool calls = final

        # Verify retries occurred
        assert mock_sleep.call_count == 3  # 3 retries
        assert mock_native_client.aio.models.generate_content_stream.call_count == 4


@pytest.mark.unit
class TestGeminiNativeThinkingClientModelSpecificConfig:
    """Tests for model-specific thinking configuration."""

    @patch('tarsy.integrations.llm.gemini_client.genai.Client')
    def test_get_thinking_config_gemini_25_pro(self, mock_genai_client: MagicMock) -> None:
        """Test that Gemini 2.5 Pro uses 32768 token thinking budget."""
        config = LLMProviderConfig(
            type=LLMProviderType.GOOGLE,
            model="gemini-2.5-pro",
            api_key_env="GOOGLE_API_KEY",
            api_key="test-key",
        )
        client = GeminiNativeThinkingClient(config)
        
        thinking_config = client._get_thinking_config("test-request-id")
        
        assert thinking_config.thinking_budget == 32768
        assert thinking_config.include_thoughts is True
        assert not hasattr(thinking_config, 'thinking_level') or thinking_config.thinking_level is None

    @patch('tarsy.integrations.llm.gemini_client.genai.Client')
    def test_get_thinking_config_gemini_25_flash(self, mock_genai_client: MagicMock) -> None:
        """Test that Gemini 2.5 Flash uses 24576 token thinking budget."""
        config = LLMProviderConfig(
            type=LLMProviderType.GOOGLE,
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            api_key="test-key",
        )
        client = GeminiNativeThinkingClient(config)
        
        thinking_config = client._get_thinking_config("test-request-id")
        
        assert thinking_config.thinking_budget == 24576
        assert thinking_config.include_thoughts is True
        assert not hasattr(thinking_config, 'thinking_level') or thinking_config.thinking_level is None

    @patch('tarsy.integrations.llm.gemini_client.genai.Client')
    def test_get_thinking_config_gemini_3_pro(self, mock_genai_client: MagicMock) -> None:
        """Test that Gemini 3 Pro uses 'high' thinking level."""
        config = LLMProviderConfig(
            type=LLMProviderType.GOOGLE,
            model="gemini-3-pro-preview",
            api_key_env="GOOGLE_API_KEY",
            api_key="test-key",
        )
        client = GeminiNativeThinkingClient(config)
        
        thinking_config = client._get_thinking_config("test-request-id")
        
        assert thinking_config.thinking_level == google_genai_types.ThinkingLevel.HIGH
        assert thinking_config.include_thoughts is True
        assert not hasattr(thinking_config, 'thinking_budget') or thinking_config.thinking_budget is None

    @patch('tarsy.integrations.llm.gemini_client.genai.Client')
    def test_get_thinking_config_unknown_model(self, mock_genai_client: MagicMock) -> None:
        """Test that unknown models fall back to 24576 token thinking budget."""
        config = LLMProviderConfig(
            type=LLMProviderType.GOOGLE,
            model="gemini-unknown-model",
            api_key_env="GOOGLE_API_KEY",
            api_key="test-key",
        )
        client = GeminiNativeThinkingClient(config)
        
        thinking_config = client._get_thinking_config("test-request-id")
        
        assert thinking_config.thinking_budget == 24576
        assert thinking_config.include_thoughts is True

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_generate_applies_model_specific_config(
        self,
        mock_context: MagicMock,
    ) -> None:
        """Test that generate() applies model-specific thinking config automatically."""
        # Create client with 2.5 Pro model
        with patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-pro",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-key",
            )
            client = GeminiNativeThinkingClient(config)
        
        # Create a valid response to avoid triggering retry logic
        response = MagicMock()
        part = MagicMock()
        part.thought = False
        part.text = "Test response"
        part.thought_signature = None
        response.candidates = [MagicMock(content=MagicMock(parts=[part]))]
        response.function_calls = None
        response.usage_metadata = None

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=mock_stream_response(response)
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System prompt."),
                LLMMessage(role=MessageRole.USER, content="Test"),
            ]
        )

        # Note: No thinking_level parameter passed
        await client.generate(
            conversation=conversation,
            session_id="test",
            mcp_tools=[],
        )

        # Verify generate_content_stream was called with correct thinking config
        call_args = mock_native_client.aio.models.generate_content_stream.call_args
        config = call_args.kwargs.get("config")

        # The thinking_budget for 2.5 Pro should be 32768
        assert config.thinking_config.thinking_budget == 32768
        assert config.thinking_config.include_thoughts is True


@pytest.mark.unit
class TestGeminiNativeThinkingStreaming:
    """Tests for native thinking streaming functionality."""

    @pytest.fixture
    def client(self) -> GeminiNativeThinkingClient:
        """Create a client for testing."""
        with patch(
            "tarsy.integrations.llm.gemini_client.get_settings"
        ) as mock_settings, \
             patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            settings = MagicMock()
            settings.enable_llm_streaming = True
            mock_settings.return_value = settings

            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-flash",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-api-key",
                temperature=0.7,
            )
            return GeminiNativeThinkingClient(config, "test-provider")

    @pytest.fixture
    def sample_conversation(self) -> LLMConversation:
        """Create a sample conversation for testing."""
        return LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are an assistant."),
                LLMMessage(role=MessageRole.USER, content="Analyze this alert."),
            ]
        )

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_streaming_publishes_thinking_chunks(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that thinking content is published via streaming."""
        # Create streaming response with thinking and response parts
        thinking_chunk = MagicMock()
        thinking_part = MagicMock()
        thinking_part.thought = True
        thinking_part.text = "Let me analyze this..."
        thinking_part.thought_signature = None
        thinking_chunk.candidates = [
            MagicMock(content=MagicMock(parts=[thinking_part]))
        ]
        thinking_chunk.function_calls = None
        thinking_chunk.usage_metadata = None

        response_chunk = MagicMock()
        response_part = MagicMock()
        response_part.thought = False
        response_part.text = "Analysis complete."
        response_part.thought_signature = b"sig123"
        response_chunk.candidates = [
            MagicMock(content=MagicMock(parts=[response_part]))
        ]
        response_chunk.function_calls = None
        response_chunk.usage_metadata = MagicMock(
            prompt_token_count=100, candidates_token_count=50, total_token_count=150
        )

        async def multi_chunk_stream():
            yield thinking_chunk
            yield response_chunk

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=multi_chunk_stream()
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        # Mock the streaming publisher's publish_chunk method to track calls
        with patch.object(
            client._streaming_publisher, "publish_chunk", new_callable=AsyncMock
        ) as mock_publish:
            result = await client.generate(
                conversation=sample_conversation,
                session_id="test-session",
                mcp_tools=[],
            )

        # Verify result
        assert result.thinking_content is not None
        assert "Let me analyze" in result.thinking_content
        assert "Analysis complete" in result.content

        # Verify streaming was attempted
        # (calls may vary based on chunk sizes)
        assert mock_publish.call_count >= 1

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_streaming_disabled_via_settings(
        self,
        mock_context: MagicMock,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that streaming can be disabled via settings."""
        with patch(
            "tarsy.integrations.llm.gemini_client.get_settings"
        ) as mock_settings, \
             patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            settings = MagicMock()
            settings.enable_llm_streaming = False
            mock_settings.return_value = settings

            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-flash",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-api-key",
                temperature=0.7,
            )
            client = GeminiNativeThinkingClient(config, "test-provider")

            response = MagicMock()
            part = MagicMock()
            part.thought = False
            part.text = "Response text."
            part.thought_signature = None
            response.candidates = [MagicMock(content=MagicMock(parts=[part]))]
            response.function_calls = None
            response.usage_metadata = None

            mock_native_client = MagicMock()
            mock_native_client.aio.models.generate_content_stream = AsyncMock(
                return_value=mock_stream_response(response)
            )
            client._native_client = mock_native_client

            mock_ctx = MagicMock()
            mock_ctx.interaction = MagicMock()
            mock_ctx.complete_success = AsyncMock()
            mock_context_cm = MagicMock()
            mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_context_cm.__aexit__ = AsyncMock(return_value=None)
            mock_context.return_value = mock_context_cm

            # Even though we call generate, streaming events should not be published
            # when streaming is disabled (the _publish_stream_chunk returns early)
            result = await client.generate(
                conversation=sample_conversation, session_id="test-session", mcp_tools=[]
            )

            assert result.content == "Response text."


@pytest.mark.unit
class TestGeminiNativeThinkingRetryLogic:
    """Tests for retry logic when handling empty LLM responses."""

    @pytest.fixture
    def client(self) -> GeminiNativeThinkingClient:
        """Create a client for testing."""
        with patch('tarsy.integrations.llm.gemini_client.genai.Client'):
            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-flash",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-api-key",
                temperature=0.7,
            )
            return GeminiNativeThinkingClient(config, "test-provider")

    @pytest.fixture
    def sample_conversation(self) -> LLMConversation:
        """Create a sample conversation for testing."""
        return LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are an assistant."),
                LLMMessage(role=MessageRole.USER, content="Analyze this alert."),
            ]
        )

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock)
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_empty_response_retries_and_succeeds(
        self,
        mock_context: MagicMock,
        mock_sleep: AsyncMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that empty response on first attempt retries and succeeds on second attempt."""
        # First response: empty (should trigger retry)
        empty_response = MagicMock()
        empty_response.candidates = []
        empty_response.function_calls = None
        empty_response.usage_metadata = None

        # Second response: valid content
        valid_response = MagicMock()
        valid_part = MagicMock()
        valid_part.thought = False
        valid_part.text = "Analysis complete."
        valid_part.thought_signature = None
        valid_response.candidates = [MagicMock(content=MagicMock(parts=[valid_part]))]
        valid_response.function_calls = None
        valid_response.usage_metadata = None

        # Use separate generator factories for each mock call to avoid shared state
        async def stream_empty_response():
            yield empty_response

        async def stream_valid_response():
            yield valid_response

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            side_effect=[stream_empty_response(), stream_valid_response()]
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        result = await client.generate(
            conversation=sample_conversation, session_id="test-session", mcp_tools=[]
        )

        # Should succeed on retry
        assert result.content == "Analysis complete."
        assert result.is_final is True

        # Verify sleep was called once (3 second delay between attempts)
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(3)

        # Verify generate_content_stream was called twice (original + 1 retry)
        assert mock_native_client.aio.models.generate_content_stream.call_count == 2

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock)
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_empty_response_all_attempts_injects_error(
        self,
        mock_context: MagicMock,
        mock_sleep: AsyncMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that persistent empty responses inject error message after max retries."""
        # All responses: empty
        empty_response = MagicMock()
        empty_response.candidates = []
        empty_response.function_calls = None
        empty_response.usage_metadata = None

        async def empty_stream():
            yield empty_response

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            side_effect=[empty_stream() for _ in range(4)]  # 4 attempts (1 + 3 retries)
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        result = await client.generate(
            conversation=sample_conversation, session_id="test-session", mcp_tools=[]
        )

        # Should inject error message
        assert "LLM Response Error" in result.content
        assert "empty responses after 4 attempts" in result.content
        assert "gemini-2.5-flash" in result.content

        # Verify sleep was called 3 times (between attempts)
        assert mock_sleep.call_count == 3

        # Verify generate_content_stream was called 4 times
        assert mock_native_client.aio.models.generate_content_stream.call_count == 4

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_thinking_only_response_retries(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that thinking content only (no actual content, no tool calls) triggers retry."""
        # First response: only thinking, no content
        thinking_only_response = MagicMock()
        thinking_part = MagicMock()
        thinking_part.thought = True
        thinking_part.text = "Let me think about this..."
        thinking_part.thought_signature = None
        thinking_only_response.candidates = [
            MagicMock(content=MagicMock(parts=[thinking_part]))
        ]
        thinking_only_response.function_calls = None
        thinking_only_response.usage_metadata = None

        # Second response: valid content
        valid_response = MagicMock()
        valid_part = MagicMock()
        valid_part.thought = False
        valid_part.text = "Analysis complete."
        valid_part.thought_signature = None
        valid_response.candidates = [MagicMock(content=MagicMock(parts=[valid_part]))]
        valid_response.function_calls = None
        valid_response.usage_metadata = None

        async def thinking_stream():
            yield thinking_only_response

        async def valid_stream():
            yield valid_response

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            side_effect=[thinking_stream(), valid_stream()]
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        with patch(
            "tarsy.integrations.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await client.generate(
                conversation=sample_conversation,
                session_id="test-session",
                mcp_tools=[],
            )

        # Should succeed on retry with valid content
        assert result.content == "Analysis complete."

        # Verify retry occurred (sleep called once)
        assert mock_sleep.call_count == 1

        # Verify two attempts were made
        assert mock_native_client.aio.models.generate_content_stream.call_count == 2

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_empty_content_with_tool_calls_does_not_retry(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that empty content with tool calls is considered valid (no retry)."""
        # Response with tool call but no text content
        response = MagicMock()
        response.candidates = []  # No text content
        response.usage_metadata = None

        # Add function call
        function_call = MagicMock()
        function_call.name = "kubernetes__get_pods"
        function_call.args = {"namespace": "default"}
        response.function_calls = [function_call]

        async def tool_call_stream():
            yield response

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=tool_call_stream()
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        result = await client.generate(
            conversation=sample_conversation,
            session_id="test-session",
            mcp_tools=[
                ToolWithServer(
                    server="kubernetes",
                    tool=Tool(name="get_pods", description="Get pods", inputSchema={}),
                )
            ],
        )

        # Should not retry (tool calls are actionable)
        assert result.has_tool_calls is True
        assert result.is_final is False
        assert len(result.tool_calls) == 1

        # Verify only one attempt was made (no retry)
        assert mock_native_client.aio.models.generate_content_stream.call_count == 1

    @pytest.mark.asyncio
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_whitespace_only_response_retries(
        self,
        mock_context: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
    ) -> None:
        """Test that whitespace-only response triggers retry."""
        # First response: whitespace only
        whitespace_response = MagicMock()
        whitespace_part = MagicMock()
        whitespace_part.thought = False
        whitespace_part.text = "   \n\t  "  # Only whitespace
        whitespace_part.thought_signature = None
        whitespace_response.candidates = [
            MagicMock(content=MagicMock(parts=[whitespace_part]))
        ]
        whitespace_response.function_calls = None
        whitespace_response.usage_metadata = None

        # Second response: valid content
        valid_response = MagicMock()
        valid_part = MagicMock()
        valid_part.thought = False
        valid_part.text = "Valid content."
        valid_part.thought_signature = None
        valid_response.candidates = [MagicMock(content=MagicMock(parts=[valid_part]))]
        valid_response.function_calls = None
        valid_response.usage_metadata = None

        async def whitespace_stream():
            yield whitespace_response

        async def valid_stream():
            yield valid_response

        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            side_effect=[whitespace_stream(), valid_stream()]
        )
        client._native_client = mock_native_client

        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock()
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm

        with patch(
            "tarsy.integrations.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await client.generate(
                conversation=sample_conversation,
                session_id="test-session",
                mcp_tools=[],
            )

        # Should succeed on retry
        assert result.content == "Valid content."

        # Verify retry occurred
        assert mock_sleep.call_count == 1
        assert mock_native_client.aio.models.generate_content_stream.call_count == 2
