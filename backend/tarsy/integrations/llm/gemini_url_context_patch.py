"""
Monkeypatch for URL_CONTEXT tool support in langchain-google-genai.

PROBLEM:
--------
LangChain's convert_to_genai_function_declarations() doesn't recognize url_context
as a native Google tool, causing "Invalid function name" errors when trying to use it.

SOLUTION:
---------
This patch intercepts the tool conversion process to manually attach url_context
to the Google API Tool object.

SCOPE:
------
- Only affects: Gemini models using LangChain (ReAct controllers)
- Does NOT affect: Native thinking controller (uses Google SDK directly)
- Safe: Gracefully handles errors, won't break initialization

NOTE: MCP function calling is handled by the native Google SDK in
      generate_response_with_native_thinking(), NOT through this LangChain patch.

TODO: Remove this patch when langchain-google-genai adds native url_context support
      (Track: https://github.com/langchain-ai/langchain-google/issues)
"""

import logging

from tarsy.models.llm_models import GoogleNativeTool

logger = logging.getLogger(__name__)


def apply_url_context_patch() -> bool:
    """
    Apply monkeypatch to enable URL_CONTEXT in LangChain's Gemini integration.
    
    This patch is only needed for the LangChain path (ReAct controllers)
    which binds native Google tools (google_search, url_context, code_execution).
    
    Returns:
        bool: True if patch was applied successfully, False otherwise
    """
    try:
        from langchain_google_genai import _function_utils, chat_models
        
        # Store original function
        _original_convert = _function_utils.convert_to_genai_function_declarations
        
        def _patched_convert_to_genai_function_declarations(tools):
            """Patched version that handles url_context native tool.
            
            Args:
                tools: Tools to convert (can be list, tuple, or single tool)
                
            Returns:
                gapic.Tool object with url_context properly attached
            """
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
                    logger.warning(
                        "Failed to attach url_context to Google API Tool object. "
                        "The Google API structure may have changed."
                    )
                    
            return gapic_tool

        # Apply the patch to both modules
        _function_utils.convert_to_genai_function_declarations = _patched_convert_to_genai_function_declarations
        chat_models.convert_to_genai_function_declarations = _patched_convert_to_genai_function_declarations
        
        logger.info("Successfully applied url_context patch for langchain-google-genai")
        return True
        
    except ImportError:
        logger.debug("langchain-google-genai not installed, skipping url_context patch")
        return False
        
    except Exception as e:
        logger.warning(f"Failed to apply url_context patch: {e}")
        return False

