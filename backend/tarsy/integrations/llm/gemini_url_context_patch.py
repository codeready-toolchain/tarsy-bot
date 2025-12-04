"""
Monkeypatch for Gemini tool support in langchain-google-genai.

This module patches LangChain's Google Gemini integration to support:
1. URL_CONTEXT tool (GoogleNativeTool.URL_CONTEXT) - not yet natively supported
2. JSON Schema type conversion for MCP tools (object → OBJECT, string → STRING)

PROBLEM 1 - URL_CONTEXT:
------------------------
LangChain's convert_to_genai_function_declarations() doesn't recognize url_context
as a native Google tool, causing "Invalid function name" errors when trying to use it.

PROBLEM 2 - JSON Schema Types:
------------------------------
MCP tools use standard JSON Schema format with lowercase types ("object", "string").
Google's Gemini API expects uppercase enum values ("OBJECT", "STRING").
LangChain's _dict_to_gapic_schema() fails with:
  "Invalid enum value TYPE.OBJECT for enum type google.ai.generativelanguage.v1beta.Type"

SOLUTION:
---------
This patch intercepts the tool conversion process to:
1. Manually attach url_context to the Google API Tool object
2. Transform JSON Schema types to uppercase before conversion

SCOPE:
------
- Only affects: Gemini models
- Does NOT affect: Other LLM providers
- Safe: Gracefully handles errors, won't break initialization

TODO: Remove this patch when langchain-google-genai adds native support
      (Track: https://github.com/langchain-ai/langchain-google/issues)
"""

import json
import logging
from typing import Any, Dict, List, Union
from tarsy.models.llm_models import GoogleNativeTool

logger = logging.getLogger(__name__)


def _convert_json_schema_types_to_gemini(schema: Any) -> Any:
    """
    Recursively convert JSON Schema type values to Gemini-compatible uppercase format.
    
    JSON Schema uses: "object", "string", "number", "integer", "boolean", "array", "null"
    Gemini API expects: "OBJECT", "STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "NULL"
    
    Args:
        schema: JSON Schema dictionary or any value
        
    Returns:
        Schema with converted type values
    """
    if not isinstance(schema, dict):
        return schema
    
    result = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, str):
            # Convert lowercase JSON Schema types to uppercase Gemini types
            result[key] = value.upper()
        elif key == "properties" and isinstance(value, dict):
            # Recursively convert property schemas
            result[key] = {
                prop_name: _convert_json_schema_types_to_gemini(prop_schema)
                for prop_name, prop_schema in value.items()
            }
        elif key == "items" and isinstance(value, dict):
            # Recursively convert array item schemas
            result[key] = _convert_json_schema_types_to_gemini(value)
        elif key == "additionalProperties" and isinstance(value, dict):
            # Recursively convert additionalProperties schema
            result[key] = _convert_json_schema_types_to_gemini(value)
        elif isinstance(value, dict):
            # Recursively convert any nested dicts
            result[key] = _convert_json_schema_types_to_gemini(value)
        elif isinstance(value, list):
            # Recursively convert lists (e.g., anyOf, oneOf)
            result[key] = [
                _convert_json_schema_types_to_gemini(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    
    return result


def _transform_tool_schemas(tools: List[Any]) -> List[Any]:
    """
    Transform tool schemas to be Gemini-compatible.
    
    Handles both OpenAI-style function tools and raw function declarations.
    
    Args:
        tools: List of tool definitions
        
    Returns:
        List of tools with transformed schemas
    """
    transformed = []
    for tool in tools:
        if isinstance(tool, dict):
            # OpenAI-style format: {"type": "function", "function": {...}}
            if tool.get("type") == "function" and "function" in tool:
                func = tool["function"]
                if "parameters" in func:
                    func["parameters"] = _convert_json_schema_types_to_gemini(func["parameters"])
                transformed.append(tool)
            # Direct function declaration format: {"name": ..., "parameters": ...}
            elif "name" in tool and "parameters" in tool:
                tool["parameters"] = _convert_json_schema_types_to_gemini(tool["parameters"])
                transformed.append(tool)
            else:
                # Pass through unchanged (e.g., native Google tools)
                transformed.append(tool)
        else:
            # Non-dict tools pass through unchanged
            transformed.append(tool)
    
    return transformed


def apply_url_context_patch() -> bool:
    """
    Apply monkeypatch to enable URL_CONTEXT and fix JSON Schema types in LangChain.
    
    This patch enables:
    1. GoogleNativeTool.URL_CONTEXT for Google/Gemini models
    2. JSON Schema type conversion (object → OBJECT) for MCP tools
    
    Returns:
        bool: True if patch was applied successfully, False otherwise
    """
    try:
        from langchain_google_genai import _function_utils, chat_models
        
        # Store original function
        _original_convert = _function_utils.convert_to_genai_function_declarations
        
        def _patched_convert_to_genai_function_declarations(tools):
            """Patched version that handles url_context and JSON Schema type conversion.
            
            Fixes two issues with LangChain's Gemini integration:
            1. URL_CONTEXT not recognized as native Google tool
            2. JSON Schema lowercase types ("object") not converted to Gemini uppercase ("OBJECT")
            
            Args:
                tools: Tools to convert (can be list, tuple, or single tool)
                
            Returns:
                gapic.Tool object with url_context properly attached
            """
            # Separate url_context tools from others
            # Note: Using string literal here as LangChain's API expects it
            URL_CONTEXT_KEY = GoogleNativeTool.URL_CONTEXT.value
            standard_tools = []
            url_context_config = None
            
            # Handle single tool or sequence
            if not isinstance(tools, (list, tuple)):
                tools_seq = [tools]
            else:
                tools_seq = list(tools)
                
            for tool in tools_seq:
                is_url_context = False
                if isinstance(tool, dict) and URL_CONTEXT_KEY in tool:
                    is_url_context = True
                    url_context_config = tool[URL_CONTEXT_KEY]
                
                if not is_url_context:
                    standard_tools.append(tool)
            
            # Transform JSON Schema types to Gemini-compatible uppercase format
            # This fixes "Invalid enum value TYPE.OBJECT" errors for MCP tools
            standard_tools = _transform_tool_schemas(standard_tools)
            
            # Call original conversion for standard tools
            if standard_tools:
                gapic_tool = _original_convert(standard_tools)
            else:
                # Create empty tool if only url_context was provided
                gapic_tool = _original_convert([])
                
            # Manually add url_context if present
            if url_context_config is not None:
                try:
                    gapic_tool.url_context = url_context_config
                except AttributeError:
                    # Graceful fallback if API structure changes
                    logger.warning(
                        "Failed to attach url_context to Google API Tool object. "
                        "The Google API structure may have changed."
                    )
                    
            return gapic_tool

        # Apply the patch to both modules (chat_models imports from _function_utils)
        _function_utils.convert_to_genai_function_declarations = _patched_convert_to_genai_function_declarations
        chat_models.convert_to_genai_function_declarations = _patched_convert_to_genai_function_declarations
        
        logger.info("Successfully applied Gemini tool patches for langchain-google-genai")
        return True
        
    except ImportError:
        # LangChain Google GenAI package not installed - this is fine
        logger.debug("langchain-google-genai not installed, skipping Gemini patches")
        return False
        
    except Exception as e:
        # Don't fail initialization if patch fails
        logger.warning(f"Failed to apply Gemini tool patches: {e}")
        return False

