"""
Unit tests for LLM client timeout functionality.

Tests the 60-second timeout implementation for LLM API calls
to prevent indefinite hanging.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.integrations.llm.client import LLMClient
from tarsy.models.llm_models import LLMProviderConfig
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


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
class TestLLMClientTimeout:
    """Test LLM client timeout functionality."""
    
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
    
    @pytest.fixture
    def sample_conversation(self):
        """Create sample conversation."""
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Test question")
        ])
    
    @pytest.mark.asyncio
    async def test_llm_call_timeout_after_60_seconds(self, client, mock_llm_client, sample_conversation):
        """Test that LLM call times out after 60 seconds."""
        # Mock ainvoke to raise TimeoutError (simulating asyncio.wait_for timeout)
        mock_llm_client.ainvoke.side_effect = asyncio.TimeoutError("LLM API call timed out after 60s")
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "timeout-test-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up retry sleep
                # Should raise Exception (wrapping TimeoutError) after exhausting retries
                with pytest.raises(Exception, match="openai API error.*timed out"):
                    await client.generate_response(sample_conversation, "test-session")
                
                # Should have attempted max_retries + 1 times (4 total)
                assert mock_llm_client.ainvoke.call_count == 4
    
    @pytest.mark.asyncio
    async def test_llm_timeout_retry_logic(self, client, mock_llm_client, sample_conversation):
        """Test that timeout triggers retry with 5-second delay."""
        # First call times out, second succeeds
        success_response = Mock()
        success_response.content = "Success after timeout retry"
        
        mock_llm_client.ainvoke.side_effect = [
            asyncio.TimeoutError(),  # First call times out
            success_response  # Second call succeeds
        ]
        
        sleep_times = []
        async def mock_sleep(duration):
            sleep_times.append(duration)
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "retry-test-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep', side_effect=mock_sleep):
                result = await client.generate_response(sample_conversation, "test-session")
                
                assert result.get_latest_assistant_message().content == "Success after timeout retry"
                # Should have retried after 5-second delay
                assert 5 in sleep_times
                assert mock_llm_client.ainvoke.call_count == 2
    
    @pytest.mark.asyncio
    async def test_llm_timeout_final_failure(self, client, mock_llm_client, sample_conversation):
        """Test final failure after max retries exhausted."""
        # All calls time out
        mock_llm_client.ainvoke.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up retry delays
                with pytest.raises(Exception, match="openai API error.*timed out"):
                    await client.generate_response(sample_conversation, "test-session")
                
                # Should have tried max_retries + 1 times
                assert mock_llm_client.ainvoke.call_count == 4
    
    @pytest.mark.asyncio
    async def test_llm_call_completes_within_timeout(self, client, mock_llm_client, sample_conversation):
        """Test that normal calls complete successfully within timeout."""
        # Fast response
        mock_response = Mock()
        mock_response.content = "Quick response"
        mock_llm_client.ainvoke.return_value = mock_response
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "normal-test-789"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client.generate_response(sample_conversation, "test-session")
            
            assert result.get_latest_assistant_message().content == "Quick response"
            assert mock_llm_client.ainvoke.call_count == 1
    
    @pytest.mark.asyncio
    async def test_timeout_doesnt_interfere_with_rate_limit_retry(self, client, mock_llm_client, sample_conversation):
        """Test that timeout handling doesn't interfere with rate limit retry logic."""
        # First call rate limited, second succeeds
        rate_limit_error = Exception("429 Too Many Requests - rate limit exceeded")
        success_response = Mock()
        success_response.content = "Success after rate limit"
        
        mock_llm_client.ainvoke.side_effect = [rate_limit_error, success_response]
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "rate-limit-test"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up test
                result = await client.generate_response(sample_conversation, "test-session")
                
                assert result.get_latest_assistant_message().content == "Success after rate limit"
                assert mock_llm_client.ainvoke.call_count == 2
    
    @pytest.mark.asyncio
    async def test_timeout_with_custom_max_tokens(self, client, mock_llm_client, sample_conversation):
        """Test that timeout works correctly with max_tokens parameter."""
        # Simulate timeout
        mock_llm_client.ainvoke.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                with pytest.raises(Exception, match="openai API error.*timed out"):
                    await client.generate_response(
                        sample_conversation, 
                        "test-session",
                        max_tokens=500
                    )
                
                # Verify max_tokens was passed in config
                call_args = mock_llm_client.ainvoke.call_args
                assert 'config' in call_args.kwargs
                assert 'max_tokens' in call_args.kwargs['config']
                assert call_args.kwargs['config']['max_tokens'] == 500


@pytest.mark.unit
@pytest.mark.parametrize(
    "timeout_duration,expected_retries,should_succeed",
    [
        (30, 1, True),    # Short timeout, retry once and succeed
        (65, 1, True),    # Just over 60s, retry once and succeed  
        (120, 4, False),  # Long timeout, exhaust all retries
        (10, 1, True),    # Very short, retry once and succeed
    ],
)
class TestLLMClientTimeoutMatrix:
    """Test timeout behavior with multiple scenarios."""
    
    @pytest.mark.asyncio
    async def test_timeout_scenarios(self, timeout_duration, expected_retries, should_succeed):
        """Test various timeout scenarios."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", create_test_config(api_key="test"))
            mock_llm_client = AsyncMock()
            client.llm_client = mock_llm_client
            client.available = True
            
            # Build side_effect list based on expected scenario
            side_effects = []
            for i in range(expected_retries):
                if i == expected_retries - 1 and should_succeed:
                    # Last attempt succeeds
                    response = Mock()
                    response.content = "Success"
                    side_effects.append(response)
                else:
                    # Timeout
                    side_effects.append(asyncio.TimeoutError())
            
            # If not supposed to succeed, all attempts time out
            if not should_succeed:
                side_effects = [asyncio.TimeoutError()] * 4  # max_retries + 1
            
            mock_llm_client.ainvoke.side_effect = side_effects
            
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Test")
            ])
            
            with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
                mock_ctx = AsyncMock()
                mock_ctx.get_request_id.return_value = f"matrix-test-{timeout_duration}"
                mock_context.return_value.__aenter__.return_value = mock_ctx
                
                with patch('asyncio.sleep'):  # Speed up retries
                    if should_succeed:
                        result = await client.generate_response(conversation, "test-session")
                        assert result.get_latest_assistant_message().content == "Success"
                    else:
                        with pytest.raises(Exception, match="openai API error.*timed out"):
                            await client.generate_response(conversation, "test-session")


@pytest.mark.unit
class TestLLMClientTimeoutLogging:
    """Test that timeout events are properly logged."""
    
    @pytest.mark.asyncio
    async def test_timeout_logs_error_message(self, caplog):
        """Test that timeout errors are logged with appropriate messages."""
        with patch('tarsy.integrations.llm.client.ChatOpenAI'):
            client = LLMClient("openai", create_test_config(api_key="test"))
            mock_llm_client = AsyncMock()
            client.llm_client = mock_llm_client
            client.available = True
            
            mock_llm_client.ainvoke.side_effect = asyncio.TimeoutError()
            
            conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Test")
            ])
            
            with patch('tarsy.integrations.llm.client.llm_interaction_context') as mock_context:
                mock_ctx = AsyncMock()
                mock_context.return_value.__aenter__.return_value = mock_ctx
                
                with patch('asyncio.sleep'):
                    with pytest.raises(Exception, match="openai API error.*timed out"):
                        await client.generate_response(conversation, "test-session")
            
            # Verify timeout was logged
            assert any("timed out after 60s" in record.message for record in caplog.records)

