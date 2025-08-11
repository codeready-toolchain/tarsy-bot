"""
Test suite for JSON parser utilities.

Tests the parse_llm_json_response function that handles LLM responses
with proper error handling and markdown code block extraction.
"""

import json
import pytest

from tarsy.agents.json_parser import parse_llm_json_response


class TestParseLLMJsonResponse:
    """Test parse_llm_json_response function."""

    def test_parse_simple_json_dict(self):
        """Test parsing simple JSON dictionary."""
        response = '{"key": "value", "number": 42}'
        result = parse_llm_json_response(response)
        assert result == {"key": "value", "number": 42}

    def test_parse_simple_json_list(self):
        """Test parsing simple JSON list."""
        response = '["item1", "item2", "item3"]'
        result = parse_llm_json_response(response, expected_type=list)
        assert result == ["item1", "item2", "item3"]

    def test_parse_json_with_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code block."""
        response = '''```json
{"action": "analyze", "tools": ["kubectl", "logs"]}
```'''
        result = parse_llm_json_response(response)
        assert result == {"action": "analyze", "tools": ["kubectl", "logs"]}

    def test_parse_json_with_generic_code_block(self):
        """Test parsing JSON wrapped in generic code block."""
        response = '''```
{"status": "ready", "count": 5}
```'''
        result = parse_llm_json_response(response)
        assert result == {"status": "ready", "count": 5}

    def test_parse_json_with_unclosed_markdown_block(self):
        """Test parsing JSON with unclosed markdown block."""
        response = '''```json
{"incomplete": "block"}'''
        result = parse_llm_json_response(response)
        assert result == {"incomplete": "block"}

    def test_parse_json_with_unclosed_generic_block(self):
        """Test parsing JSON with unclosed generic block."""
        response = '''```
{"also": "incomplete"}'''
        result = parse_llm_json_response(response)
        assert result == {"also": "incomplete"}

    def test_parse_json_with_whitespace(self):
        """Test parsing JSON with surrounding whitespace."""
        response = '''   
        {"clean": "data"}   
        '''
        result = parse_llm_json_response(response)
        assert result == {"clean": "data"}

    def test_parse_empty_response_raises_error(self):
        """Test that empty response raises ValueError."""
        with pytest.raises(ValueError, match="Empty response received"):
            parse_llm_json_response("")

    def test_parse_none_response_raises_error(self):
        """Test that None response raises ValueError."""
        with pytest.raises(ValueError, match="Empty response received"):
            parse_llm_json_response(None)

    def test_parse_invalid_json_raises_error(self):
        """Test that invalid JSON raises ValueError."""
        response = '{"invalid": json,}'
        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            parse_llm_json_response(response)

    def test_parse_wrong_type_raises_error(self):
        """Test that wrong expected type raises ValueError."""
        response = '["this", "is", "a", "list"]'
        with pytest.raises(ValueError, match="Response must be a JSON dict, got list"):
            parse_llm_json_response(response, expected_type=dict)

    def test_parse_complex_nested_json(self):
        """Test parsing complex nested JSON structure."""
        response = '''```json
{
    "analysis": {
        "status": "complete",
        "findings": [
            {"type": "error", "message": "Connection failed"},
            {"type": "warning", "message": "High latency"}
        ]
    },
    "recommendations": ["restart", "scale"]
}
```'''
        result = parse_llm_json_response(response)
        expected = {
            "analysis": {
                "status": "complete",
                "findings": [
                    {"type": "error", "message": "Connection failed"},
                    {"type": "warning", "message": "High latency"}
                ]
            },
            "recommendations": ["restart", "scale"]
        }
        assert result == expected

    def test_parse_json_with_text_before_and_after(self):
        """Test parsing JSON with surrounding text."""
        response = '''Here's the analysis result:
```json
{"result": "success"}
```
That's all!'''
        result = parse_llm_json_response(response)
        assert result == {"result": "success"}

    def test_type_validation_with_list(self):
        """Test type validation works correctly for lists."""
        response = '["tool1", "tool2"]'
        result = parse_llm_json_response(response, expected_type=list)
        assert result == ["tool1", "tool2"]
        assert isinstance(result, list)

    def test_type_validation_with_custom_type(self):
        """Test type validation with different built-in types."""
        # Test string
        response = '"hello world"'
        result = parse_llm_json_response(response, expected_type=str)
        assert result == "hello world"
        assert isinstance(result, str)

        # Test number
        response = '42'
        result = parse_llm_json_response(response, expected_type=int)
        assert result == 42
        assert isinstance(result, int)