"""
Token counting utility for estimating token usage in MCP results and observations.

This module provides utilities for counting tokens in text data using tiktoken,
with fallback handling for unknown models and specific formatting for ReAct observations.
"""

import json
import tiktoken
from typing import Any, Dict

from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class TokenCounter:
    """Utility for estimating token counts in text data."""
    
    def __init__(self, model: str = "gpt-4o"):
        """Initialize with tiktoken encoding for the specified model.
        
        Args:
            model: The model name to use for token encoding (defaults to gpt-4o)
        """
        try:
            self.encoding = tiktoken.encoding_for_model(model)
            logger.debug(f"Initialized TokenCounter with {model} encoding")
        except KeyError:
            # Fallback to o200k_base encoding for unknown models
            self.encoding = tiktoken.get_encoding("o200k_base")
            logger.warning(f"Unknown model {model}, using o200k_base encoding fallback")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text string.
        
        Args:
            text: The text to count tokens for
            
        Returns:
            The number of tokens in the text
        """
        if not text:
            return 0
        return len(self.encoding.encode(text))
    
    def estimate_observation_tokens(self, server_name: str, tool_name: str, result: Dict[str, Any]) -> int:
        """Estimate tokens that would be used in ReAct observation.
        
        This method simulates the format_observation output format to provide
        accurate token estimates for summarization threshold decisions.
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool that produced the result
            result: The tool result dictionary
            
        Returns:
            Estimated number of tokens the observation would consume
        """
        try:
            # Simulate the format_observation output format
            if isinstance(result, dict) and 'result' in result:
                formatted_result = json.dumps(result['result'], indent=2, default=str) if isinstance(result['result'], dict) else str(result['result'])
            else:
                formatted_result = json.dumps(result, indent=2, default=str)
            
            observation_text = f"{server_name}.{tool_name}: {formatted_result}"
            return self.count_tokens(observation_text)
        except Exception as e:
            # If formatting fails, estimate conservatively with string representation
            logger.warning(f"Failed to format result for token counting: {e}")
            observation_text = f"{server_name}.{tool_name}: {str(result)}"
            return self.count_tokens(observation_text)

