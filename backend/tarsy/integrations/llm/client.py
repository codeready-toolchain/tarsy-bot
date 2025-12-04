"""
Unified LLM client implementation using LangChain.
Handles all LLM providers through LangChain's abstraction.

HYBRID APPROACH FOR GOOGLE/GEMINI NATIVE TOOLS:
-----------------------------------------------
For Google/Gemini models, we use a hybrid approach combining:
1. LangChain's ChatGoogleGenerativeAI for multi-provider abstraction
2. NEW google.genai.types for tool definitions (modern format)
3. .bind() method to attach tools to model (not passed to astream)

This approach enables:
- Tool combination support (GoogleNativeTool enum: GOOGLE_SEARCH, CODE_EXECUTION, URL_CONTEXT)
- Modern tool format matching Google's official documentation
- Full LangChain compatibility across all providers

Note: LangChain's older protobuf-based approach (v1beta) does NOT support
tool combination. The NEW SDK types (google.genai.types) are required.
"""

import asyncio
import pprint
import traceback
from typing import Any, Dict, List, Optional

import httpx
import urllib3
from google.genai import (
    types as google_genai_types,  # Google SDK types for tool definitions
)
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_vertexai.model_garden import ChatAnthropicVertex
from langchain_openai import ChatOpenAI
from langchain_xai import ChatXAI

from tarsy.config.settings import Settings
from tarsy.hooks.hook_context import llm_interaction_context

# Apply url_context patch for Gemini models
# This enables url_context tool support which is not yet natively supported in LangChain
from tarsy.integrations.llm.gemini_url_context_patch import apply_url_context_patch
from tarsy.models.constants import LLMInteractionType, StreamingEventType
from tarsy.models.llm_models import GoogleNativeTool, LLMProviderConfig, LLMProviderType
from tarsy.models.mcp_selection_models import NativeToolsConfig
from tarsy.models.processing_context import ToolWithServer
from tarsy.models.unified_interactions import LLMConversation, MessageRole
from tarsy.utils.error_details import extract_error_details
from tarsy.utils.logger import get_module_logger

apply_url_context_patch()

# Suppress SSL warnings when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup logger for this module
logger = get_module_logger(__name__)

# Setup separate logger for LLM communications
llm_comm_logger = get_module_logger("llm.communications")

# Constants for Google code execution response parts
# These part types are returned by Google's native code execution tool
# See: https://ai.google.dev/gemini-api/docs/code-execution
CODE_EXECUTION_PART_EXECUTABLE = 'executable_code'
CODE_EXECUTION_PART_RESULT = 'code_execution_result'


# LLM Providers mapping using LangChain
def _create_openai_client(temp, api_key, model, disable_ssl_verification=False, base_url=None):
    """Create ChatOpenAI client with optional SSL verification disable and custom base URL.
    
    Note: stream_usage=True enables token usage tracking during streaming by adding
    usage metadata to the final chunk. Requires langchain-openai >= 0.1.9.
    """
    client_kwargs = {
        "model": model, 
        "temperature": temp, 
        "api_key": api_key,
        "stream_usage": True  # Enable token usage in streaming responses
    }
    
    # Only set base_url if explicitly provided, otherwise let LangChain use defaults
    if base_url:
        client_kwargs["base_url"] = base_url
    
    if disable_ssl_verification:
        client_kwargs["http_client"] = httpx.Client(verify=False)
        client_kwargs["http_async_client"] = httpx.AsyncClient(verify=False)
    
    return ChatOpenAI(**client_kwargs)

def _create_google_client(temp, api_key, model, disable_ssl_verification=False, base_url=None):
    """Create ChatGoogleGenerativeAI client."""
    client_kwargs = {
        "model": model, 
        "temperature": temp if temp is not None else 1.0,  # Default to 1.0 if not specified
        "google_api_key": api_key
    }
    # Note: ChatGoogleGenerativeAI may not support custom base_url or HTTP clients
    return ChatGoogleGenerativeAI(**client_kwargs)

def _create_xai_client(temp, api_key, model, disable_ssl_verification=False, base_url=None):
    """Create ChatXAI client."""
    client_kwargs = {
        "model": model, 
        "api_key": api_key, 
        "temperature": temp
    }
    if base_url:
        client_kwargs["base_url"] = base_url
    # Note: ChatXAI may not support custom HTTP clients - would need to verify
    return ChatXAI(**client_kwargs)

def _create_anthropic_client(temp, api_key, model, disable_ssl_verification=False, base_url=None):
    """Create ChatAnthropic client."""
    client_kwargs = {
        "model": model, 
        "api_key": api_key, 
        "temperature": temp
    }
    if base_url:
        client_kwargs["base_url"] = base_url
    # Note: ChatAnthropic may not support custom HTTP clients - would need to verify  
    return ChatAnthropic(**client_kwargs)

def _create_vertexai_client(temp, api_key, model, disable_ssl_verification=False, base_url=None):
    """Create ChatAnthropicVertex client for Claude models on Vertex AI.
    
    Authentication via GOOGLE_APPLICATION_CREDENTIALS env var pointing to service account JSON.
    Project and location extracted from api_key field (format: "project_id:location" or just "project_id").
    """
    # Parse project and location from api_key field
    # Expected format: "project_id:location" or "project_id" (defaults to us-east5)
    if ":" in api_key:
        project, location = api_key.split(":", 1)
    else:
        project = api_key
        location = "us-east5"  # Default region for Claude
    
    client_kwargs = {
        "model_name": model,
        "project": project,
        "location": location,
        "temperature": temp
    }
    
    return ChatAnthropicVertex(**client_kwargs)

LLM_PROVIDERS = {
    LLMProviderType.OPENAI.value: _create_openai_client,
    LLMProviderType.GOOGLE.value: _create_google_client,
    LLMProviderType.XAI.value: _create_xai_client,
    LLMProviderType.ANTHROPIC.value: _create_anthropic_client,
    LLMProviderType.VERTEXAI.value: _create_vertexai_client
}


