"""
Unit tests for LLM client.

Tests the unified LLM client that handles communication with different
LLM providers using LangChain and the new typed hook system.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tarsy.integrations.llm.client import LLM_PROVIDERS, LLMClient, LLMManager
from tarsy.models.constants import DEFAULT_LLM_TEMPERATURE
from tarsy.models.llm_models import LLMProviderConfig
from tarsy.models.unified_interactions import LLMMessage, LLMConversation, MessageRole


def create_test_config(provider_type: str = "openai", **overrides) -> LLMProviderConfig:
    """Helper to create test LLMProviderConfig instances."""
    defaults = {
        "type": provider_type,
        "model": "gpt-4",
        "api_key_env": "OPENAI_API_KEY",
        "temperature": 0.7,
        "api_key": "test-api-key"
    }
    defaults.update(overrides)
    return LLMProviderConfig(**defaults)


@pytest.mark.unit
class TestLLMClientInitialization:
    """Test LLM client initialization with different providers."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock LLM configuration."""
        return create_test_config()
    
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
            google_config = create_test_config(type="google")
            client = LLMClient("google", google_config)
            
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
            xai_config = create_test_config(type="xai")
            client = LLMClient("xai", xai_config)
            
            assert client.provider_name == "xai"
            assert client.available == True
            mock_xai.assert_called_once_with(
                model="gpt-4",
                api_key="test-api-key",
                temperature=0.7
            )
    
    def test_initialization_anthropic_success(self, mock_config):
        """Test successful Anthropic client initialization."""
        with patch('tarsy.integrations.llm.client.ChatAnthropic') as mock_anthropic:
            mock_anthropic.return_value = Mock()
            
            # Use 'anthropic' as provider name and 'type': 'anthropic' in config
            anthropic_config = create_test_config(type="anthropic")
            client = LLMClient("anthropic", anthropic_config)
            
            assert client.provider_name == "anthropic"
            assert client.available == True
            mock_anthropic.assert_called_once_with(
                model="gpt-4",
                api_key="test-api-key",
                temperature=0.7
            )
    
    def test_initialization_unknown_provider(self):
        """Test that BaseModel validation prevents unknown provider types."""
        # BaseModel should prevent unknown provider types at creation time
        with pytest.raises(Exception):  # Pydantic validation error
            LLMProviderConfig(
                type="unknown-provider",  # Should fail validation
                model="test-model",
                api_key_env="TEST_API_KEY",
                api_key="test-key"
            )
    
    def test_initialization_with_defaults(self):
        """Test initialization with minimal config uses BaseModel defaults."""
        # Create config with only required fields to test BaseModel defaults
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4", 
            api_key_env="OPENAI_API_KEY",
            api_key="test-key"
            # Uses BaseModel defaults: temperature=0.1
        )
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai:
            mock_openai.return_value = Mock()
            
            client = LLMClient("openai", config)
            
            mock_openai.assert_called_once_with(
                model_name="gpt-4",  # model from config
                temperature=0.1,     # BaseModel default temperature
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
            return LLMClient("openai", LLMProviderConfig(
                type="openai",
                model="gpt-4", 
                api_key_env="OPENAI_API_KEY",
                api_key="test"
            ))
    
    def test_convert_system_message(self, client):
        """Test system message conversion."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant")
        ])
        
        result = client._convert_conversation_to_langchain(conversation)
        
        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are a helpful assistant"
    
    def test_convert_user_message(self, client):
        """Test user message conversion."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message"),
            LLMMessage(role=MessageRole.USER, content="Hello, world!")
        ])
        
        result = client._convert_conversation_to_langchain(conversation)
        
        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert result[1].content == "Hello, world!"
    
    def test_convert_assistant_message(self, client):
        """Test assistant message conversion."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Hello! How can I help?")
        ])
        
        result = client._convert_conversation_to_langchain(conversation)
        
        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], AIMessage)
        assert result[1].content == "Hello! How can I help?"
    
    def test_convert_multiple_messages(self, client):
        """Test conversion of multiple messages."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="User message"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Assistant response")
        ])
        
        result = client._convert_conversation_to_langchain(conversation)
        
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)
    
    def test_convert_empty_message_list(self, client):
        """Test conversion of empty message list."""
        # Note: LLMConversation requires at least one message (system message)
        # This test now tests with minimal valid conversation
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message")
        ])
        
        result = client._convert_conversation_to_langchain(conversation)
        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)


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
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.llm_client = mock_llm_client
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_generate_response_success(self, client, mock_llm_client):
        """Test successful response generation with typed hooks."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test question")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "req-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client.generate_response(conversation, "test-session-123")
            
            # The method should return an updated conversation, not just a string
            assert isinstance(result, LLMConversation)
            assert len(result.messages) == 3  # System + User + Assistant response
            assert result.messages[2].content == "Test response from LLM"  # Assistant message is at index 2
            mock_llm_client.ainvoke.assert_called_once()
            
            # Verify context was used
            mock_context.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_client_unavailable(self, client):
        """Test response generation when client is unavailable."""
        client.available = False
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test question")
        ])
        
        with pytest.raises(Exception, match="openai client not available"):
            await client.generate_response(conversation, "test-session")
    
    @pytest.mark.asyncio
    async def test_generate_response_llm_error(self, client, mock_llm_client):
        """Test response generation handles LLM errors."""
        mock_llm_client.ainvoke.side_effect = Exception("LLM API error")
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test question")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with pytest.raises(Exception, match="openai API error"):
                await client.generate_response(conversation, "test-session")
    
    @pytest.mark.asyncio
    async def test_generate_response_creates_proper_request_data(self, client):
        """Test that proper request data is created for typed context."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="User question")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "req-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.generate_response(conversation, "test-session-456")
            
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


