"""
Gemini Client - Native Thinking and Function Calling.

This module provides native thinking and function calling capabilities for Gemini models,
bypassing LangChain to use the Google SDK directly for full access to:
- Thinking content (internal reasoning via ThinkingConfig)
- Native function calling (structured tool calls without text parsing)
- Thought signatures (multi-turn reasoning continuity)
- Live streaming of thinking summaries and response content

Used by NativeThinkingController for Gemini-specific agent iteration.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from google import genai
from google.genai import types as google_genai_types

from tarsy.config.settings import get_settings
from tarsy.hooks.hook_context import llm_interaction_context
from tarsy.models.constants import LLMInteractionType, StreamingEventType
from tarsy.models.llm_models import GoogleNativeTool, LLMProviderConfig, LLMProviderType
from tarsy.models.mcp_selection_models import NativeToolsConfig
from tarsy.models.processing_context import ToolWithServer
from tarsy.models.unified_interactions import LLMConversation, MessageRole
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    pass

logger = get_module_logger(__name__)

# Streaming chunk sizes (small values for responsive UI updates)
THINKING_CHUNK_SIZE = 1  # Tokens between thinking summary updates
RESPONSE_CHUNK_SIZE = 2  # Tokens between response updates


@dataclass
class NativeThinkingToolCall:
    """Structured tool call from Gemini native function calling response."""
    server: str
    tool: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NativeThinkingResponse:
    """
    Response from Gemini native thinking generation.
    
    Contains:
    - content: The text response from the model
    - thinking_content: Internal reasoning (from thinking parts)
    - tool_calls: Structured tool calls (from function_call parts)
    - thought_signature: Opaque bytes for multi-turn reasoning continuity (pass back to next request)
    - is_final: Whether this is a final response (no tool calls)
    - conversation: Updated conversation with response
    """
    content: str
    conversation: 'LLMConversation'
    thinking_content: Optional[str] = None
    tool_calls: List[NativeThinkingToolCall] = field(default_factory=list)
    thought_signature: Optional[bytes] = None  # Opaque signature from Google SDK
    is_final: bool = False
    
    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls to execute."""
        return len(self.tool_calls) > 0


