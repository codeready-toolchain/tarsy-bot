"""
Unit tests for LLM client.

Tests the unified LLM client that handles communication with different
LLM providers using LangChain and the new typed hook system.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tarsy.integrations.llm.client import LLM_PROVIDERS, LLMClient
from tarsy.models.unified_interactions import LLMMessage


@pytest.mark.unit
class TestLLMClientInitialization:
    """Test LLM client initialization with different providers."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock LLM configuration."""
        return {
            "temperature": 0.7,
            "api_key": "test-api-key",
            "model": "gpt-4"
        }
    
    def test_initialization_openai_success(self, mock_config):
        """Test successful OpenAI client initialization."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai:
            mock_openai.return_value = Mock()
            
            client = LLMClient("openai", mock_config)
            
            assert client.provider_name == "openai"
            assert client.available == True
            mock_openai.assert_called_once_with(
                model_name="gpt-4",
                temperature=0.7,
                api_key="test-api-key"
            )
    
    def test_initialization_google_success(self, mock_config):
        """Test successful Google client initialization."""
        with patch('tarsy.integrations.llm.client.ChatGoogleGenerativeAI') as mock_google:
            mock_google.return_value = Mock()
            
            # Use 'google' as provider name and 'type': 'google' in config
            mock_config = {**mock_config, "type": "google"}
            client = LLMClient("google", mock_config)
            
            assert client.provider_name == "google"
            assert client.available == True
            mock_google.assert_called_once_with(
                model="gpt-4",
                temperature=0.7,
                google_api_key="test-api-key"
            )
    
    def test_initialization_xai_success(self, mock_config):
        """Test successful xAI client initialization."""
        with patch('tarsy.integrations.llm.client.ChatXAI') as mock_xai:
            mock_xai.return_value = Mock()
            
            # Use 'xai' as provider name and 'type': 'xai' in config
            mock_config = {**mock_config, "type": "xai"}
            client = LLMClient("xai", mock_config)
            
            assert client.provider_name == "xai"
            assert client.available == True
            mock_xai.assert_called_once_with(
                model_name="gpt-4",
                api_key="test-api-key",
                temperature=0.7
            )
    
    def test_initialization_anthropic_success(self, mock_config):
        """Test successful Anthropic client initialization."""
        with patch('tarsy.integrations.llm.client.ChatAnthropic') as mock_anthropic:
            mock_anthropic.return_value = Mock()
            
            # Use 'anthropic' as provider name and 'type': 'anthropic' in config
            mock_config = {**mock_config, "type": "anthropic"}
            client = LLMClient("anthropic", mock_config)
            
            assert client.provider_name == "anthropic"
            assert client.available == True
            mock_anthropic.assert_called_once_with(
                model="gpt-4",
                api_key="test-api-key",
                temperature=0.7
            )
    
    def test_initialization_unknown_provider(self, mock_config):
        """Test initialization with unknown provider."""
        client = LLMClient("unknown", mock_config)
        
        assert client.provider_name == "unknown"
        assert client.available == False
        assert client.llm_client is None
    
    def test_initialization_with_defaults(self):
        """Test initialization with minimal config uses defaults."""
        config = {"api_key": "test-key"}
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai:
            mock_openai.return_value = Mock()
            
            client = LLMClient("openai", config)
            
            mock_openai.assert_called_once_with(
                model_name="default",  # default model when not specified
                temperature=0.3,  # default temperature
                api_key="test-key"
            )
    
    def test_initialization_handles_langchain_error(self, mock_config):
        """Test initialization handles LangChain errors gracefully."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai:
            mock_openai.side_effect = Exception("LangChain error")
            
            client = LLMClient("openai", mock_config)
            
            assert client.available == False
            assert client.llm_client is None