@pytest.mark.unit
class TestLLMClientSSLAndBaseURL:
    """Test SSL verification and base URL configuration."""
    
    def test_initialization_with_ssl_disabled(self):
        """Test client initialization with SSL verification disabled."""
        config = create_test_config(
            api_key="test-key",
            disable_ssl_verification=True
        )
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai, \
             patch('tarsy.integrations.llm.client.httpx.Client') as mock_client, \
             patch('tarsy.integrations.llm.client.httpx.AsyncClient') as mock_async_client:
            
            client = LLMClient("openai", config)
            
            # Verify SSL warning was logged
            assert client.available is True
            
            # Verify httpx clients were created with verify=False
            mock_client.assert_called_with(verify=False)
            mock_async_client.assert_called_with(verify=False)
            
            # Verify the clients were passed to ChatOpenAI
            call_args = mock_openai.call_args[1]  # keyword arguments
            assert 'http_client' in call_args
            assert 'http_async_client' in call_args
    
    def test_initialization_with_custom_base_url(self):
        """Test client initialization with custom base URL."""
        config = create_test_config(
            api_key="test-key",
            base_url="https://custom-api.example.com/v1"
        )
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI') as mock_openai:
            client = LLMClient("openai", config)
            
            # Verify base_url was passed to ChatOpenAI
            call_args = mock_openai.call_args[1]
            assert call_args['base_url'] == "https://custom-api.example.com/v1"
    
    def test_initialization_google_ignores_base_url(self):
        """Test Google client ignores base_url parameter."""
        config = create_test_config(
            type="google",
            model="gemini-pro",
            api_key="test-key",
            base_url="https://custom-google.example.com"  # Should be ignored
        )
        
        with patch('tarsy.integrations.llm.client.ChatGoogleGenerativeAI') as mock_google:
            client = LLMClient("google", config)
            
            # Verify base_url was not passed to Google client
            call_args = mock_google.call_args[1]
            assert 'base_url' not in call_args


