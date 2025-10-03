"""
Unified LLM client implementation using LangChain.
Handles all LLM providers through LangChain's abstraction.
"""

import asyncio
import httpx
import pprint
import traceback
import urllib3
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_xai import ChatXAI
from langchain_anthropic import ChatAnthropic

from tarsy.config.settings import Settings
from tarsy.hooks.typed_context import llm_interaction_context
from tarsy.models.constants import LLMInteractionType
from tarsy.models.llm_models import LLMProviderConfig
from tarsy.models.unified_interactions import LLMConversation, MessageRole
from tarsy.utils.logger import get_module_logger
from tarsy.utils.error_details import extract_error_details

# Suppress SSL warnings when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup logger for this module
logger = get_module_logger(__name__)

# Setup separate logger for LLM communications
llm_comm_logger = get_module_logger("llm.communications")


# LLM Providers mapping using LangChain
def _create_openai_client(temp, api_key, model, disable_ssl_verification=False, base_url=None):
    """Create ChatOpenAI client with optional SSL verification disable and custom base URL."""
    client_kwargs = {
        "model_name": model, 
        "temperature": temp, 
        "api_key": api_key
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
        "temperature": temp, 
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

LLM_PROVIDERS = {
    "openai": _create_openai_client,
    "google": _create_google_client,
    "xai": _create_xai_client,
    "anthropic": _create_anthropic_client
}


class LLMClient:
    """Simple LLM client focused purely on communication with LLM providers via LangChain."""
    
    def __init__(self, provider_name: str, config: LLMProviderConfig):
        self.provider_name = provider_name
        self.config = config
        self.provider_config = config  # Store config for access to provider-specific settings
        self.model = config.model  # Direct field access on BaseModel
        self.api_key = config.api_key or ""  # Handle Optional field
        self.temperature = config.temperature  # Field with default in BaseModel
        self.llm_client: Optional[BaseChatModel] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the LangChain LLM client."""
        try:
            # Map provider name to provider type for LLM_PROVIDERS
            provider_type = self.config.type  # Direct field access on BaseModel
            
            if provider_type in LLM_PROVIDERS:
                if not self.api_key:
                    logger.warning(f"No API key provided for {self.provider_name}")
                    self.available = False
                    return
                
                disable_ssl_verification = self.config.disable_ssl_verification
                if disable_ssl_verification:
                    logger.warning(f"SSL verification is DISABLED for {self.provider_name} - use with caution!")
                
                base_url = self.config.base_url
                self.llm_client = LLM_PROVIDERS[provider_type](
                    self.temperature, 
                    self.api_key, 
                    self.model,
                    disable_ssl_verification,
                    base_url
                )
                self.available = True
                logger.info(f"Successfully initialized {self.provider_name} with LangChain")
            else:
                logger.error(f"Unknown LLM provider type: {provider_type} for provider: {self.provider_name}")
                self.available = False
        except Exception as e:
            logger.error(f"Failed to initialize {self.provider_name}: {str(e)}")
            self.available = False

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
        interaction_type: Optional[str] = None
    ) -> LLMConversation:
        """
        Generate response using type-safe conversation object.
        
        It takes original LLMConversation and returns updated conversation
        with response assistant message appended.
        
        Args:
            conversation: The conversation to generate a response for
            session_id: Session ID for tracking
            stage_execution_id: Optional stage execution ID
            max_tokens: Optional max tokens configuration for LLM
            interaction_type: Optional interaction type (investigation, summarization, final_analysis).
                            If None, auto-detects based on response content.
        
        Returns:
            Updated conversation with assistant response appended
        
        To get the assistant response: conversation.get_latest_assistant_message().content
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
        
        # Use typed hook context for clean data flow
        async with llm_interaction_context(session_id, request_data, stage_execution_id) as ctx:
            
            # Get request ID for logging  
            request_id = ctx.get_request_id()

            # Log the outgoing conversation
            llm_comm_logger.debug(f"=== LLM REQUEST [{self.provider_name}] [ID: {request_id}] ===")

            try:
                # Convert typed conversation to LangChain format  
                langchain_messages = self._convert_conversation_to_langchain(conversation)
                
                # Get both response and usage metadata
                response, usage_metadata = await self._execute_with_retry(langchain_messages, max_tokens=max_tokens)
                
                # Store token usage in dedicated type-safe fields on interaction
                if usage_metadata:
                    input_tokens = usage_metadata.get('input_tokens', 0)
                    output_tokens = usage_metadata.get('output_tokens', 0)
                    total_tokens = usage_metadata.get('total_tokens', 0)
                    
                    # Store token data (use None instead of 0 for cleaner database storage)
                    ctx.interaction.input_tokens = input_tokens if input_tokens > 0 else None
                    ctx.interaction.output_tokens = output_tokens if output_tokens > 0 else None
                    ctx.interaction.total_tokens = total_tokens if total_tokens > 0 else None
                
                # Extract response content
                response_content = response.content if hasattr(response, 'content') else str(response)
                
                # Add assistant response to conversation
                conversation.append_assistant_message(response_content)
                
                # Update the interaction with conversation data
                ctx.interaction.conversation = conversation  # Store complete conversation
                ctx.interaction.provider = self.provider_name
                ctx.interaction.model_name = self.model
                ctx.interaction.temperature = self.temperature
                
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
                
                # Complete the typed context with success
                await ctx.complete_success({})
                
                return conversation  # Return updated conversation
                
            except Exception as e:
                # Log the detailed error (hooks will be triggered automatically by context manager)
                self._log_llm_detailed_error(e, request_id)
                
                # Create enhanced error message with key attributes
                error_details = extract_error_details(e)
                enhanced_message = f"{self.provider_name} API error: {str(e)}"
                if error_details:
                    enhanced_message += f" | Details: {error_details}"
                
                raise Exception(enhanced_message) from e
    
    def _contains_final_answer(self, conversation: LLMConversation) -> bool:
        """
        Check if the LAST message is from assistant and starts with 'Final Answer:'.
        
        This indicates a ReAct stage conclusion. Only checks the very last message
        in the conversation to avoid false positives.
        
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
        
        # Check if Final Answer appears at start of line
        content = last_msg.content.strip()
        if content.startswith("Final Answer:"):
            return True
        
        # Also check for Final Answer after newlines (multi-line messages)
        if "\nFinal Answer:" in last_msg.content:
            return True
        
        return False
    
    def get_max_tool_result_tokens(self) -> int:
        """Return the maximum tool result tokens for the current provider."""
        return self.provider_config.max_tool_result_tokens  # Already an int with BaseModel validation
    
    async def _execute_with_retry(
        self,
        langchain_messages: List,
        max_retries: int = 3,
        max_tokens: Optional[int] = None
    ) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """Execute LLM call with usage tracking and retry logic."""
        for attempt in range(max_retries + 1):
            try:
                # Add callback handler to capture token usage
                callback = UsageMetadataCallbackHandler()
                
                # Build config with callbacks only
                config = {"callbacks": [callback]}
                
                if max_tokens is not None:
                    config["max_tokens"] = max_tokens

                response = await self.llm_client.ainvoke(
                    langchain_messages,
                    config=config
                )
                
                # Check for empty response content
                if response and hasattr(response, 'content'):
                    content = response.content
                    if content is None or (isinstance(content, str) and content.strip() == ""):
                        if attempt < max_retries:
                            # Only retry empty responses once (first attempt) to avoid too many retries
                            if attempt == 0:
                                logger.warning(f"Empty LLM response received (attempt {attempt + 1}/{max_retries + 1}), retrying in 3s")
                                await asyncio.sleep(3)
                                continue
                            else:
                                logger.warning(f"Empty LLM response received again (attempt {attempt + 1}/{max_retries + 1}), injecting error message")
                                # Inject descriptive error message instead of proceeding with empty response
                                error_message = f"⚠️ **LLM Response Error**\n\nThe {self.provider_name} LLM returned empty responses after {attempt + 1} attempts. This may be due to:\n- Temporary provider issues\n- API rate limiting\n- Model overload\n\nPlease try processing this alert again in a few moments."
                                response.content = error_message
                        else:
                            logger.warning(f"Empty LLM response received on final attempt, injecting error message")
                            # Inject descriptive error message for final attempt
                            error_message = f"⚠️ **LLM Response Error**\n\nThe {self.provider_name} LLM returned an empty response on the final attempt (attempt {attempt + 1}/{max_retries + 1}). This may be due to:\n- Temporary provider issues\n- API rate limiting\n- Model overload\n\nPlease try processing this alert again in a few moments."
                            response.content = error_message
                
                # Return both response and usage metadata from first model
                usage_metadata = None
                if callback.usage_metadata:
                    # Log the entire usage_metadata object for debugging
                    logger.info(f"Complete usage_metadata object: {pprint.pformat(callback.usage_metadata, width=100, depth=5)}")
                    
                    # Extract the first (and likely only) model's usage metadata
                    first_model_name = next(iter(callback.usage_metadata.keys()), None)
                    if first_model_name:
                        model_usage = callback.usage_metadata[first_model_name]
                        if isinstance(model_usage, dict):
                            # Create a simple UsageMetadata-like object
                            usage_metadata = model_usage
                
                return response, usage_metadata
                
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = any(indicator in error_str for indicator in [
                    "429", "rate limit", "quota", "too many requests", "rate_limit_exceeded"
                ])
                
                if is_rate_limit and attempt < max_retries:
                    # Extract retry delay from error if available
                    retry_delay = self._extract_retry_delay(str(e))
                    if retry_delay is None:
                        # Exponential backoff: 2^attempt seconds
                        retry_delay = (2 ** attempt)
                    
                    logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}), retrying in {retry_delay}s")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    # Log detailed error information for debugging
                    error_details = extract_error_details(e)
                    logger.error(f"LLM execution failed after {attempt + 1} attempts - {error_details}")
                    
                    # Re-raise the exception for non-rate-limit errors or max retries reached
                    raise e
    
    def _extract_retry_delay(self, error_message: str) -> Optional[int]:
        """Extract retry delay from error message if available."""
        try:
            # Look for patterns like "retry_delay { seconds: 4 }"
            import re
            delay_match = re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', error_message)
            if delay_match:
                return int(delay_match.group(1))
        except:
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
                client = LLMClient(provider_name, config)
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
                              interaction_type: Optional[str] = None) -> LLMConversation:
        """Generate a response using the specified or default LLM provider.
        
        Args:
            conversation: LLMConversation object containing complete message thread
            session_id: Required session ID for timeline logging and tracking
            stage_execution_id: Optional stage execution ID for tracking
            provider: Optional provider override (uses default if not specified)
            max_tokens: Optional max tokens configuration for LLM
            interaction_type: Optional interaction type (investigation, summarization, final_analysis).
                            If None, auto-detects based on response content.
            
        Returns:
            Updated LLMConversation with new assistant message appended
        """
        client = self.get_client(provider)
        if not client:
            available = list(self.clients.keys())
            raise Exception(f"LLM provider not available. Available: {available}")

        return await client.generate_response(conversation, session_id, stage_execution_id, max_tokens, interaction_type)

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