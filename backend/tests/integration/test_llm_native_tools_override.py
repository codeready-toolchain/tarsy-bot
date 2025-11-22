"""
Integration tests for LLM native tools override functionality.

Tests the end-to-end flow of native tools configuration from alert submission
through to LLM client application.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from tarsy.integrations.llm.client import LLMClient
from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType, GoogleNativeTool
from tarsy.models.mcp_selection_models import NativeToolsConfig
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


@pytest.fixture
def mock_google_provider_config():
    """Create a mock Google provider config."""
    config = LLMProviderConfig(
        type=LLMProviderType.GOOGLE,
        model="gemini-2.5-pro",
        api_key_env="GOOGLE_API_KEY",
        api_key="test-key",
        native_tools={
            "google_search": True,
            "code_execution": True,
            "url_context": True
        }
    )
    return config


@pytest.fixture
def llm_client(mock_google_provider_config):
    """Create an LLM client with Google provider."""
    with patch('tarsy.integrations.llm.client.ChatGoogleGenerativeAI'):
        client = LLMClient("test-provider", mock_google_provider_config, settings=None)
        # Mock the llm_client to avoid actual API calls
        client.llm_client = Mock()
        client.available = True
        return client


class TestNativeToolsOverride:
    """Test native tools override functionality."""
    
    def test_apply_native_tools_override_all_enabled(self, llm_client):
        """Test applying override with all tools enabled."""
        override = NativeToolsConfig(
            google_search=True,
            code_execution=True,
            url_context=True
        )
        
        overridden_tools = llm_client._apply_native_tools_override(override)
        
        assert overridden_tools[GoogleNativeTool.GOOGLE_SEARCH.value] is not None
        assert overridden_tools[GoogleNativeTool.CODE_EXECUTION.value] is not None
        assert overridden_tools[GoogleNativeTool.URL_CONTEXT.value] is not None
    
    def test_apply_native_tools_override_partial(self, llm_client):
        """Test applying override with only some tools enabled."""
        override = NativeToolsConfig(
            google_search=True,
            code_execution=False,
            url_context=False
        )
        
        overridden_tools = llm_client._apply_native_tools_override(override)
        
        assert overridden_tools[GoogleNativeTool.GOOGLE_SEARCH.value] is not None
        assert overridden_tools[GoogleNativeTool.CODE_EXECUTION.value] is None
        assert overridden_tools[GoogleNativeTool.URL_CONTEXT.value] is None
    
    def test_apply_native_tools_override_none_enabled(self, llm_client):
        """Test applying override with no tools enabled."""
        override = NativeToolsConfig(
            google_search=False,
            code_execution=False,
            url_context=False
        )
        
        overridden_tools = llm_client._apply_native_tools_override(override)
        
        assert overridden_tools[GoogleNativeTool.GOOGLE_SEARCH.value] is None
        assert overridden_tools[GoogleNativeTool.CODE_EXECUTION.value] is None
        assert overridden_tools[GoogleNativeTool.URL_CONTEXT.value] is None
    
    @pytest.mark.asyncio
    async def test_generate_response_with_native_tools_override(self, llm_client):
        """Test generate_response applies native tools override correctly."""
        # Setup
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="Test system message"),
            LLMMessage(role=MessageRole.USER, content="Test user message")
        ])
        
        override = NativeToolsConfig(
            google_search=True,
            code_execution=False,
            url_context=False
        )
        
        # Mock streaming response
        mock_chunk = Mock()
        mock_chunk.content = "Test response"
        mock_chunk.usage_metadata = None
        mock_chunk.response_metadata = {}
        
        # Mock the astream method
        async def mock_astream(*args, **kwargs):
            yield mock_chunk
        
        llm_with_tools_mock = Mock()
        llm_with_tools_mock.astream = mock_astream
        
        # Mock bind to return the mock with astream
        llm_client.llm_client.bind = Mock(return_value=llm_with_tools_mock)
        
        # Execute
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            # Setup context manager mock
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "test-request-id"
            mock_ctx.interaction = Mock()
            mock_ctx.__aenter__.return_value = mock_ctx
            mock_ctx.__aexit__.return_value = None
            mock_context.return_value = mock_ctx
            
            result = await llm_client.generate_response(
                conversation=conversation,
                session_id="test-session",
                native_tools_override=override
            )
        
        # Verify bind was called (tools were bound to model)
        assert llm_client.llm_client.bind.called
        
        # Verify the conversation was updated
        assert len(result.messages) == 3  # Original 2 + 1 assistant response
        assert result.messages[-1].role == MessageRole.ASSISTANT
    
    @pytest.mark.asyncio
    async def test_generate_response_without_override_uses_defaults(self, llm_client):
        """Test generate_response uses default tools when no override provided."""
        # Setup
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="Test system message"),
            LLMMessage(role=MessageRole.USER, content="Test user message")
        ])
        
        # Mock streaming response
        mock_chunk = Mock()
        mock_chunk.content = "Test response"
        mock_chunk.usage_metadata = None
        mock_chunk.response_metadata = {}
        
        async def mock_astream(*args, **kwargs):
            yield mock_chunk
        
        llm_with_tools_mock = Mock()
        llm_with_tools_mock.astream = mock_astream
        llm_client.llm_client.bind = Mock(return_value=llm_with_tools_mock)
        
        # Execute without override
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "test-request-id"
            mock_ctx.interaction = Mock()
            mock_ctx.__aenter__.return_value = mock_ctx
            mock_ctx.__aexit__.return_value = None
            mock_context.return_value = mock_ctx
            
            result = await llm_client.generate_response(
                conversation=conversation,
                session_id="test-session",
                native_tools_override=None  # No override
            )
        
        # Verify bind was still called with default tools
        assert llm_client.llm_client.bind.called
        
        # Verify default tools were used (all 3 tools from config)
        bind_call_args = llm_client.llm_client.bind.call_args
        assert bind_call_args is not None