class LLMClient:
    """Simple LLM client focused purely on communication with LLM providers via LangChain."""
    
    def __init__(self, provider_name: str, config: LLMProviderConfig, settings: Optional[Settings] = None):
        self.provider_name = provider_name
        self.config = config
        self.provider_config = config  # Store config for access to provider-specific settings
        self.model = config.model  # Direct field access on BaseModel
        # Strip whitespace from API key to avoid gRPC metadata errors
        self.api_key = (config.api_key or "").strip()
        self.temperature = config.temperature  # Field with default in BaseModel
        self.llm_client: Optional[BaseChatModel] = None
        self.settings = settings  # Store settings for feature flag access
        self.available: bool = False
        self._sqlite_warning_logged: bool = False
        # Store native tools for Google/Gemini models (GoogleNativeTool enum values)
        self.native_tools: Dict[str, Optional[google_genai_types.Tool]] = {
            GoogleNativeTool.GOOGLE_SEARCH.value: None,
            GoogleNativeTool.CODE_EXECUTION.value: None,
            GoogleNativeTool.URL_CONTEXT.value: None
        }
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the LangChain LLM client."""
        try:
            # Map provider name to provider type for LLM_PROVIDERS
            provider_type = self.config.type  # Direct field access on BaseModel
            
            if provider_type.value in LLM_PROVIDERS:
                if not self.api_key:
                    logger.warning(f"No API key provided for {self.provider_name}")
                    self.available = False
                    return
                
                disable_ssl_verification = self.config.disable_ssl_verification
                if disable_ssl_verification:
                    logger.warning(f"SSL verification is DISABLED for {self.provider_name} - use with caution!")
                
                base_url = self.config.base_url
                self.llm_client = LLM_PROVIDERS[provider_type.value](
                    self.temperature, 
                    self.api_key, 
                    self.model,
                    disable_ssl_verification,
                    base_url
                )
                
                # Initialize native tools for Google/Gemini models
                # Uses Google AI SDK types (google.genai.types) for tool definition format
                if provider_type == LLMProviderType.GOOGLE:
                    self._initialize_native_tools()
                
                self.available = True
                logger.info(f"Successfully initialized {self.provider_name} with LangChain")
            else:
                logger.error(f"Unknown LLM provider type: {provider_type.value} for provider: {self.provider_name}")
                self.available = False
        except Exception as e:
            import traceback
            logger.error(f"Failed to initialize {self.provider_name}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            self.available = False

    def _initialize_native_tools(self):
        """Initialize Google/Gemini native tools based on config.
        
        Supports three native tools (GoogleNativeTool enum):
        - GOOGLE_SEARCH: Web search capability (enabled by default)
        - CODE_EXECUTION: Python code execution in sandbox (disabled by default)
        - URL_CONTEXT: URL grounding for specific web pages (enabled by default)
        
        Default behavior when not configured:
        - google_search and url_context are enabled
        - code_execution is disabled for security reasons
        """
        enabled_tools = []
        
        try:
            # Google Search tool
            if self.config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value):
                self.native_tools[GoogleNativeTool.GOOGLE_SEARCH.value] = google_genai_types.Tool(
                    google_search=google_genai_types.GoogleSearch()
                )
                enabled_tools.append(GoogleNativeTool.GOOGLE_SEARCH.value)
        except Exception as e:
            logger.warning(f"Failed to initialize {GoogleNativeTool.GOOGLE_SEARCH.value} tool for {self.provider_name}: {e}")
        
        try:
            # Code Execution tool
            if self.config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value):
                self.native_tools[GoogleNativeTool.CODE_EXECUTION.value] = google_genai_types.Tool(
                    code_execution={}
                )
                enabled_tools.append(GoogleNativeTool.CODE_EXECUTION.value)
        except Exception as e:
            logger.warning(f"Failed to initialize {GoogleNativeTool.CODE_EXECUTION.value} tool for {self.provider_name}: {e}")
        
        try:
            # URL Context tool
            if self.config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value):
                self.native_tools[GoogleNativeTool.URL_CONTEXT.value] = google_genai_types.Tool(
                    url_context={}
                )
                enabled_tools.append(GoogleNativeTool.URL_CONTEXT.value)
        except Exception as e:
            logger.warning(f"Failed to initialize {GoogleNativeTool.URL_CONTEXT.value} tool for {self.provider_name}: {e}")
        
        if enabled_tools:
            logger.info(f"Successfully initialized native tools for {self.provider_name}: {enabled_tools}")
        else:
            logger.info(f"No native tools enabled for {self.provider_name}")

    def _apply_native_tools_override(
        self,
        override: NativeToolsConfig
    ) -> Dict[str, Optional[google_genai_types.Tool]]:
        """
        Apply per-session native tools override with tri-state semantics.
        
        Creates a temporary tools dictionary based on the override configuration.
        
        **Tri-state behavior per tool:**
        - `None`: Use provider default configuration
        - `True`: Explicitly enable (override provider default)
        - `False`: Explicitly disable (override provider default)
        
        Args:
            override: Session-level native tools configuration
            
        Returns:
            Dictionary of native tools with override applied (tool_name -> Tool or None)
        """
        overridden_tools = {
            GoogleNativeTool.GOOGLE_SEARCH.value: None,
            GoogleNativeTool.CODE_EXECUTION.value: None,
            GoogleNativeTool.URL_CONTEXT.value: None
        }
        
        enabled_tools = []
        enabled_from_defaults = []
        
        # Google Search tool
        should_enable_search = override.google_search if override.google_search is not None else \
                               self.config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value)
        
        if should_enable_search:
            try:
                overridden_tools[GoogleNativeTool.GOOGLE_SEARCH.value] = google_genai_types.Tool(
                    google_search=google_genai_types.GoogleSearch()
                )
                enabled_tools.append(GoogleNativeTool.GOOGLE_SEARCH.value)
                if override.google_search is None:
                    enabled_from_defaults.append(GoogleNativeTool.GOOGLE_SEARCH.value)
            except Exception as e:
                logger.warning(f"Failed to create {GoogleNativeTool.GOOGLE_SEARCH.value} tool override: {e}")
        
        # Code Execution tool
        should_enable_code = override.code_execution if override.code_execution is not None else \
                             self.config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value)
        
        if should_enable_code:
            try:
                overridden_tools[GoogleNativeTool.CODE_EXECUTION.value] = google_genai_types.Tool(
                    code_execution={}
                )
                enabled_tools.append(GoogleNativeTool.CODE_EXECUTION.value)
                if override.code_execution is None:
                    enabled_from_defaults.append(GoogleNativeTool.CODE_EXECUTION.value)
            except Exception as e:
                logger.warning(f"Failed to create {GoogleNativeTool.CODE_EXECUTION.value} tool override: {e}")
        
        # URL Context tool
        should_enable_url = override.url_context if override.url_context is not None else \
                            self.config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value)
        
        if should_enable_url:
            try:
                overridden_tools[GoogleNativeTool.URL_CONTEXT.value] = google_genai_types.Tool(
                    url_context={}
                )
                enabled_tools.append(GoogleNativeTool.URL_CONTEXT.value)
                if override.url_context is None:
                    enabled_from_defaults.append(GoogleNativeTool.URL_CONTEXT.value)
            except Exception as e:
                logger.warning(f"Failed to create {GoogleNativeTool.URL_CONTEXT.value} tool override: {e}")
        
        log_msg = f"Applied native tools override for {self.provider_name}: enabled={enabled_tools}"
        if enabled_from_defaults:
            log_msg += f" (from provider defaults: {enabled_from_defaults})"
        disabled = [name for name, tool in overridden_tools.items() if tool is None]
        if disabled:
            log_msg += f", disabled={disabled}"
        logger.info(log_msg)
        
        return overridden_tools

    def _convert_mcp_tools_for_binding(
        self,
        available_tools: List[ToolWithServer]
    ) -> List[Dict[str, Any]]:
        """
        Convert MCP tools to format compatible with LangChain's .bind(tools=...).
        
        Uses OpenAI-style format which is then processed by our Gemini patch
        to handle JSON Schema type conversion (object → OBJECT).
        
        Function names use double underscore separator (server__tool_name) to
        avoid conflicts with dots in tool names while remaining valid identifiers.
        
        Args:
            available_tools: List of MCP tools with server context
            
        Returns:
            List of tool definitions in OpenAI-style dict format
        """
        tools = []
        
        for tool_with_server in available_tools:
            try:
                # Use server__tool_name as function name (double underscore separator)
                # This avoids dots which aren't valid in function names
                func_name = f"{tool_with_server.server}__{tool_with_server.tool.name}"
                
                # Get the input schema, defaulting to empty object if not specified
                input_schema = tool_with_server.tool.inputSchema or {"type": "object", "properties": {}}
                
                # Create tool definition in OpenAI-style format
                # Our Gemini patch converts JSON Schema types (object → OBJECT) during binding
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "description": tool_with_server.tool.description or f"Tool {tool_with_server.tool.name} from {tool_with_server.server}",
                        "parameters": input_schema
                    }
                }
                tools.append(tool_def)
                
                logger.debug(f"Converted MCP tool for binding: {func_name}")
                
            except Exception as e:
                logger.warning(f"Failed to convert MCP tool {tool_with_server.server}.{tool_with_server.tool.name}: {e}")
                continue
        
        logger.info(f"Converted {len(tools)} MCP tools for binding")
        return tools

    def _convert_conversation_to_langchain(self, conversation: LLMConversation) -> List:
        """Convert typed conversation to LangChain message objects."""
        langchain_messages = []
        for msg in conversation.messages:
            if msg.role == MessageRole.SYSTEM:
                langchain_messages.append(SystemMessage(content=msg.content))
            elif msg.role == MessageRole.USER:
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                langchain_messages.append(AIMessage(content=msg.content))
        return langchain_messages
    
    async def generate_response(
        self,
        conversation: LLMConversation,
        session_id: str,
        stage_execution_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        interaction_type: Optional[str] = None,
        max_retries: int = 3,
        timeout_seconds: int = 120,
        mcp_event_id: Optional[str] = None,
        native_tools_override: Optional[NativeToolsConfig] = None
    ) -> LLMConversation:
        """
        Generate response with streaming to WebSocket.
        
        Uses streaming API (.astream) in all environments for consistency.
        Event publishing automatically disabled in SQLite/dev mode via publish_transient.
        
        Includes retry logic:
        - Timeout protection (default: 120s, increased for code execution scenarios)
        - Rate limit retry with exponential backoff
        - Timeout retry with increasing delays
        - Empty response handling
        
        Args:
            conversation: The conversation to generate a response for
            session_id: Session ID for tracking
            stage_execution_id: Optional stage execution ID
            max_tokens: Optional max tokens configuration for LLM
            interaction_type: Optional interaction type (investigation, summarization, final_analysis).
                            If None, auto-detects based on response content.
            max_retries: Maximum number of retry attempts (default: 3)
            timeout_seconds: Timeout for LLM streaming call (default: 120s).
                           Increased from 60s to accommodate code execution which can take up to
                           30s per execution plus multiple regeneration rounds (up to 5x).
            mcp_event_id: Optional MCP event ID if summarizing a tool result
            native_tools_override: Optional per-session native tools configuration override.
                                 When specified, completely replaces provider's default native tools
                                 settings for this request (Google/Gemini only).
        
        Returns:
            Updated conversation with assistant response appended
        """
        if not self.available or not self.llm_client:
            raise Exception(f"{self.provider_name} client not available")
        
        # Prepare request data for typed context (ensure JSON serializable)
        request_data = {
            'messages': [msg.model_dump() for msg in conversation.messages],
            'model': self.model,
            'provider': self.provider_name,
            'temperature': self.temperature
        }
        
        # Prepare native tools config for audit trail (Google/Gemini only)
        # Apply session-level override if provided
        native_tools_config = None
        active_native_tools = self.native_tools  # Default to provider config
        
        if self.config.type == LLMProviderType.GOOGLE:
            # Apply override if provided (session-level takes precedence)
            if native_tools_override is not None:
                active_native_tools = self._apply_native_tools_override(native_tools_override)
                logger.info(f"Using session-level native tools override for {session_id}")
            
            # Capture effective config for audit trail
            native_tools_config = {
                GoogleNativeTool.GOOGLE_SEARCH.value: bool(active_native_tools[GoogleNativeTool.GOOGLE_SEARCH.value]),
                GoogleNativeTool.CODE_EXECUTION.value: bool(active_native_tools[GoogleNativeTool.CODE_EXECUTION.value]),
                GoogleNativeTool.URL_CONTEXT.value: bool(active_native_tools[GoogleNativeTool.URL_CONTEXT.value])
            }
        
        # Use typed hook context for clean data flow
        async with llm_interaction_context(session_id, request_data, stage_execution_id, native_tools_config) as ctx:
            # Get request ID for logging  
            request_id = ctx.get_request_id()

            # Log the outgoing conversation
            llm_comm_logger.debug(f"=== LLM REQUEST [{self.provider_name}] [ID: {request_id}] ===")

            # Retry loop for resilience
            for attempt in range(max_retries + 1):
                try:
                    # Convert typed conversation to LangChain format  
                    langchain_messages = self._convert_conversation_to_langchain(conversation)
                    accumulated_content = ""
                    
                    # Streaming state (for thoughts, final answers, and summarizations)
                    is_streaming_thought = False
                    is_streaming_final_answer = False
                    is_streaming_summarization = False
                    token_count_since_last_send = 0
                    THOUGHT_CHUNK_SIZE = 1  # Faster streaming for plain text thoughts
                    FINAL_ANSWER_CHUNK_SIZE = 3  # Reduced but still stable for markdown
                    SUMMARIZATION_CHUNK_SIZE = 1  # Faster streaming for plain text summaries
                    
                    # Check if we should stream as plain text summarization
                    if interaction_type == LLMInteractionType.SUMMARIZATION.value:
                        is_streaming_summarization = True
                        logger.debug(f"Streaming plain text summarization for {session_id}")
                    
                    # Stream tokens with timeout protection
                    # Token usage tracking uses dual approach:
                    # 1. Chunk aggregation (OpenAI with stream_usage=True) - primary
                    # 2. UsageMetadataCallbackHandler - fallback for other providers
                    callback = UsageMetadataCallbackHandler()
                    config = {"callbacks": [callback]}
                    if max_tokens is not None:
                        config["max_tokens"] = max_tokens
                    
                    # HYBRID APPROACH: Bind native tools to model using Google AI SDK types
                    # Tools are converted to dicts and bound to the model, not passed to astream()
                    # Supports multiple tools: GoogleNativeTool enum (GOOGLE_SEARCH, CODE_EXECUTION, URL_CONTEXT)
                    # Uses active_native_tools which may be overridden at session level
                    llm_with_tools = self.llm_client
                    code_execution_enabled = False
                    
                    if self.config.type == LLMProviderType.GOOGLE:
                        # Collect all enabled native tools (from active config which may be overridden)
                        active_tools = [tool for tool in active_native_tools.values() if tool is not None]
                        # Check if code execution is specifically enabled
                        code_execution_enabled = active_native_tools.get(GoogleNativeTool.CODE_EXECUTION.value) is not None
                        
                        if active_tools:
                            try:
                                # Convert all Google AI SDK tools to dicts and bind to model
                                tools_as_dicts = [t.model_dump(exclude_none=True) for t in active_tools]
                                llm_with_tools = self.llm_client.bind(tools=tools_as_dicts)
                                tool_names = [k for k, v in active_native_tools.items() if v is not None]
                                logger.info(f"Bound native tools to {self.provider_name} model: {tool_names}")
                            except Exception as e:
                                logger.error(f"Failed to bind native tools: {e}, continuing without tools")
                                llm_with_tools = self.llm_client
                    
                    # Aggregate chunks for usage metadata (OpenAI stream_usage=True approach)
                    aggregate_chunk = None
                    
                    # Wrap streaming with timeout protection (Python 3.11+)
                    async with asyncio.timeout(timeout_seconds):
                        async for chunk in llm_with_tools.astream(langchain_messages, config=config):
                            # Aggregate chunks by adding them together
                            # This properly accumulates usage_metadata across all chunks
                            aggregate_chunk = chunk if aggregate_chunk is None else aggregate_chunk + chunk
                            
                            # Extract token content, filtering out code execution parts if enabled
                            # This preserves ReAct format by only accumulating text content
                            token = self._extract_token_content(chunk, filter_code_execution=code_execution_enabled)
                            accumulated_content += token
                            
                            # Detect start of "Thought:" streaming (disabled during summarization)
                            if (not is_streaming_summarization) and (not is_streaming_thought) and (not is_streaming_final_answer):
                                if "Thought:" in accumulated_content and "Final Answer:" not in accumulated_content:
                                    is_streaming_thought = True
                                    token_count_since_last_send = 0
                                    logger.debug(f"Started streaming thought for {session_id}")
                            
                            # Check if we should STOP streaming thought
                            if is_streaming_thought and ("Action:" in accumulated_content or "Final Answer:" in accumulated_content):
                                # Extract clean thought content (everything between "Thought:" and stop marker)
                                thought_start_idx = accumulated_content.find("Thought:")
                                stop_idx = accumulated_content.find("Action:") if "Action:" in accumulated_content else accumulated_content.find("Final Answer:")
                                clean_thought = accumulated_content[thought_start_idx + len("Thought:"):stop_idx].strip()
                                
                                # Send final complete thought
                                if clean_thought:
                                    await self._publish_stream_chunk(
                                        session_id, stage_execution_id,
                                        StreamingEventType.THOUGHT, clean_thought,
                                        is_complete=True
                                    )
                                else:
                                    # Send completion marker
                                    await self._publish_stream_chunk(
                                        session_id, stage_execution_id,
                                        StreamingEventType.THOUGHT, "",
                                        is_complete=True
                                    )
                                is_streaming_thought = False
                                token_count_since_last_send = 0
                                logger.debug(f"Stopped streaming thought for {session_id}")
                                
                                # If "Final Answer:" detected, start streaming it
                                if "Final Answer:" in accumulated_content:
                                    is_streaming_final_answer = True
                                    token_count_since_last_send = 0
                                    logger.debug(f"Started streaming final answer for {session_id}")
                                
                                continue  # Skip token accumulation for this iteration
                            
                            # Send periodic updates with ENTIRE content (not just new tokens)
                            if is_streaming_thought or is_streaming_final_answer or is_streaming_summarization:
                                token_count_since_last_send += 1
                                
                                # Determine chunk size based on what we're streaming
                                if is_streaming_thought:
                                    current_chunk_size = THOUGHT_CHUNK_SIZE
                                elif is_streaming_final_answer:
                                    current_chunk_size = FINAL_ANSWER_CHUNK_SIZE
                                else:  # is_streaming_summarization
                                    current_chunk_size = SUMMARIZATION_CHUNK_SIZE
                                
                                # Send entire content every N tokens
                                if token_count_since_last_send >= current_chunk_size:
                                    if is_streaming_thought:
                                        thought_start_idx = accumulated_content.find("Thought:")
                                        current_thought = accumulated_content[thought_start_idx + len("Thought:"):].lstrip()
                                        
                                        # Check if Action: or Final Answer: appeared (strip them from streaming)
                                        # This handles cases where LLM doesn't put them on new lines
                                        if "Action:" in current_thought:
                                            current_thought = current_thought[:current_thought.find("Action:")].strip()
                                        elif "Final Answer:" in current_thought:
                                            current_thought = current_thought[:current_thought.find("Final Answer:")].strip()
                                        
                                        if current_thought:
                                            await self._publish_stream_chunk(
                                                session_id, stage_execution_id,
                                                StreamingEventType.THOUGHT, current_thought,
                                                is_complete=False
                                            )
                                    
                                    elif is_streaming_final_answer:
                                        final_answer_start_idx = accumulated_content.find("Final Answer:")
                                        current_final_answer = accumulated_content[final_answer_start_idx + len("Final Answer:"):].lstrip()
                                        
                                        if current_final_answer:
                                            await self._publish_stream_chunk(
                                                session_id, stage_execution_id,
                                                StreamingEventType.FINAL_ANSWER, current_final_answer,
                                                is_complete=False
                                            )
                                    
                                    elif is_streaming_summarization:
                                        # Stream entire accumulated content as plain text
                                        if accumulated_content.strip():
                                            await self._publish_stream_chunk(
                                                session_id, stage_execution_id,
                                                StreamingEventType.SUMMARIZATION, accumulated_content.strip(),
                                                is_complete=False,
                                                mcp_event_id=mcp_event_id
                                            )
                                    
                                    token_count_since_last_send = 0
                    
                    # Send final complete content if streaming is still active (after stream completes)
                    if is_streaming_thought:
                        thought_start_idx = accumulated_content.find("Thought:")
                        final_thought = accumulated_content[thought_start_idx + len("Thought:"):].strip()
                        
                        # Strip any trailing Action: or Final Answer: (in case LLM didn't put them on new lines)
                        if "Action:" in final_thought:
                            final_thought = final_thought[:final_thought.find("Action:")].strip()
                        elif "Final Answer:" in final_thought:
                            final_thought = final_thought[:final_thought.find("Final Answer:")].strip()
                        
                        if final_thought:
                            await self._publish_stream_chunk(
                                session_id, stage_execution_id,
                                StreamingEventType.THOUGHT, final_thought,
                                is_complete=True
                            )
                        else:
                            # Send completion marker
                            await self._publish_stream_chunk(
                                session_id, stage_execution_id,
                                StreamingEventType.THOUGHT, "",
                                is_complete=True
                            )
                    
                    # Send final complete final answer if streaming is still active
                    if is_streaming_final_answer:
                        final_answer_start_idx = accumulated_content.find("Final Answer:")
                        final_answer = accumulated_content[final_answer_start_idx + len("Final Answer:"):].strip()
                        
                        if final_answer:
                            await self._publish_stream_chunk(
                                session_id, stage_execution_id,
                                StreamingEventType.FINAL_ANSWER, final_answer,
                                is_complete=True
                            )
                        else:
                            # Send completion marker
                            await self._publish_stream_chunk(
                                session_id, stage_execution_id,
                                StreamingEventType.FINAL_ANSWER, "",
                                is_complete=True
                            )
                    
                    # Send final complete summarization if streaming is still active
                    if is_streaming_summarization:
                        final_summarization = accumulated_content.strip()
                        
                        if final_summarization:
                            await self._publish_stream_chunk(
                                session_id, stage_execution_id,
                                StreamingEventType.SUMMARIZATION, final_summarization,
                                is_complete=True,
                                mcp_event_id=mcp_event_id
                            )
                        else:
                            # Send completion marker
                            await self._publish_stream_chunk(
                                session_id, stage_execution_id,
                                StreamingEventType.SUMMARIZATION, "",
                                is_complete=True,
                                mcp_event_id=mcp_event_id
                            )
                    
                    # Check for empty response and retry if needed
                    if not accumulated_content or accumulated_content.strip() == "":
                        if attempt < max_retries:
                            logger.warning(f"Empty LLM response (attempt {attempt + 1}/{max_retries + 1}), retrying in 3s")
                            await asyncio.sleep(3)
                            continue  # Retry
                        else:
                            # Inject descriptive error message on final attempt
                            logger.warning("Empty LLM response on final attempt, injecting error message")
                            accumulated_content = f"⚠️ **LLM Response Error**\n\nThe {self.provider_name} LLM returned empty responses after {max_retries + 1} attempts. This may be due to:\n- Temporary provider issues\n- API rate limiting\n- Model overload\n\nPlease try processing this alert again in a few moments."
                    
                    # Extract usage metadata from aggregated chunk (OpenAI stream_usage=True)
                    chunk_usage = None
                    if aggregate_chunk and hasattr(aggregate_chunk, 'usage_metadata'):
                        chunk_usage = aggregate_chunk.usage_metadata
                        logger.debug(f"Extracted usage metadata from aggregated chunk: {chunk_usage}")
                    
                    # Store usage metadata (from aggregated chunks or callback)
                    self._store_usage_metadata(ctx, callback, chunk_usage)
                    
                    # Extract complete response metadata from aggregated chunk
                    if aggregate_chunk and hasattr(aggregate_chunk, 'response_metadata'):
                        ctx.interaction.response_metadata = aggregate_chunk.response_metadata
                        try:
                            keys = list(aggregate_chunk.response_metadata.keys()) if aggregate_chunk.response_metadata else []
                            logger.debug(f"Captured response metadata with keys: {keys if keys else 'none'}")
                        except (TypeError, AttributeError):
                            # Handle cases where response_metadata is not a dict (e.g., in tests)
                            logger.debug("Captured response metadata (keys unavailable)")
                    
                    # For Google code execution, extract structured parts from chunk content
                    # ONLY extract if code execution is actually enabled to avoid unnecessary processing
                    # Google returns parts with types defined in CODE_EXECUTION_PART_* constants
                    # See: https://ai.google.dev/gemini-api/docs/code-execution
                    if code_execution_enabled and aggregate_chunk and hasattr(aggregate_chunk, 'content'):
                        content = aggregate_chunk.content
                        if isinstance(content, list):
                            # Extract parts array from list content
                            parts = []
                            for item in content:
                                if isinstance(item, dict):
                                    parts.append(item)
                                elif hasattr(item, '__dict__'):
                                    # Convert object to dict
                                    parts.append(vars(item))
                            
                            # Add parts to response_metadata if we found any structured content
                            if parts:
                                if ctx.interaction.response_metadata is None:
                                    ctx.interaction.response_metadata = {}
                                if not isinstance(ctx.interaction.response_metadata, dict):
                                    ctx.interaction.response_metadata = {}
                                ctx.interaction.response_metadata['parts'] = parts
                                logger.debug(f"Captured {len(parts)} structured parts from content for code execution")
                    
                    # Finalize conversation and interaction
                    self._finalize_conversation(ctx, conversation, accumulated_content, interaction_type, mcp_event_id)
                    
                    # Complete the typed context with success
                    await ctx.complete_success({})
                    
                    # Success - break out of retry loop
                    return conversation
                
                except asyncio.TimeoutError:
                    # Handle timeout - will retry up to max_retries with 5s delay between attempts
                    logger.error(f"LLM streaming timed out after {timeout_seconds}s (attempt {attempt + 1}/{max_retries + 1})")
                    if attempt < max_retries:
                        logger.warning("Retrying after timeout in 5s...")
                        await asyncio.sleep(5)
                        continue  # Retry
                    else:
                        logger.error(f"LLM streaming timed out after {max_retries + 1} attempts")
                        self._log_llm_detailed_error(TimeoutError(f"LLM streaming timed out after {timeout_seconds}s"), request_id)
                        raise TimeoutError(f"LLM streaming timed out after {timeout_seconds}s on all {max_retries + 1} attempts") from None
                
                except Exception as e:
                    # Check if this is a rate limit error
                    error_str = str(e).lower()
                    is_rate_limit = any(indicator in error_str for indicator in [
                        "429", "rate limit", "quota", "too many requests", "rate_limit_exceeded"
                    ])
                    
                    if is_rate_limit and attempt < max_retries:
                        # Extract retry delay from error if available
                        retry_delay = self._extract_retry_delay(str(e))
                        if retry_delay is None:
                            # Exponential backoff: 2^attempt seconds (1s, 2s, 4s)
                            retry_delay = (2 ** attempt)
                        
                        logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}), retrying in {retry_delay}s")
                        await asyncio.sleep(retry_delay)
                        continue  # Retry
                    else:
                        # Log detailed error for non-rate-limit errors or max retries reached
                        self._log_llm_detailed_error(e, request_id)
                        
                        # Create enhanced error message
                        error_details = extract_error_details(e)
                        enhanced_message = f"{self.provider_name} API error: {str(e)}"
                        if error_details:
                            enhanced_message += f" | Details: {error_details}"
                        
                        if is_rate_limit:
                            enhanced_message += f" (max retries {max_retries + 1} exhausted)"
                        
                        raise Exception(enhanced_message) from e

    def _contains_final_answer(self, conversation: LLMConversation) -> bool:
        """
        Check if the LAST message is from assistant and contains 'Final Answer:'.
        
        Uses the centralized ReAct parser to determine if the response contains
        a final answer, ensuring consistency across the codebase.
        
        Args:
            conversation: The conversation to check
            
        Returns:
            True if last message is assistant with "Final Answer:", False otherwise
        """
        if not conversation.messages:
            return False
        
        # Check LAST message only
        last_msg = conversation.messages[-1]
        
        # Must be from assistant
        if last_msg.role != MessageRole.ASSISTANT:
            return False
        
        # Use the centralized ReAct parser to determine if this is a final answer
        # This ensures all Final Answer detection logic is in one place
        from tarsy.agents.parsers.react_parser import ReActParser
        
        parsed = ReActParser.parse_response(last_msg.content)
        return parsed.is_final_answer
    
    def get_max_tool_result_tokens(self) -> int:
        """Return the maximum tool result tokens for the current provider."""
        return self.provider_config.max_tool_result_tokens  # Already an int with BaseModel validation
    
    def _extract_token_content(self, chunk: Any, filter_code_execution: bool = False) -> str:
        """
        Extract string content from LLM chunk, handling various provider formats.
        
        Some providers return lists of content blocks that need to be flattened.
        When filter_code_execution is True, filters out executable_code and 
        code_execution_result parts to preserve ReAct format.
        
        Args:
            chunk: Raw chunk from LLM stream
            filter_code_execution: If True, skip code execution parts (for Google native tool)
            
        Returns:
            String content extracted from chunk (text only when filtering)
        """
        token = (chunk.content if hasattr(chunk, "content") else str(chunk)) or ""
        
        # Handle list content (some providers return lists)
        if isinstance(token, list):
            token_str = ""
            for block in token:
                # Skip code execution parts if filtering is enabled
                # These parts are captured in metadata but shouldn't be in streamed content
                if filter_code_execution:
                    if isinstance(block, dict):
                        # Skip code execution parts using constants
                        if CODE_EXECUTION_PART_EXECUTABLE in block or CODE_EXECUTION_PART_RESULT in block:
                            continue
                    elif hasattr(block, CODE_EXECUTION_PART_EXECUTABLE) or hasattr(block, CODE_EXECUTION_PART_RESULT):
                        continue
                
                # Extract text content
                if isinstance(block, str):
                    token_str += block
                elif isinstance(block, dict) and 'text' in block:
                    token_str += block['text'] or ""
                elif hasattr(block, 'text'):
                    token_str += block.text or ""
                elif not filter_code_execution:
                    # Only stringify unknown blocks if not filtering
                    token_str += str(block)
            return token_str
        
        # Defensive str() coercion for future-proofing against potential library API shifts
        return str(token) if not isinstance(token, str) else token
    
    def _store_usage_metadata(
        self, 
        ctx: Any, 
        callback: UsageMetadataCallbackHandler, 
        chunk_usage: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Extract and store token usage metadata in interaction.
        
        Token usage is extracted from aggregated streaming chunks or callback handler:
        
        **Priority 1** - Aggregated chunk metadata (OpenAI stream_usage=True):
          When stream_usage=True is enabled, chunks are aggregated using the + operator.
          The final aggregate contains complete usage_metadata with input/output/total tokens.
          This is the preferred approach as it's provider-native.
        
        **Priority 2** - UsageMetadataCallbackHandler (fallback):
          For providers without stream_usage support, the callback handler captures
          metadata. It stores usage keyed by model name, so we extract the first entry.
        
        Stores token counts as None instead of 0 for cleaner database representation.
        
        Args:
            ctx: LLM interaction context with interaction attribute to store tokens
            callback: UsageMetadataCallbackHandler that may have captured metadata
            chunk_usage: Optional usage metadata from aggregated streaming chunk
        """
        usage_metadata = None
        
        # Priority 1: Check final chunk usage (OpenAI stream_usage=True)
        if chunk_usage:
            usage_metadata = chunk_usage
            logger.debug(f"Using token usage from streaming chunk: {usage_metadata}")
        # Priority 2: Check callback's usage_metadata attribute (standard approach)
        elif hasattr(callback, 'usage_metadata') and callback.usage_metadata:
            # callback.usage_metadata is a dict keyed by model name
            # Extract the first (and usually only) model's usage
            callback_data = callback.usage_metadata
            if isinstance(callback_data, dict) and callback_data:
                # Get the first model's usage data
                model_usage = next(iter(callback_data.values()), None)
                if model_usage:
                    usage_metadata = model_usage
                    logger.debug(f"Using token usage from callback handler: {usage_metadata}")
        
        if usage_metadata and isinstance(usage_metadata, dict):
            # Safely extract token counts (ensure they're integers)
            input_tokens = usage_metadata.get('input_tokens', 0)
            output_tokens = usage_metadata.get('output_tokens', 0)
            total_tokens = usage_metadata.get('total_tokens', 0)
            
            # Ensure we have integers (handle potential None or other types)
            try:
                input_tokens = int(input_tokens) if input_tokens is not None else 0
                output_tokens = int(output_tokens) if output_tokens is not None else 0
                total_tokens = int(total_tokens) if total_tokens is not None else 0
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid token usage data types: {e}")
                return
            
            # Store token data (use None instead of 0 for cleaner database storage)
            ctx.interaction.input_tokens = input_tokens if input_tokens > 0 else None
            ctx.interaction.output_tokens = output_tokens if output_tokens > 0 else None
            ctx.interaction.total_tokens = total_tokens if total_tokens > 0 else None
            
            logger.debug(
                f"Stored token usage: input={input_tokens}, "
                f"output={output_tokens}, total={total_tokens}"
            )
        else:
            # Some providers may not support token usage metadata
            logger.debug(f"No token usage metadata available for {self.provider_name}")
    
    def _finalize_conversation(
        self,
        ctx: Any,
        conversation: LLMConversation,
        accumulated_content: str,
        interaction_type: Optional[str],
        mcp_event_id: Optional[str] = None
    ) -> None:
        """
        Finalize conversation by adding assistant message and updating interaction.
        
        Args:
            ctx: LLM interaction context
            conversation: Conversation object to update
            accumulated_content: Complete LLM response content
            interaction_type: Optional explicit interaction type
            mcp_event_id: Optional MCP event ID if summarizing a tool result
        """
        # Add assistant response to conversation
        conversation.append_assistant_message(accumulated_content)
        
        # Update the interaction with conversation data
        ctx.interaction.conversation = conversation
        ctx.interaction.provider = self.provider_name
        ctx.interaction.model_name = self.model
        ctx.interaction.temperature = self.temperature
        
        # Store MCP event ID if provided (for summarizations)
        if mcp_event_id is not None:
            ctx.interaction.mcp_event_id = mcp_event_id
        
        # Determine interaction type
        if interaction_type is not None:
            # Explicit type provided - use as-is
            ctx.interaction.interaction_type = interaction_type
        else:
            # No type provided - auto-detect
            if self._contains_final_answer(conversation):
                ctx.interaction.interaction_type = LLMInteractionType.FINAL_ANALYSIS.value
            else:
                ctx.interaction.interaction_type = LLMInteractionType.INVESTIGATION.value
    
    async def _publish_stream_chunk(
        self,
        session_id: str,
        stage_execution_id: Optional[str],
        stream_type: StreamingEventType,
        chunk: str,
        is_complete: bool,
        mcp_event_id: Optional[str] = None
    ) -> None:
        """Publish streaming chunk via transient channel."""
        # Check if streaming is enabled via config flag
        if self.settings and not self.settings.enable_llm_streaming:
            # Streaming disabled by config - return early without warning (expected behavior)
            return
        
        try:
            from tarsy.database.init_db import get_async_session_factory
            from tarsy.models.event_models import LLMStreamChunkEvent
            from tarsy.services.events.publisher import publish_transient_event
            from tarsy.utils.timestamp import now_us
            
            async_session_factory = get_async_session_factory()
            async with async_session_factory() as session:
                # Check database dialect to warn about SQLite limitations
                db_dialect = session.bind.dialect.name
                
                if db_dialect != "postgresql":
                    # Only log warning once per session (on first chunk)
                    if not self._sqlite_warning_logged:
                        logger.warning(
                            f"LLM streaming requested but database is {db_dialect}. "
                            "Real-time streaming requires PostgreSQL with NOTIFY support. "
                            "Events will be published but may not be delivered in real time."
                        )
                        self._sqlite_warning_logged = True
                
                event = LLMStreamChunkEvent(
                    session_id=session_id,
                    stage_execution_id=stage_execution_id,
                    chunk=chunk,
                    stream_type=stream_type.value,
                    is_complete=is_complete,
                    mcp_event_id=mcp_event_id,
                    timestamp_us=now_us()
                )
                
                await publish_transient_event(
                    session, 
                    f"session:{session_id}", 
                    event
                )
                logger.debug(f"Published streaming chunk ({stream_type.value}, complete={is_complete}, mcp_event={mcp_event_id}) for {session_id}")
        except Exception as e:
            # Don't fail LLM call if streaming fails
            logger.warning(f"Failed to publish streaming chunk: {e}")
    
    def _extract_retry_delay(self, error_message: str) -> Optional[int]:
        """Extract retry delay from error message if available."""
        try:
            # Look for patterns like "retry_delay { seconds: 4 }"
            import re
            delay_match = re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', error_message)
            if delay_match:
                return int(delay_match.group(1))
        except Exception:
            pass
        return None
    
    
    def _log_llm_detailed_error(self, exception: Exception, request_id: str):
        """Log detailed LLM communication errors using built-in capabilities."""
        llm_comm_logger.error(f"=== FULL LLM ERROR DUMP [{self.provider_name}] [ID: {request_id}] ===")
        llm_comm_logger.error(f"Request ID: {request_id}")
        
        # Use traceback.format_exception for comprehensive error formatting
        llm_comm_logger.error("--- FORMATTED EXCEPTION ---")
        formatted_exception = traceback.format_exception(type(exception), exception, exception.__traceback__)
        for line in formatted_exception:
            llm_comm_logger.error(line.rstrip())
        
        # Dump all exception variables using vars()
        llm_comm_logger.error("--- EXCEPTION VARIABLES ---")
        try:
            exception_vars = vars(exception)
            if exception_vars:
                for key, value in exception_vars.items():
                    llm_comm_logger.error(f"{key}: {pprint.pformat(value, width=100, depth=3)}")
            else:
                llm_comm_logger.error("No instance variables")
        except Exception as e:
            llm_comm_logger.error(f"Could not access exception variables: {e}")
        
        # Exception chain using traceback utilities
        llm_comm_logger.error("--- EXCEPTION CHAIN ---")
        try:
            for exc in traceback.walk_tb(exception.__traceback__):
                frame, lineno = exc
                llm_comm_logger.error(f"File {frame.f_code.co_filename}, line {lineno}, in {frame.f_code.co_name}")
        except Exception as e:
            llm_comm_logger.error(f"Could not walk traceback: {e}")
        
        llm_comm_logger.error(f"=== END ERROR DUMP [ID: {request_id}] ===")
    