@pytest.mark.unit
class TestLLMClientRetryLogic:
    """Test retry logic for rate limiting and empty responses."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LangChain client."""
        return AsyncMock()
    
    @pytest.fixture
    def client_with_retry(self, mock_llm_client):
        """Create client for retry testing."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.llm_client = mock_llm_client
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, client_with_retry, mock_llm_client):
        """Test retry logic for rate limiting errors."""
        # First call fails with rate limit, second succeeds
        rate_limit_error = Exception("429 Too Many Requests - rate limit exceeded")
        success_response = Mock()
        success_response.content = "Success after retry"
        
        mock_llm_client.ainvoke.side_effect = [rate_limit_error, success_response]
        
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "retry-test"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep') as mock_sleep:  # Speed up test
                result = await client_with_retry.generate_response(conversation, "test-session")
                
                assert isinstance(result, LLMConversation)
                assert result.get_latest_assistant_message().content == "Success after retry"
                assert mock_llm_client.ainvoke.call_count == 2
                mock_sleep.assert_called_once()  # Should have slept before retry
    
    @pytest.mark.asyncio
    async def test_retry_exhausted_on_rate_limit(self, client_with_retry, mock_llm_client):
        """Test behavior when rate limit retries are exhausted."""
        rate_limit_error = Exception("rate_limit_exceeded")
        mock_llm_client.ainvoke.side_effect = rate_limit_error
        
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up test
                with pytest.raises(Exception, match="rate_limit_exceeded"):
                    await client_with_retry.generate_response(conversation, "test-session")
                
                # Should have tried max_retries + 1 times
                assert mock_llm_client.ainvoke.call_count == 4  # 3 retries + 1 initial
    
    @pytest.mark.asyncio
    async def test_empty_response_retry(self, client_with_retry, mock_llm_client):
        """Test retry logic for empty responses."""
        # First response empty, second has content
        empty_response = Mock()
        empty_response.content = ""
        success_response = Mock()
        success_response.content = "Success after empty retry"
        
        mock_llm_client.ainvoke.side_effect = [empty_response, success_response]
        
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "empty-retry-test"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up test
                result = await client_with_retry.generate_response(conversation, "test-session")
                
                assert isinstance(result, LLMConversation)
                assert result.get_latest_assistant_message().content == "Success after empty retry"
                assert mock_llm_client.ainvoke.call_count == 2
    
    @pytest.mark.asyncio
    async def test_empty_response_fallback_message(self, client_with_retry, mock_llm_client):
        """Test fallback message injection for persistent empty responses."""
        empty_response = Mock()
        empty_response.content = ""
        mock_llm_client.ainvoke.return_value = empty_response
        
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                result = await client_with_retry.generate_response(conversation, "test-session")
                
                # Should inject error message
                assert isinstance(result, LLMConversation)
                latest_message = result.get_latest_assistant_message()
                assert "LLM Response Error" in latest_message.content
                assert "openai LLM returned empty responses" in latest_message.content
    
    @pytest.mark.asyncio
    async def test_retry_delay_extraction(self, client_with_retry):
        """Test extraction of retry delay from error message."""
        # Test the private method
        error_with_delay = "API error: retry_delay { seconds: 5 }"
        delay = client_with_retry._extract_retry_delay(error_with_delay)
        assert delay == 5
        
        error_without_delay = "Generic API error"
        delay = client_with_retry._extract_retry_delay(error_without_delay)
        assert delay is None
    
    @pytest.mark.asyncio
    async def test_non_rate_limit_error_no_retry(self, client_with_retry, mock_llm_client):
        """Test that non-rate-limit errors don't trigger retries."""
        generic_error = Exception("Generic API error")
        mock_llm_client.ainvoke.side_effect = generic_error
        
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test")
        ])
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with pytest.raises(Exception, match="Generic API error"):
                await client_with_retry.generate_response(conversation, "test-session")
            
            # Should only try once (no retries)
            assert mock_llm_client.ainvoke.call_count == 1


