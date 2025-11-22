"""
Monkeypatch for URL_CONTEXT support in langchain-google-genai.

This module patches LangChain's Google Gemini integration to support the URL_CONTEXT
tool (GoogleNativeTool.URL_CONTEXT), which is not yet natively supported in 
langchain-google-genai v2.1.5.

PROBLEM:
--------
LangChain's convert_to_genai_function_declarations() doesn't recognize url_context
as a native Google tool, causing "Invalid function name" errors when trying to use it.

SOLUTION:
---------
This patch intercepts the tool conversion process and manually attaches url_context
to the underlying Google API Tool object, bypassing LangChain's validation.

SCOPE:
------
- Only affects: Gemini models with GoogleNativeTool.URL_CONTEXT enabled
- Does NOT affect: Other LLM providers, other Gemini tools, function calling
- Safe: Gracefully handles errors, won't break initialization

TODO: Remove this patch when langchain-google-genai adds native url_context support
      (Track: https://github.com/langchain-ai/langchain-google/issues)
"""

import logging
from tarsy.models.llm_models import GoogleNativeTool

logger = logging.getLogger(__name__)


def apply_url_context_patch() -> bool:
    """
    Apply monkeypatch to enable URL_CONTEXT tool support in LangChain.
    
    Enables GoogleNativeTool.URL_CONTEXT for Google/Gemini models.
    
    Returns:
        bool: True if patch was applied successfully, False otherwise
    """
    try:
        from langchain_google_genai import _function_utils, chat_models
        
        # Store original function
        _original_convert = _function_utils.convert_to_genai_function_declarations
        
        def _patched_convert_to_genai_function_declarations(tools):
            """Patched version that handles url_context in tool dictionaries.
            
            LangChain's current version doesn't recognize GoogleNativeTool.URL_CONTEXT as a native
            Google tool. This patch intercepts the conversion process and manually
            attaches url_context to the Google API Tool object.
            
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
                tools_seq = tools
                
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
                    # Graceful fallback if API structure changes
                    logger.warning(
                        "Failed to attach url_context to Google API Tool object. "
                        "The Google API structure may have changed."
                    )
                    
            return gapic_tool

        # Apply the patch to both modules (chat_models imports from _function_utils)
        _function_utils.convert_to_genai_function_declarations = _patched_convert_to_genai_function_declarations
        chat_models.convert_to_genai_function_declarations = _patched_convert_to_genai_function_declarations
        
        logger.info("Successfully applied url_context patch for langchain-google-genai")
        return True
        
    except ImportError:
        # LangChain Google GenAI package not installed - this is fine
        logger.debug("langchain-google-genai not installed, skipping url_context patch")
        return False
        
    except Exception as e:
        # Don't fail initialization if patch fails
        logger.warning(f"Failed to apply url_context patch: {e}")
        return False

