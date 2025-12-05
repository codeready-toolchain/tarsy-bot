"""
Native Google tools configuration utilities.

This module provides shared functionality for configuring Google/Gemini native tools
(google_search, code_execution, url_context) used by both LangChain-based LLMClient
and the native GeminiNativeThinkingClient.
"""

from typing import TYPE_CHECKING, Dict, List, Optional

from google.genai import types as google_genai_types

from tarsy.models.llm_models import GoogleNativeTool
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.models.llm_models import LLMProviderConfig
    from tarsy.models.mcp_selection_models import NativeToolsConfig

logger = get_module_logger(__name__)


class NativeToolsHelper:
    """
    Handles native Google tools configuration and override logic.
    
    This utility centralizes the native tools configuration logic used by both
    LLMClient (LangChain) and GeminiNativeThinkingClient (Google SDK).
    
    Supports three native tools (GoogleNativeTool enum):
    - GOOGLE_SEARCH: Web search capability (enabled by default)
    - CODE_EXECUTION: Python code execution in sandbox (disabled by default)
    - URL_CONTEXT: URL grounding for specific web pages (enabled by default)
    
    Default behavior when not configured:
    - google_search and url_context are enabled
    - code_execution is disabled for security reasons
    """
    
    @staticmethod
    def get_effective_config(
        provider_config: 'LLMProviderConfig',
        override: Optional['NativeToolsConfig'] = None
    ) -> Dict[str, bool]:
        """
        Compute effective native tools configuration with tri-state override semantics.
        
        **Tri-state behavior per tool:**
        - `None` in override: Use provider default configuration
        - `True` in override: Explicitly enable (override provider default)
        - `False` in override: Explicitly disable (override provider default)
        
        Args:
            provider_config: LLM provider configuration with native tool defaults
            override: Optional session-level native tools configuration
            
        Returns:
            Dictionary mapping tool names to enabled status (tool_name -> bool)
        """
        # Start with provider defaults
        google_search_enabled = provider_config.get_native_tool_status(
            GoogleNativeTool.GOOGLE_SEARCH.value
        )
        code_execution_enabled = provider_config.get_native_tool_status(
            GoogleNativeTool.CODE_EXECUTION.value
        )
        url_context_enabled = provider_config.get_native_tool_status(
            GoogleNativeTool.URL_CONTEXT.value
        )
        
        # Apply session-level override if provided
        if override is not None:
            if override.google_search is not None:
                google_search_enabled = override.google_search
            if override.code_execution is not None:
                code_execution_enabled = override.code_execution
            if override.url_context is not None:
                url_context_enabled = override.url_context
        
        return {
            GoogleNativeTool.GOOGLE_SEARCH.value: google_search_enabled,
            GoogleNativeTool.CODE_EXECUTION.value: code_execution_enabled,
            GoogleNativeTool.URL_CONTEXT.value: url_context_enabled
        }
    
    @staticmethod
    def build_tool_objects(
        config: Dict[str, bool],
        provider_name: str = "unknown"
    ) -> Dict[str, Optional[google_genai_types.Tool]]:
        """
        Create Google SDK Tool objects from effective configuration.
        
        This method creates Tool objects for each enabled native tool. The returned
        dictionary maps tool names to Tool objects (or None if disabled).
        
        Used by LLMClient for binding tools to LangChain models.
        
        Args:
            config: Dictionary mapping tool names to enabled status
            provider_name: Provider name for logging (optional)
            
        Returns:
            Dictionary mapping tool names to Tool objects (or None if disabled)
        """
        tools: Dict[str, Optional[google_genai_types.Tool]] = {
            GoogleNativeTool.GOOGLE_SEARCH.value: None,
            GoogleNativeTool.CODE_EXECUTION.value: None,
            GoogleNativeTool.URL_CONTEXT.value: None
        }
        
        enabled_tools = []
        
        # Google Search tool
        if config.get(GoogleNativeTool.GOOGLE_SEARCH.value, False):
            try:
                tools[GoogleNativeTool.GOOGLE_SEARCH.value] = google_genai_types.Tool(
                    google_search=google_genai_types.GoogleSearch()
                )
                enabled_tools.append(GoogleNativeTool.GOOGLE_SEARCH.value)
            except Exception as e:
                logger.warning(
                    f"Failed to create {GoogleNativeTool.GOOGLE_SEARCH.value} tool "
                    f"for {provider_name}: {e}"
                )
        
        # Code Execution tool
        if config.get(GoogleNativeTool.CODE_EXECUTION.value, False):
            try:
                tools[GoogleNativeTool.CODE_EXECUTION.value] = google_genai_types.Tool(
                    code_execution={}
                )
                enabled_tools.append(GoogleNativeTool.CODE_EXECUTION.value)
            except Exception as e:
                logger.warning(
                    f"Failed to create {GoogleNativeTool.CODE_EXECUTION.value} tool "
                    f"for {provider_name}: {e}"
                )
        
        # URL Context tool
        if config.get(GoogleNativeTool.URL_CONTEXT.value, False):
            try:
                tools[GoogleNativeTool.URL_CONTEXT.value] = google_genai_types.Tool(
                    url_context={}
                )
                enabled_tools.append(GoogleNativeTool.URL_CONTEXT.value)
            except Exception as e:
                logger.warning(
                    f"Failed to create {GoogleNativeTool.URL_CONTEXT.value} tool "
                    f"for {provider_name}: {e}"
                )
        
        if enabled_tools:
            logger.debug(f"Built native tool objects for {provider_name}: {enabled_tools}")
        
        return tools
    
    @staticmethod
    def build_tool_list(
        config: Dict[str, bool],
        provider_name: str = "unknown"
    ) -> List[google_genai_types.Tool]:
        """
        Create a list of Google SDK Tool objects for enabled native tools.
        
        This method creates separate Tool objects for each enabled native tool.
        Used by GeminiNativeThinkingClient which needs a list format.
        
        Note: Standard generateContent API doesn't support multi-tool use
        (combining function calling with google_search/url_context/code_execution).
        When MCP tools are provided, caller should use MCP tools exclusively.
        
        Args:
            config: Dictionary mapping tool names to enabled status
            provider_name: Provider name for logging (optional)
            
        Returns:
            List of Tool objects for enabled native tools
        """
        tools: List[google_genai_types.Tool] = []
        enabled_tools: List[str] = []
        
        # Google Search tool
        if config.get(GoogleNativeTool.GOOGLE_SEARCH.value, False):
            try:
                tools.append(google_genai_types.Tool(
                    google_search=google_genai_types.GoogleSearch()
                ))
                enabled_tools.append(GoogleNativeTool.GOOGLE_SEARCH.value)
            except Exception as e:
                logger.warning(
                    f"Failed to create {GoogleNativeTool.GOOGLE_SEARCH.value} tool "
                    f"for {provider_name}: {e}"
                )
        
        # URL Context tool
        if config.get(GoogleNativeTool.URL_CONTEXT.value, False):
            try:
                tools.append(google_genai_types.Tool(
                    url_context=google_genai_types.UrlContext()
                ))
                enabled_tools.append(GoogleNativeTool.URL_CONTEXT.value)
            except Exception as e:
                logger.warning(
                    f"Failed to create {GoogleNativeTool.URL_CONTEXT.value} tool "
                    f"for {provider_name}: {e}"
                )
        
        # Code Execution tool
        if config.get(GoogleNativeTool.CODE_EXECUTION.value, False):
            try:
                tools.append(google_genai_types.Tool(
                    code_execution=google_genai_types.ToolCodeExecution()
                ))
                enabled_tools.append(GoogleNativeTool.CODE_EXECUTION.value)
            except Exception as e:
                logger.warning(
                    f"Failed to create {GoogleNativeTool.CODE_EXECUTION.value} tool "
                    f"for {provider_name}: {e}"
                )
        
        if enabled_tools:
            logger.debug(f"Built native tool list for {provider_name}: {enabled_tools}")
        
        return tools
    
    @staticmethod
    def log_override_applied(
        provider_name: str,
        config: Dict[str, bool],
        override: Optional['NativeToolsConfig'] = None
    ) -> None:
        """
        Log the effective native tools configuration after override.
        
        Args:
            provider_name: Provider name for logging context
            config: Effective configuration (after override)
            override: Optional override that was applied (for distinguishing defaults)
        """
        enabled = [name for name, enabled in config.items() if enabled]
        disabled = [name for name, enabled in config.items() if not enabled]
        
        # Determine which are from defaults vs explicit override
        from_defaults = []
        if override is not None:
            if override.google_search is None and config.get(GoogleNativeTool.GOOGLE_SEARCH.value):
                from_defaults.append(GoogleNativeTool.GOOGLE_SEARCH.value)
            if override.code_execution is None and config.get(GoogleNativeTool.CODE_EXECUTION.value):
                from_defaults.append(GoogleNativeTool.CODE_EXECUTION.value)
            if override.url_context is None and config.get(GoogleNativeTool.URL_CONTEXT.value):
                from_defaults.append(GoogleNativeTool.URL_CONTEXT.value)
        
        log_msg = f"Applied native tools config for {provider_name}: enabled={enabled}"
        if from_defaults:
            log_msg += f" (from provider defaults: {from_defaults})"
        if disabled:
            log_msg += f", disabled={disabled}"
        
        logger.info(log_msg)