@pytest.mark.unit
class TestLLMClientErrorHandling:
    """Test comprehensive error handling and logging."""
    
    @pytest.fixture
    def client_for_errors(self):
        """Create client for error testing."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.available = True
            return client
    
    @pytest.mark.usefixtures("client_for_errors")
    def test_extract_error_details_basic_exception(self):
        """Test error detail extraction for basic exceptions."""
        from tarsy.utils.error_details import extract_error_details
        
        try:
            raise ValueError("Test error message")
        except Exception as e:
            details = extract_error_details(e)
            
            assert "Type=ValueError" in details
            assert "Message=Test error message" in details
    
    @pytest.mark.usefixtures("client_for_errors")
    def test_extract_error_details_with_cause(self):
        """Test error detail extraction with exception chain."""
        from tarsy.utils.error_details import extract_error_details
        
        try:
            try:
                raise ConnectionError("Network failed")
            except Exception as e:
                raise ValueError("Wrapper error") from e
        except Exception as e:
            details = extract_error_details(e)
            
            assert "Type=ValueError" in details
            assert "RootCause=ConnectionError: Network failed" in details
    
    @pytest.mark.usefixtures("client_for_errors")
    def test_extract_error_details_with_attributes(self):
        """Test error detail extraction with exception attributes."""
        from tarsy.utils.error_details import extract_error_details
        
        class CustomException(Exception):
            def __init__(self, message):
                super().__init__(message)
                self.status_code = 500
                self.error_type = "server_error"
        
        try:
            raise CustomException("Custom error")
        except Exception as e:
            details = extract_error_details(e)
            
            assert "status_code=500" in details
            assert "error_type='server_error'" in details
    
    @pytest.mark.usefixtures("client_for_errors")
    def test_extract_error_details_preserves_long_values(self):
        """Test that long attribute values are preserved in full."""
        from tarsy.utils.error_details import extract_error_details
        
        class LongAttributeException(Exception):
            def __init__(self):
                super().__init__("Error with long attribute")
                self.long_data = "x" * 300  # Very long string
        
        try:
            raise LongAttributeException()
        except Exception as e:
            details = extract_error_details(e)
            
            # Should preserve full long values for debugging
            assert "long_data=" in details
            assert "x" * 300 in details  # Full string should be preserved


@pytest.mark.integration
class TestLLMClientIntegration:
    """Integration tests for LLM client."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test complete LLM client workflow."""
        config = create_test_config(
            temperature=0.5,
            api_key="test-integration-key"
        )
        
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
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a test assistant"),
                LLMMessage(role=MessageRole.USER, content="Hello, test!")
            ])
            
            with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
                mock_ctx = AsyncMock()
                mock_ctx.get_request_id.return_value = "integration-req-789"
                mock_context.return_value.__aenter__.return_value = mock_ctx
                
                result = await client.generate_response(conversation, "integration-session")
                
                assert isinstance(result, LLMConversation)
                assert result.get_latest_assistant_message().content == "Integration test response"
                
                # Verify the complete flow
                mock_openai.assert_called_once()
                mock_langchain_client.ainvoke.assert_called_once()
                mock_context.assert_called_once()
                
                # Verify message conversion worked
                invoke_args = mock_langchain_client.ainvoke.call_args[0][0]
                assert len(invoke_args) == 2
                assert isinstance(invoke_args[0], SystemMessage)
                assert isinstance(invoke_args[1], HumanMessage)


@pytest.mark.unit
class TestLLMClientMaxToolResultTokens:
    """Test max tool result tokens functionality."""
    
    def test_get_max_tool_result_tokens_with_config(self):
        """Test get_max_tool_result_tokens with configured value."""
        config = create_test_config(
            api_key="test-key",
            max_tool_result_tokens=200000
        )
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", config)
            
            result = client.get_max_tool_result_tokens()
            assert result == 200000
    
    def test_get_max_tool_result_tokens_no_config(self):
        """Test get_max_tool_result_tokens uses BaseModel default when not explicitly configured."""
        config = create_test_config(api_key="test-key")
        # BaseModel will automatically use default max_tool_result_tokens=100000
        
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", config)
            
            result = client.get_max_tool_result_tokens()
            assert result == 100000  # BaseModel default value
    
    def test_get_max_tool_result_tokens_invalid_value(self):
        """Test that BaseModel validation rejects invalid max_tool_result_tokens values."""
        # BaseModel should reject invalid values at creation time
        with pytest.raises(Exception):  # Pydantic validation error
            create_test_config(
                api_key="test-key",
                max_tool_result_tokens="invalid-string"  # Invalid value - should fail validation
            )
    
    def test_get_max_tool_result_tokens_none_value(self):
        """Test that BaseModel validation rejects None value."""
        # BaseModel should reject None values at creation time (field validation: gt=0)
        with pytest.raises(Exception):  # Pydantic validation error
            create_test_config(
                api_key="test-key",
                max_tool_result_tokens=None  # Should fail validation
            )
    
    def test_get_max_tool_result_tokens_zero_value(self):
        """Test that BaseModel validation rejects zero value."""
        # BaseModel should reject zero values at creation time (field validation: gt=0) 
        with pytest.raises(Exception):  # Pydantic validation error
            create_test_config(
                api_key="test-key",
                max_tool_result_tokens=0  # Should fail validation (gt=0)
            )


