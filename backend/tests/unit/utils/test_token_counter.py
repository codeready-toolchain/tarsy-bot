"""
Tests for token counting utility.

This module tests the TokenCounter class used for estimating token usage
in MCP results and observations for summarization threshold decisions.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tarsy.utils.token_counter import TokenCounter


@pytest.mark.unit
class TestTokenCounter:
    """Test cases for TokenCounter class."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        # Mock tiktoken to avoid real model dependencies in tests
        with patch('tarsy.utils.token_counter.tiktoken') as mock_tiktoken:
            mock_encoding = MagicMock()
            mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
            mock_tiktoken.encoding_for_model.return_value = mock_encoding
            
            self.token_counter = TokenCounter("gpt-4o")
            self.mock_encoding = mock_encoding
    
    def test_init_with_known_model(self):
        """Test initialization with a known model."""
        with patch('tarsy.utils.token_counter.tiktoken') as mock_tiktoken:
            mock_encoding = MagicMock()
            mock_tiktoken.encoding_for_model.return_value = mock_encoding
            
            counter = TokenCounter("gpt-4o")
            mock_tiktoken.encoding_for_model.assert_called_once_with("gpt-4o")
            assert counter.encoding == mock_encoding
    
    def test_init_with_unknown_model_fallback(self):
        """Test initialization with unknown model falls back to o200k_base."""
        with patch('tarsy.utils.token_counter.tiktoken') as mock_tiktoken:
            # Simulate KeyError for unknown model
            mock_tiktoken.encoding_for_model.side_effect = KeyError("unknown model")
            mock_fallback_encoding = MagicMock()
            mock_tiktoken.get_encoding.return_value = mock_fallback_encoding
            
            counter = TokenCounter("unknown-model")
            
            mock_tiktoken.get_encoding.assert_called_once_with("o200k_base")
            assert counter.encoding == mock_fallback_encoding
    
    def test_count_tokens_with_text(self):
        """Test token counting with valid text."""
        result = self.token_counter.count_tokens("Hello world")
        
        # Our mock encoding returns 5 tokens for any input
        assert result == 5
        self.mock_encoding.encode.assert_called_once_with("Hello world")
    
    def test_count_tokens_with_empty_text(self):
        """Test token counting with empty text."""
        result = self.token_counter.count_tokens("")
        
        assert result == 0
        # Should not call encode for empty string
        self.mock_encoding.encode.assert_not_called()
    
    def test_count_tokens_with_none(self):
        """Test token counting with None input."""
        result = self.token_counter.count_tokens(None)
        
        assert result == 0
        # Should not call encode for None
        self.mock_encoding.encode.assert_not_called()
    
    def test_estimate_observation_tokens_with_dict_result(self):
        """Test observation token estimation with dictionary result containing 'result' key."""
        test_result = {
            "result": {"status": "running", "replicas": 3},
            "metadata": "ignored"
        }
        
        result = self.token_counter.estimate_observation_tokens("kubectl", "get_pods", test_result)
        
        assert result == 5  # Mock returns 5 tokens
        
        # Verify the format matches what would be sent to the LLM
        expected_formatted = json.dumps(test_result["result"], indent=2, default=str)
        expected_observation = f"kubectl.get_pods: {expected_formatted}"
        
        self.mock_encoding.encode.assert_called_once_with(expected_observation)
    
    def test_estimate_observation_tokens_with_simple_result(self):
        """Test observation token estimation with simple result without 'result' key."""
        test_result = {"status": "success", "message": "Operation completed"}
        
        result = self.token_counter.estimate_observation_tokens("postgres", "query", test_result)
        
        assert result == 5  # Mock returns 5 tokens
        
        # Verify the format matches what would be sent to the LLM
        expected_formatted = json.dumps(test_result, indent=2, default=str)
        expected_observation = f"postgres.query: {expected_formatted}"
        
        self.mock_encoding.encode.assert_called_once_with(expected_observation)
    
    def test_estimate_observation_tokens_with_string_result_value(self):
        """Test observation token estimation when result['result'] is a string."""
        test_result = {
            "result": "Pod is running successfully",
            "timestamp": "2024-01-01T00:00:00Z"
        }
        
        result = self.token_counter.estimate_observation_tokens("kubectl", "describe", test_result)
        
        assert result == 5  # Mock returns 5 tokens
        
        # String results should not be JSON formatted
        expected_observation = f"kubectl.describe: Pod is running successfully"
        
        self.mock_encoding.encode.assert_called_once_with(expected_observation)
    
    def test_estimate_observation_tokens_with_formatting_error(self):
        """Test observation token estimation gracefully handles JSON formatting errors."""
        # Create a result with dict content that will cause JSON serialization issues
        class UnserializableObject:
            pass
        
        # Make result['result'] a dict so json.dumps gets called and fails
        test_result = {"result": {"data": UnserializableObject()}}
        
        with patch('tarsy.utils.token_counter.json.dumps') as mock_json_dumps:
            mock_json_dumps.side_effect = TypeError("Object not serializable")
            
            result = self.token_counter.estimate_observation_tokens("server", "tool", test_result)
            
            assert result == 5  # Mock returns 5 tokens
            
            # Should fall back to string representation of full result
            expected_observation = f"server.tool: {str(test_result)}"
            self.mock_encoding.encode.assert_called_once_with(expected_observation)
    
    def test_estimate_observation_tokens_edge_cases(self):
        """Test observation token estimation with various edge cases."""
        # Empty result
        result = self.token_counter.estimate_observation_tokens("server", "tool", {})
        assert result == 5
        
        # None result content
        result = self.token_counter.estimate_observation_tokens("server", "tool", {"result": None})
        assert result == 5
        
        # Very nested structure
        complex_result = {
            "result": {
                "level1": {
                    "level2": {
                        "data": [1, 2, 3, {"nested": True}]
                    }
                }
            }
        }
        result = self.token_counter.estimate_observation_tokens("server", "tool", complex_result)
        assert result == 5

