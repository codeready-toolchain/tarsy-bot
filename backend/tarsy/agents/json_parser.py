"""
Shared JSON parsing utilities for agent LLM responses.

Provides consistent JSON parsing logic across all agent modules with
proper error handling and markdown code block extraction.
"""

import json
from typing import Any, Dict, Type, TypeVar

from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)

T = TypeVar('T')


def parse_llm_json_response(response: str, expected_type: Type[T] = dict) -> T:
    """
    Parse JSON response from LLM, handling markdown code blocks.
    
    This utility handles the common pattern of LLMs returning JSON wrapped
    in markdown code blocks and provides consistent error handling.
    
    Args:
        response: Raw LLM response string
        expected_type: Expected Python type (dict, list, etc.)
        
    Returns:
        Parsed JSON data of the expected type
        
    Raises:
        ValueError: If JSON parsing fails or type validation fails
    """
    if not response:
        raise ValueError("Empty response received")
        
    response = response.strip()
    
    # Find JSON in the response (handle markdown code blocks)
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end == -1:
            logger.warning("Found ```json start marker but no closing ```")
            response = response[start:].strip()
        else:
            response = response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end == -1:
            logger.warning("Found ``` start marker but no closing ```")
            response = response[start:].strip()
        else:
            response = response[start:end].strip()
    
    # Parse the JSON
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {str(e)}")
        logger.debug(f"Raw response was: {repr(response[:500])}")
        raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")
    
    # Validate type
    if not isinstance(parsed, expected_type):
        type_name = getattr(expected_type, '__name__', str(expected_type))
        actual_type = type(parsed).__name__
        raise ValueError(f"Response must be a JSON {type_name}, got {actual_type}")
    
    return parsed