@pytest.mark.unit
class TestLLMClientTokenUsageTracking:
    """Test token usage tracking functionality added in EP-0009."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LangChain LLM client."""
        return AsyncMock()
    
    @pytest.fixture
    def client(self, mock_llm_client):
        """Create client with mocked LangChain client."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.llm_client = mock_llm_client
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_generate_response_captures_token_usage(self, client, mock_llm_client):
        """Test that token usage is captured and stored in interaction context."""
        # Arrange
        mock_response = Mock()
        mock_response.content = "Test response from LLM"
        
        # Mock the _execute_with_retry to return usage metadata
        usage_metadata = {
            'input_tokens': 120,
            'output_tokens': 45,
            'total_tokens': 165
        }
        
        with patch.object(client, '_execute_with_retry', return_value=(mock_response, usage_metadata)) as mock_execute:
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="Test question")
            ])
            
            with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
                mock_ctx = AsyncMock()
                mock_ctx.get_request_id.return_value = "req-123"
                mock_context.return_value.__aenter__.return_value = mock_ctx
                
                # Act
                result = await client.generate_response(conversation, "test-session-123")
                
                # Assert
                assert isinstance(result, LLMConversation)
                
                # Verify token usage was stored in context
                assert mock_ctx.interaction.input_tokens == 120
                assert mock_ctx.interaction.output_tokens == 45  
                assert mock_ctx.interaction.total_tokens == 165
                
                mock_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_handles_missing_token_usage(self, client, mock_llm_client):
        """Test graceful handling when provider doesn't return usage metadata."""
        # Arrange
        mock_response = Mock()
        mock_response.content = "Test response from LLM"
        
        # Mock _execute_with_retry to return None usage metadata
        with patch.object(client, '_execute_with_retry', return_value=(mock_response, None)):
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="Test question")
            ])
            
            with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
                mock_ctx = AsyncMock()
                mock_context.return_value.__aenter__.return_value = mock_ctx
                
                # Act
                result = await client.generate_response(conversation, "test-session")
                
                # Assert
                assert isinstance(result, LLMConversation)
                
                # Token fields should not have been set when usage_metadata is None
                # Since we mocked _execute_with_retry to return None usage_metadata,
                # the token setting code should not execute
                # We can verify this by checking that the token assignment code path wasn't taken
                
                # The key assertion is that the method completed without error,
                # meaning it handled None usage_metadata gracefully
    
    @pytest.mark.asyncio
    async def test_generate_response_handles_zero_token_usage(self, client, mock_llm_client):
        """Test handling of zero token usage values."""
        # Arrange
        mock_response = Mock()
        mock_response.content = "Test response"
        
        # Mock usage metadata with zero values
        usage_metadata = {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0
        }
        
        with patch.object(client, '_execute_with_retry', return_value=(mock_response, usage_metadata)):
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="Test")
            ])
            
            with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
                mock_ctx = AsyncMock()
                mock_context.return_value.__aenter__.return_value = mock_ctx
                
                # Act
                await client.generate_response(conversation, "test-session")
                
                # Assert - zero values should be stored as None for cleaner database storage
                assert mock_ctx.interaction.input_tokens is None
                assert mock_ctx.interaction.output_tokens is None  
                assert mock_ctx.interaction.total_tokens is None
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_uses_usage_metadata_callback(self, client):
        """Test that _execute_with_retry properly uses UsageMetadataCallbackHandler."""
        # Arrange
        mock_response = Mock()
        mock_response.content = "Test response"
        client.llm_client.ainvoke.return_value = mock_response
        
        # Mock the callback to return usage data
        with patch('tarsy.integrations.llm.client.UsageMetadataCallbackHandler') as mock_callback_class:
            mock_callback_instance = Mock()
            mock_callback_instance.usage_metadata = {
                'gpt-4': {
                    'input_tokens': 100,
                    'output_tokens': 50,
                    'total_tokens': 150
                }
            }
            mock_callback_class.return_value = mock_callback_instance
            
            # Act
            response, usage_metadata = await client._execute_with_retry([])
            
            # Assert
            assert response == mock_response
            assert usage_metadata == {
                'input_tokens': 100,
                'output_tokens': 50,
                'total_tokens': 150
            }
            
            # Verify callback was used
            mock_callback_class.assert_called_once()
            client.llm_client.ainvoke.assert_called_once()
            
            # Verify callback was passed to ainvoke
            call_args = client.llm_client.ainvoke.call_args
            assert 'config' in call_args.kwargs
            assert 'callbacks' in call_args.kwargs['config']
            assert call_args.kwargs['config']['callbacks'] == [mock_callback_instance]
    
    @pytest.mark.asyncio
    async def test_generate_response_with_llm_config(self, client, mock_llm_client):
        """Test that max_tokens parameter is properly passed to ainvoke."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="User question")
        ])

        # Mock successful LLM response
        mock_response = Mock()
        mock_response.content = "Test response"
        mock_llm_client.ainvoke.return_value = mock_response

        # Test with max_tokens parameter
        max_tokens = 500

        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = Mock()
            mock_ctx.get_request_id.return_value = "test-request-id"
            mock_ctx.interaction = Mock()
            mock_ctx.complete_success = AsyncMock()  # Make this async
            mock_context.return_value.__aenter__.return_value = mock_ctx
            mock_context.return_value.__aexit__.return_value = None

            await client.generate_response(
                conversation, "test-session", "test-stage", max_tokens=max_tokens
            )

        # Verify ainvoke was called with correct config
        call_args = mock_llm_client.ainvoke.call_args
        assert 'config' in call_args.kwargs
        config = call_args.kwargs['config']

        # Config should contain callbacks and max_tokens
        assert 'callbacks' in config
        assert 'max_tokens' in config
        assert config['max_tokens'] == 500
        
        # max_tokens should NOT be passed as top-level keyword arg
        assert 'max_tokens' not in call_args.kwargs
    
    @pytest.mark.asyncio
    async def test_generate_response_without_llm_config(self, client, mock_llm_client):
        """Test that generate_response works without llm_config (backward compatibility)."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="User question")
        ])
        
        # Mock successful LLM response
        mock_response = Mock()
        mock_response.content = "Test response"
        mock_llm_client.ainvoke.return_value = mock_response
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = Mock()
            mock_ctx.get_request_id.return_value = "test-request-id"
            mock_ctx.interaction = Mock()
            mock_ctx.complete_success = AsyncMock()  # Make this async
            mock_context.return_value.__aenter__.return_value = mock_ctx
            mock_context.return_value.__aexit__.return_value = None
            
            await client.generate_response(conversation, "test-session", "test-stage")
        
        # Verify ainvoke was called with only callbacks (no extra config)
        call_args = mock_llm_client.ainvoke.call_args
        assert 'config' in call_args.kwargs
        config = call_args.kwargs['config']
        
        # Should only have callbacks in config, no extra LLM parameters as kwargs
        assert 'callbacks' in config
        assert 'max_tokens' not in config
        assert 'temperature' not in config
        # Verify max_tokens is not passed as direct kwarg
        assert 'max_tokens' not in call_args.kwargs
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_with_llm_config(self, client):
        """Test that _execute_with_retry properly handles max_tokens parameter."""
        # Mock successful LLM response
        mock_response = Mock()
        mock_response.content = "Test response"
        client.llm_client.ainvoke.return_value = mock_response

        max_tokens = 1000

        with patch('tarsy.integrations.llm.client.UsageMetadataCallbackHandler') as mock_callback_class:
            mock_callback_instance = Mock()
            mock_callback_instance.usage_metadata = None
            mock_callback_class.return_value = mock_callback_instance

            await client._execute_with_retry(
                [], max_retries=3, max_tokens=max_tokens
            )

            # Verify config was properly created
            call_args = client.llm_client.ainvoke.call_args
            config = call_args.kwargs['config']
            assert 'callbacks' in config
            assert config['callbacks'] == [mock_callback_instance]
            assert 'max_tokens' in config
            assert config['max_tokens'] == 1000
            # max_tokens should NOT be passed as direct kwarg
            assert 'max_tokens' not in call_args.kwargs