@pytest.mark.unit
class TestLLMClientMessageConversion:
    """Test message conversion functionality."""
    
    @pytest.fixture
    def client(self):
        """Create client for testing."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            return LLMClient("openai", {"api_key": "test"})
    
    def test_convert_system_message(self, client):
        """Test system message conversion."""
        messages = [LLMMessage(role="system", content="You are a helpful assistant")]
        
        result = client._convert_messages(messages)
        
        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are a helpful assistant"
    
    def test_convert_user_message(self, client):
        """Test user message conversion."""
        messages = [LLMMessage(role="user", content="Hello, world!")]
        
        result = client._convert_messages(messages)
        
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hello, world!"
    
    def test_convert_assistant_message(self, client):
        """Test assistant message conversion."""
        messages = [LLMMessage(role="assistant", content="Hello! How can I help?")]
        
        result = client._convert_messages(messages)
        
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert result[0].content == "Hello! How can I help?"
    
    def test_convert_multiple_messages(self, client):
        """Test conversion of multiple messages."""
        messages = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="User message"),
            LLMMessage(role="assistant", content="Assistant response")
        ]
        
        result = client._convert_messages(messages)
        
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)
    
    def test_convert_empty_message_list(self, client):
        """Test conversion of empty message list."""
        result = client._convert_messages([])
        assert result == []


@pytest.mark.unit
class TestLLMClientResponseGeneration:
    """Test response generation with typed hooks."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LangChain LLM client."""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Test response from LLM"
        mock_client.ainvoke.return_value = mock_response
        return mock_client
    
    @pytest.fixture
    def client(self, mock_llm_client):
        """Create client with mocked LangChain client."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", {"api_key": "test"})
            client.llm_client = mock_llm_client
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_generate_response_success(self, client, mock_llm_client):
        """Test successful response generation with typed hooks."""
        messages = [LLMMessage(role="user", content="Test question")]
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "req-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client.generate_response(messages, "test-session-123")
            
            assert result == "Test response from LLM"
            mock_llm_client.ainvoke.assert_called_once()
            
            # Verify context was used
            mock_context.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_client_unavailable(self, client):
        """Test response generation when client is unavailable."""
        client.available = False
        messages = [LLMMessage(role="user", content="Test question")]
        
        with pytest.raises(Exception, match="openai client not available"):
            await client.generate_response(messages, "test-session")
    
    @pytest.mark.asyncio
    async def test_generate_response_llm_error(self, client, mock_llm_client):
        """Test response generation handles LLM errors."""
        mock_llm_client.ainvoke.side_effect = Exception("LLM API error")
        messages = [LLMMessage(role="user", content="Test question")]
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with pytest.raises(Exception, match="LLM API error"):
                await client.generate_response(messages, "test-session")
    
    @pytest.mark.asyncio
    async def test_generate_response_creates_proper_request_data(self, client, mock_llm_client):
        """Test that proper request data is created for typed context."""
        messages = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="User question")
        ]
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "req-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.generate_response(messages, "test-session-456")
            
            # Check that context was called with proper data structure
            context_call_args = mock_context.call_args[0]  # positional args
            
            # Verify arguments: session_id, request_data, stage_execution_id (optional)
            assert len(context_call_args) >= 2
            session_id = context_call_args[0]
            request_data = context_call_args[1]
            
            assert session_id == "test-session-456"
            assert "model" in request_data
            assert "messages" in request_data
            assert len(request_data["messages"]) == 2


@pytest.mark.unit
class TestLLMProviderMappings:
    """Test LLM provider mappings."""
    
    def test_all_providers_available(self):
        """Test that all expected providers are available."""
        expected_providers = ["openai", "google", "xai", "anthropic"]
        
        for provider in expected_providers:
            assert provider in LLM_PROVIDERS
    
    def test_provider_functions_callable(self):
        """Test that provider functions are callable."""
        for provider_name, provider_func in LLM_PROVIDERS.items():
            assert callable(provider_func)
    
    def test_provider_function_signature(self):
        """Test provider functions accept required parameters."""
        # Test with mock parameters to ensure functions work
        temp = 0.7
        api_key = "test-key"
        model = "test-model"
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai, \
             patch('tarsy.integrations.llm.client.ChatGoogleGenerativeAI') as mock_google, \
             patch('tarsy.integrations.llm.client.ChatXAI') as mock_xai, \
             patch('tarsy.integrations.llm.client.ChatAnthropic') as mock_anthropic:
            
            # Test each provider function
            LLM_PROVIDERS["openai"](temp, api_key, model)
            LLM_PROVIDERS["google"](temp, api_key, model)
            LLM_PROVIDERS["xai"](temp, api_key, model)
            LLM_PROVIDERS["anthropic"](temp, api_key, model)
            
            # Verify all were called
            mock_openai.assert_called_once()
            mock_google.assert_called_once()
            mock_xai.assert_called_once()
            mock_anthropic.assert_called_once()


@pytest.mark.integration
class TestLLMClientIntegration:
    """Integration tests for LLM client."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test complete LLM client workflow."""
        config = {
            "temperature": 0.5,
            "api_key": "test-integration-key",
            "model": "gpt-4"
        }
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai:
            # Setup mock LangChain client
            mock_langchain_client = AsyncMock()
            mock_response = Mock()
            mock_response.content = "Integration test response"
            mock_langchain_client.ainvoke.return_value = mock_response
            mock_openai.return_value = mock_langchain_client
            
            # Create client
            client = LLMClient("openai", config)
            assert client.available
            
            # Test message conversion and response generation
            messages = [
                LLMMessage(role="system", content="You are a test assistant"),
                LLMMessage(role="user", content="Hello, test!")
            ]
            
            with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
                mock_ctx = AsyncMock()
                mock_ctx.get_request_id.return_value = "integration-req-789"
                mock_context.return_value.__aenter__.return_value = mock_ctx
                
                result = await client.generate_response(messages, "integration-session")
                
                assert result == "Integration test response"
                
                # Verify the complete flow
                mock_openai.assert_called_once()
                mock_langchain_client.ainvoke.assert_called_once()
                mock_context.assert_called_once()
                
                # Verify message conversion worked
                invoke_args = mock_langchain_client.ainvoke.call_args[0][0]
                assert len(invoke_args) == 2
                assert isinstance(invoke_args[0], SystemMessage)
                assert isinstance(invoke_args[1], HumanMessage)