class LLMManager:
    """Manages multiple LLM providers using LangChain."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.clients: Dict[str, LLMClient] = {}
        self.failed_providers: Dict[str, str] = {}  # provider_name -> error_message
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize LLM clients using unified implementation."""
        # Initialize each configured LLM provider
        for provider_name in self.settings.llm_providers.keys():
            config = None
            has_api_key = False
            
            try:
                config = self.settings.get_llm_config(provider_name)
                
                if not config.api_key:
                    logger.warning(f"Skipping {provider_name}: No API key provided")
                    continue  # Don't track as failure - this is expected
                
                has_api_key = True  # Mark that we have an API key
                
                # Use unified client for all providers
                client = LLMClient(provider_name, config, self.settings)
                self.clients[provider_name] = client
                logger.info(f"Initialized LLM client: {provider_name}")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to initialize LLM client {provider_name}: {error_msg}")
                # Track failure only if API key was provided (unexpected failure)
                if has_api_key:
                    self.failed_providers[provider_name] = error_msg
    
    def get_failed_providers(self) -> Dict[str, str]:
        """
        Get dictionary of failed LLM providers.
        
        Returns:
            Dict[provider_name, error_message] for providers that failed to initialize
        """
        return self.failed_providers.copy()
    
    def get_client(self, provider: str = None) -> Optional[LLMClient]:
        """Get an LLM client by provider name."""
        if not provider:
            provider = self.settings.llm_provider
        
        return self.clients.get(provider)
    
    async def generate_response(self,
                              conversation: LLMConversation,
                              session_id: str,
                              stage_execution_id: Optional[str] = None,
                              provider: str = None,
                              max_tokens: Optional[int] = None,
                              interaction_type: Optional[str] = None,
                              mcp_event_id: Optional[str] = None,
                              native_tools_override: Optional[NativeToolsConfig] = None) -> LLMConversation:
        """Generate a response using the specified or default LLM provider.
        
        Args:
            conversation: LLMConversation object containing complete message thread
            session_id: Required session ID for timeline logging and tracking
            stage_execution_id: Optional stage execution ID for tracking
            provider: Optional provider override (uses default if not specified)
            max_tokens: Optional max tokens configuration for LLM
            interaction_type: Optional interaction type (investigation, summarization, final_analysis).
                            If None, auto-detects based on response content.
            mcp_event_id: Optional MCP event ID if summarizing a tool result
            native_tools_override: Optional per-session native tools configuration override
            
        Returns:
            Updated LLMConversation with new assistant message appended
        """
        client = self.get_client(provider)
        if not client:
            available = list(self.clients.keys())
            raise Exception(f"LLM provider not available. Available: {available}")

        return await client.generate_response(
            conversation, 
            session_id, 
            stage_execution_id, 
            max_tokens, 
            interaction_type, 
            mcp_event_id=mcp_event_id,
            native_tools_override=native_tools_override
        )

    def list_available_providers(self) -> List[str]:
        """List available LLM providers."""
        return list(self.clients.keys())
    
    def is_available(self) -> bool:
        """Check if any LLM provider is available."""
        return len(self.clients) > 0 and any(client.available for client in self.clients.values())
    
    def get_availability_status(self) -> Dict:
        """Get detailed availability status for all providers."""
        return {
            provider: client.available 
            for provider, client in self.clients.items()
        }
    
    def get_max_tool_result_tokens(self) -> int:
        """Return the maximum tool result tokens for the default provider."""
        default_client = self.get_client()
        if default_client:
            return default_client.get_max_tool_result_tokens()
        
        # Fallback to safe default if no client available
        default_limit = 150000  # Conservative limit that works for most providers
        logger.info(f"No LLM client available, using default tool result limit: {default_limit:,} tokens")
        return default_limit