@pytest.mark.unit
class TestLLMManager:
    """Test LLMManager functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock Settings for LLMManager."""
        mock_settings = Mock()
        mock_settings.llm_providers = {
            "openai-default": {"api_key": "test-key-1"},
            "google-default": {"api_key": "test-key-2"},
            "anthropic-default": {"api_key": ""}  # No API key
        }
        mock_settings.llm_provider = "openai-default"
        mock_settings.get_llm_config.side_effect = lambda name: mock_settings.llm_providers[name]
        return mock_settings
    
    @pytest.fixture
    def llm_manager(self, mock_settings):
        """Create LLMManager with mocked dependencies."""
        with patch('tarsy.integrations.llm.client.LLMClient') as mock_llm_client_class:
            # Mock successful client creation for providers with API keys
            mock_client_1 = Mock()
            mock_client_1.available = True
            mock_client_1.get_max_tool_result_tokens.return_value = 250000
            
            mock_client_2 = Mock()
            mock_client_2.available = True
            mock_client_2.get_max_tool_result_tokens.return_value = 950000
            
            def client_side_effect(provider_name, config):
                if provider_name == "openai-default":
                    return mock_client_1
                elif provider_name == "google-default":
                    return mock_client_2
                return Mock(available=False)
            
            mock_llm_client_class.side_effect = client_side_effect
            
            manager = LLMManager(mock_settings)
            # Override the clients dictionary directly for testing
            manager.clients = {
                "openai-default": mock_client_1,
                "google-default": mock_client_2
            }
            return manager
    
    def test_get_max_tool_result_tokens_with_default_client(self, llm_manager):
        """Test get_max_tool_result_tokens returns value from default client."""
        # Act
        result = llm_manager.get_max_tool_result_tokens()
        
        # Assert
        assert result == 250000  # openai-default client limit
        # Verify the default client's method was called
        default_client = llm_manager.get_client()
        default_client.get_max_tool_result_tokens.assert_called_once()
    
    def test_get_max_tool_result_tokens_with_specific_provider(self, llm_manager, mock_settings):
        """Test get_max_tool_result_tokens with specific provider override."""
        # Set different default provider
        mock_settings.llm_provider = "google-default"
        
        # Act
        result = llm_manager.get_max_tool_result_tokens()
        
        # Assert - should use google-default client's limit
        google_client = llm_manager.get_client("google-default")
        google_client.get_max_tool_result_tokens.assert_called_once()
    
    def test_get_max_tool_result_tokens_no_clients_available(self, mock_settings):
        """Test get_max_tool_result_tokens when no clients are available."""
        with patch('tarsy.integrations.llm.client.LLMClient'):
            # Create manager with no available clients
            manager = LLMManager(mock_settings)
            manager.clients = {}  # No clients available
            
            # Act
            result = manager.get_max_tool_result_tokens()
            
            # Assert - should return safe fallback
            assert result == 150000
    
    def test_get_max_tool_result_tokens_client_error_handling(self, llm_manager):
        """Test error handling when client method fails."""
        # Setup client to raise exception
        default_client = llm_manager.get_client()
        default_client.get_max_tool_result_tokens.side_effect = Exception("Client error")
        
        # Act & Assert - should propagate the exception
        with pytest.raises(Exception, match="Client error"):
            llm_manager.get_max_tool_result_tokens()
    
    def test_get_max_tool_result_tokens_with_invalid_client_response(self, llm_manager):
        """Test handling when client returns invalid values."""
        # Setup client to return None
        default_client = llm_manager.get_client()
        default_client.get_max_tool_result_tokens.return_value = None
        
        # Act
        result = llm_manager.get_max_tool_result_tokens()
        
        # Assert - None should be handled gracefully by the client itself
        assert result is None  # Client handles invalid values, manager just passes through