class GeminiNativeThinkingClient:
    """
    Client for Gemini's native thinking and function calling.
    
    Uses the Google SDK directly (not LangChain) to get full access to:
    - ThinkingConfig with include_thoughts=True for reasoning content
    - Native function declarations for MCP tools
    - Thought signatures for multi-turn continuity
    
    Note: The standard generateContent API does NOT support combining function
    calling with native tools (google_search, url_context). When MCP tools are
    provided, only MCP function calling is used.
    """
    
    def __init__(self, config: LLMProviderConfig, provider_name: Optional[str] = None):
        """
        Initialize the native thinking client.
        
        Args:
            config: LLM provider configuration (must be Google/Gemini)
            provider_name: Optional provider name for logging (defaults to model name)
            
        Raises:
            ValueError: If config is not for a Google provider
        """
        if config.type != LLMProviderType.GOOGLE:
            raise ValueError(
                f"GeminiNativeThinkingClient requires Google provider, got {config.type.value}"
            )
        
        self.config = config
        self.model = config.model
        self.temperature = config.temperature
        self.provider_name = provider_name or config.model
        self.settings = get_settings()
        self._sqlite_warning_logged = False
        
        logger.info(f"Initialized GeminiNativeThinkingClient for model {self.model}")
    
    async def _publish_stream_chunk(
        self,
        session_id: str,
        stage_execution_id: Optional[str],
        stream_type: StreamingEventType,
        chunk: str,
        is_complete: bool,
        llm_interaction_id: Optional[str] = None
    ) -> None:
        """
        Publish streaming chunk via transient channel for WebSocket delivery.
        
        Args:
            session_id: Session identifier
            stage_execution_id: Stage execution identifier
            stream_type: Type of streaming content (THOUGHT, FINAL_ANSWER, NATIVE_THINKING)
            chunk: Content chunk (accumulated tokens)
            is_complete: Whether this is the final chunk
            llm_interaction_id: LLM interaction ID for deduplication
        """
        # Check if streaming is enabled via config flag
        if self.settings and not self.settings.enable_llm_streaming:
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
                    llm_interaction_id=llm_interaction_id,
                    timestamp_us=now_us()
                )
                
                await publish_transient_event(
                    session=session,
                    channel=f"session:{session_id}",
                    event=event
                )
                
        except Exception as e:
            # Don't fail the main operation if streaming fails
            logger.warning(f"Failed to publish stream chunk: {e}")
    
    def _parse_function_name(self, func_name: str) -> tuple[str, str]:
        """
        Parse Gemini function name back to server and tool names.
        
        Args:
            func_name: Function name in format "server__tool_name"
            
        Returns:
            Tuple of (server_name, tool_name)
            
        Raises:
            ValueError: If function name doesn't contain separator
        """
        if "__" not in func_name:
            raise ValueError(f"Invalid function name format: {func_name}, expected 'server__tool_name'")
        
        server, tool = func_name.split("__", 1)
        return server, tool
    
    def _convert_mcp_tools_to_functions(
        self,
        mcp_tools: List[ToolWithServer]
    ) -> List[google_genai_types.FunctionDeclaration]:
        """
        Convert MCP tools to native Google FunctionDeclaration format.
        
        Args:
            mcp_tools: List of MCP tools with server context
            
        Returns:
            List of native Google FunctionDeclaration objects
        """
        functions = []
        
        for tool_with_server in mcp_tools:
            try:
                # Use server__tool_name as function name (double underscore separator)
                func_name = f"{tool_with_server.server}__{tool_with_server.tool.name}"
                
                # Get the input schema, defaulting to empty object if not specified
                input_schema = tool_with_server.tool.inputSchema or {"type": "object", "properties": {}}
                
                # Create native Google FunctionDeclaration
                func_decl = google_genai_types.FunctionDeclaration(
                    name=func_name,
                    description=tool_with_server.tool.description or f"Tool {tool_with_server.tool.name} from {tool_with_server.server}",
                    parameters_json_schema=input_schema
                )
                functions.append(func_decl)
                
                logger.debug(f"Converted MCP tool to native function: {func_name}")
                
            except Exception as e:
                logger.warning(f"Failed to convert MCP tool {tool_with_server.server}.{tool_with_server.tool.name}: {e}")
                continue
        
        logger.info(f"Converted {len(functions)} MCP tools to native Google functions")
        return functions
    
    def _convert_conversation_to_native_format(
        self,
        conversation: LLMConversation
    ) -> List[google_genai_types.Content]:
        """
        Convert LLMConversation to native Google Content format.
        
        Args:
            conversation: The LLMConversation to convert
            
        Returns:
            List of native Google Content objects
        """
        contents = []
        
        for msg in conversation.messages:
            # Map roles: system messages become user role with [System] prefix
            if msg.role == MessageRole.SYSTEM:
                contents.append(google_genai_types.Content(
                    role="user",
                    parts=[google_genai_types.Part(text=f"[System Instructions]\n{msg.content}")]
                ))
            elif msg.role == MessageRole.USER:
                contents.append(google_genai_types.Content(
                    role="user",
                    parts=[google_genai_types.Part(text=msg.content)]
                ))
            elif msg.role == MessageRole.ASSISTANT:
                contents.append(google_genai_types.Content(
                    role="model",
                    parts=[google_genai_types.Part(text=msg.content)]
                ))
        
        return contents
    
    async def generate(
        self,
        conversation: LLMConversation,
        session_id: str,
        mcp_tools: List[ToolWithServer],
        stage_execution_id: Optional[str] = None,
        thinking_level: str = "high",
        thought_signature: Optional[bytes] = None,
        max_tokens: Optional[int] = None,
        timeout_seconds: int = 180,
        native_tools_override: Optional[NativeToolsConfig] = None
    ) -> NativeThinkingResponse:
        """
        Generate response using Gemini's native thinking and function calling.
        
        This method uses the native Google SDK directly (not LangChain) to get
        full access to thinking content and native function calling.
        
        Note: The standard generateContent API does NOT support combining function
        calling with native tools (google_search, url_context). When MCP tools are
        provided, only MCP function calling is used. Native Google tools are only
        used when no MCP tools are provided.
        
        Args:
            conversation: The conversation to continue
            session_id: Session ID for tracking
            mcp_tools: MCP tools to bind as native functions
            stage_execution_id: Optional stage execution ID
            thinking_level: Thinking depth ("low" or "high", default "high")
            thought_signature: Opaque bytes from previous turn for reasoning continuity
            max_tokens: Optional max tokens configuration
            timeout_seconds: Timeout for LLM call (default 180s for thinking)
            native_tools_override: Optional per-session native tools override
            
        Returns:
            NativeThinkingResponse with content, tool_calls, thinking_content, etc.
            
        Raises:
            TimeoutError: If generation times out
            Exception: On LLM communication failures
        """
        # Generate unique request ID for logging
        request_id = str(uuid.uuid4())[:8]
        
        logger.info(f"[{request_id}] Starting native thinking generation for {session_id}")
        logger.debug(f"[{request_id}] Thinking level: {thinking_level}, MCP tools: {len(mcp_tools)}")
        
        # Prepare request data for typed context (ensure JSON serializable)
        request_data = {
            'messages': [msg.model_dump() for msg in conversation.messages],
            'model': self.model,
            'provider': self.provider_name,
            'temperature': self.temperature,
            'thinking_level': thinking_level,
            'mcp_tools_count': len(mcp_tools)
        }
        
        # Determine which native tools to enable (using config directly)
        google_search_enabled = self.config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value)
        code_execution_enabled = self.config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value)
        url_context_enabled = self.config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value)
        
        # Apply session-level override if provided
        if native_tools_override is not None:
            if native_tools_override.google_search is not None:
                google_search_enabled = native_tools_override.google_search
            if native_tools_override.code_execution is not None:
                code_execution_enabled = native_tools_override.code_execution
            if native_tools_override.url_context is not None:
                url_context_enabled = native_tools_override.url_context
            logger.info(f"[{request_id}] Applied session-level native tools override")
        
        # Capture effective config for audit trail
        native_tools_config = {
            GoogleNativeTool.GOOGLE_SEARCH.value: google_search_enabled,
            GoogleNativeTool.CODE_EXECUTION.value: code_execution_enabled,
            GoogleNativeTool.URL_CONTEXT.value: url_context_enabled
        }
        
        # Create interaction context for audit
        async with llm_interaction_context(session_id, request_data, stage_execution_id, native_tools_config) as ctx:
            try:
                # Create native Google client
                native_client = genai.Client(api_key=self.config.api_key)
                
                # Convert conversation to native Google format
                contents = self._convert_conversation_to_native_format(conversation)
                
                # If we have a thought signature from previous turn, include it for reasoning continuity
                # The signature must be added as a Part to maintain the model's reasoning state
                if thought_signature:
                    # Add thought signature as a model turn part to preserve reasoning context
                    contents.append(google_genai_types.Content(
                        role="model",
                        parts=[google_genai_types.Part(thought_signature=thought_signature)]
                    ))
                    logger.debug(f"[{request_id}] Attached thought_signature for reasoning continuity")
                
                # Convert MCP tools to native function declarations
                mcp_functions = self._convert_mcp_tools_to_functions(mcp_tools)
                
                # Build tools list
                # NOTE: Standard generateContent API doesn't support multi-tool use
                # (combining function calling with google_search/url_context/code_execution).
                # When MCP tools are provided, we use those exclusively.
                tools = []
                
                if mcp_functions:
                    tools.append(google_genai_types.Tool(function_declarations=mcp_functions))
                    logger.info(f"[{request_id}] Bound {len(mcp_functions)} MCP tools as native functions")
                else:
                    # Only add native Google tools when no MCP function calling is needed
                    native_tools_bound = []
                    if google_search_enabled:
                        tools.append(google_genai_types.Tool(google_search=google_genai_types.GoogleSearch()))
                        native_tools_bound.append("google_search")
                    
                    if url_context_enabled:
                        tools.append(google_genai_types.Tool(url_context=google_genai_types.UrlContext()))
                        native_tools_bound.append("url_context")
                    
                    if code_execution_enabled:
                        tools.append(google_genai_types.Tool(code_execution=google_genai_types.ToolCodeExecution()))
                        native_tools_bound.append("code_execution")
                    
                    if native_tools_bound:
                        logger.info(f"[{request_id}] Bound native Google tools: {native_tools_bound}")
                
                # Configure thinking with include_thoughts=True to get reasoning content
                thinking_budget = 24576 if thinking_level == "high" else 4096
                thinking_config = google_genai_types.ThinkingConfig(
                    thinking_budget=thinking_budget,
                    include_thoughts=True  # This enables access to thinking content!
                )
                
                # Build generation config
                # temperature=None lets the model use its default (varies by model)
                gen_config = google_genai_types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=max_tokens,
                    thinking_config=thinking_config,
                    tools=tools if tools else None,
                    # Disable automatic function calling - we handle it manually
                    automatic_function_calling=google_genai_types.AutomaticFunctionCallingConfig(
                        disable=True
                    ) if tools else None
                )
                
                # Make the API call with timeout using streaming
                accumulated_content = ""
                thinking_content_parts = []
                tool_calls = []
                new_thought_signature = None
                response_metadata = {}
                
                # Streaming state tracking
                is_streaming_thinking = False
                is_streaming_response = False
                thinking_token_count = 0
                response_token_count = 0
                accumulated_thinking = ""
                
                async with asyncio.timeout(timeout_seconds):
                    # Use async streaming generate_content for real-time updates
                    async for chunk in await native_client.aio.models.generate_content_stream(
                        model=self.model,
                        contents=contents,
                        config=gen_config
                    ):
                        # Process streaming chunk
                        if chunk.candidates and len(chunk.candidates) > 0:
                            candidate = chunk.candidates[0]
                            
                            if candidate.content and candidate.content.parts:
                                for part in candidate.content.parts:
                                    # Check if this is a thought part (thinking summary)
                                    if hasattr(part, 'thought') and part.thought:
                                        if hasattr(part, 'text') and part.text:
                                            thinking_content_parts.append(part.text)
                                            accumulated_thinking += part.text
                                            thinking_token_count += 1
                                            
                                            # Start streaming thinking if not already
                                            if not is_streaming_thinking:
                                                is_streaming_thinking = True
                                                logger.debug(f"[{request_id}] Started streaming thinking content")
                                            
                                            # Stream thinking updates every N tokens
                                            if thinking_token_count >= THINKING_CHUNK_SIZE:
                                                await self._publish_stream_chunk(
                                                    session_id, stage_execution_id,
                                                    StreamingEventType.NATIVE_THINKING, accumulated_thinking,
                                                    is_complete=False,
                                                    llm_interaction_id=ctx.interaction.interaction_id
                                                )
                                                thinking_token_count = 0
                                    
                                    elif hasattr(part, 'text') and part.text:
                                        # This is regular response text
                                        accumulated_content += part.text
                                        response_token_count += 1
                                        
                                        # If we were streaming thinking, send final thinking chunk
                                        if is_streaming_thinking:
                                            await self._publish_stream_chunk(
                                                session_id, stage_execution_id,
                                                StreamingEventType.NATIVE_THINKING, accumulated_thinking,
                                                is_complete=True,
                                                llm_interaction_id=ctx.interaction.interaction_id
                                            )
                                            is_streaming_thinking = False
                                            logger.debug(f"[{request_id}] Completed streaming thinking content")
                                        
                                        # Start streaming response if not already
                                        if not is_streaming_response:
                                            is_streaming_response = True
                                            logger.debug(f"[{request_id}] Started streaming response content")
                                        
                                        # Stream response updates every N tokens
                                        if response_token_count >= RESPONSE_CHUNK_SIZE:
                                            await self._publish_stream_chunk(
                                                session_id, stage_execution_id,
                                                StreamingEventType.FINAL_ANSWER, accumulated_content,
                                                is_complete=False,
                                                llm_interaction_id=ctx.interaction.interaction_id
                                            )
                                            response_token_count = 0
                                    
                                    # Extract thought signature if present
                                    if hasattr(part, 'thought_signature') and part.thought_signature:
                                        new_thought_signature = part.thought_signature
                        
                        # Extract function calls from streaming chunk
                        if hasattr(chunk, 'function_calls') and chunk.function_calls:
                            for fc in chunk.function_calls:
                                try:
                                    func_name = fc.name if hasattr(fc, 'name') else str(fc.function_call.name if hasattr(fc, 'function_call') else '')
                                    func_args = dict(fc.args) if hasattr(fc, 'args') else {}
                                    
                                    server, tool = self._parse_function_name(func_name)
                                    tool_calls.append(NativeThinkingToolCall(
                                        server=server,
                                        tool=tool,
                                        parameters=func_args
                                    ))
                                    logger.debug(f"[{request_id}] Extracted tool call: {server}.{tool}")
                                except (ValueError, AttributeError) as e:
                                    logger.warning(f"[{request_id}] Failed to parse function call: {e}")
                        
                        # Build response metadata from last chunk
                        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                            usage = chunk.usage_metadata
                            response_metadata = {
                                'prompt_token_count': getattr(usage, 'prompt_token_count', None),
                                'candidates_token_count': getattr(usage, 'candidates_token_count', None),
                                'total_token_count': getattr(usage, 'total_token_count', None),
                            }
                            # Store token counts for interaction
                            ctx.interaction.input_tokens = getattr(usage, 'prompt_token_count', None)
                            ctx.interaction.output_tokens = getattr(usage, 'candidates_token_count', None)
                            ctx.interaction.total_tokens = getattr(usage, 'total_token_count', None)
                    
                    # Send final streaming chunks after stream completes
                    if is_streaming_thinking and accumulated_thinking:
                        await self._publish_stream_chunk(
                            session_id, stage_execution_id,
                            StreamingEventType.NATIVE_THINKING, accumulated_thinking,
                            is_complete=True,
                            llm_interaction_id=ctx.interaction.interaction_id
                        )
                    
                    if is_streaming_response and accumulated_content:
                        await self._publish_stream_chunk(
                            session_id, stage_execution_id,
                            StreamingEventType.FINAL_ANSWER, accumulated_content,
                            is_complete=True,
                            llm_interaction_id=ctx.interaction.interaction_id
                        )
                
                # Combine thinking content
                combined_thinking = "\n".join(thinking_content_parts) if thinking_content_parts else None
                
                # Determine if this is a final response (no tool calls)
                is_final = len(tool_calls) == 0
                
                # Update conversation with response
                if accumulated_content.strip():
                    conversation.append_assistant_message(accumulated_content)
                
                # Update interaction record
                ctx.interaction.conversation = conversation
                ctx.interaction.provider = self.provider_name
                ctx.interaction.model_name = self.model
                ctx.interaction.temperature = self.temperature
                ctx.interaction.response_metadata = response_metadata
                
                # Store thinking content
                if combined_thinking:
                    ctx.interaction.thinking_content = combined_thinking
                
                # Set interaction type based on whether this is final
                ctx.interaction.interaction_type = (
                    LLMInteractionType.FINAL_ANALYSIS.value if is_final 
                    else LLMInteractionType.INVESTIGATION.value
                )
                
                ctx.interaction.native_tools_config = native_tools_config
                
                await ctx.complete_success({})
                
                logger.info(
                    f"[{request_id}] Native thinking complete: "
                    f"tool_calls={len(tool_calls)}, "
                    f"has_thinking={combined_thinking is not None}, "
                    f"is_final={is_final}"
                )
                
                return NativeThinkingResponse(
                    content=accumulated_content,
                    conversation=conversation,
                    thinking_content=combined_thinking,
                    tool_calls=tool_calls,
                    thought_signature=new_thought_signature,
                    is_final=is_final
                )
                
            except asyncio.TimeoutError:
                logger.error(f"[{request_id}] Native thinking timed out after {timeout_seconds}s")
                raise TimeoutError(f"Native thinking timed out after {timeout_seconds}s") from None
            except Exception as e:
                logger.error(f"[{request_id}] Native thinking failed: {e}")
                raise

