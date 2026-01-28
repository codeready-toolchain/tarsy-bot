"""
LLM Manager for multi-provider orchestration.

Manages multiple LLM providers, handles availability checking, and provides
unified access to both LangChain-based clients and native thinking clients.
"""

from typing import TYPE_CHECKING, Dict, List, Optional

from tarsy.config.settings import Settings
from tarsy.integrations.llm.client import LLMClient
from tarsy.models.llm_models import LLMProviderType
from tarsy.models.mcp_selection_models import NativeToolsConfig
from tarsy.models.parallel_metadata import ParallelExecutionMetadata
from tarsy.models.unified_interactions import LLMConversation
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.integrations.llm.gemini_client import GeminiNativeThinkingClient

logger = get_module_logger(__name__)


class LLMManager:
    """
    Manages multiple LLM providers using LangChain.
    
    Provides unified access to:
    - LLMClient instances for LangChain-based ReAct workflows
    - GeminiNativeThinkingClient instances for native thinking workflows (Google/Gemini only)
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.clients: Dict[str, LLMClient] = {}
        self._native_thinking_clients: Dict[str, 'GeminiNativeThinkingClient'] = {}
        self.failed_providers: Dict[str, str] = {}  # provider_name -> error_message
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize LLM clients using unified implementation."""
        # Initialize each configured LLM provider
        for provider_name in self.settings.llm_providers.keys():
            config = None
            auth_provided = False
            
            try:
                config = self.settings.get_llm_config(provider_name)
                
                if not config.is_auth_configured():
                    logger.warning(f"Skipping {provider_name}: Auth not fully configured")
                    continue  # Don't track as failure - this is expected
                
                auth_provided = True  # Mark that we have an API key or some other means of auth
                
                # Use unified client for all providers
                client = LLMClient(provider_name, config, self.settings)
                self.clients[provider_name] = client
                logger.info(f"Initialized LLM client: {provider_name}")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to initialize LLM client {provider_name}: {error_msg}")
                # Track failure only if auth was provided (unexpected failure)
                if auth_provided:
                    self.failed_providers[provider_name] = error_msg
    
    def get_failed_providers(self) -> Dict[str, str]:
        """
        Get dictionary of failed LLM providers.
        
        Returns:
            Dict[provider_name, error_message] for providers that failed to initialize
        """
        return self.failed_providers.copy()
    
    def get_client(self, provider: str | None = None) -> Optional[LLMClient]:
        """Get an LLM client by provider name."""
        if not provider:
            provider = self.settings.llm_provider
        
        return self.clients.get(provider)
    
    def get_native_thinking_client(
        self, 
        provider: str | None = None
    ) -> Optional['GeminiNativeThinkingClient']:
        """
        Get native thinking client for Google/Gemini providers.
        
        Creates clients lazily and caches them. Returns None for non-Google providers.
        
        Args:
            provider: Optional provider name (uses default if not specified)
            
        Returns:
            GeminiNativeThinkingClient if provider is Google/Gemini, None otherwise
        """
        # Import here to avoid circular imports
        from tarsy.integrations.llm.gemini_client import GeminiNativeThinkingClient
        
        provider = provider or self.settings.llm_provider
        
        # Return cached client if available
        if provider in self._native_thinking_clients:
            return self._native_thinking_clients[provider]
        
        # Check if this is a Google provider
        llm_client = self.clients.get(provider)
        if not llm_client:
            logger.warning(f"LLM provider '{provider}' not found for native thinking client")
            return None
        
        if llm_client.config.type != LLMProviderType.GOOGLE:
            logger.debug(
                f"Provider '{provider}' is {llm_client.config.type.value}, "
                "not Google/Gemini - cannot create native thinking client"
            )
            return None
        
        # Create and cache native thinking client
        try:
            native_client = GeminiNativeThinkingClient(
                llm_client.config,
                provider_name=provider
            )
            self._native_thinking_clients[provider] = native_client
            logger.info(f"Created native thinking client for provider: {provider}")
            return native_client
        except Exception as e:
            logger.error(f"Failed to create native thinking client for {provider}: {e}")
            return None
    
    async def generate_response(self,
                              conversation: LLMConversation,
                              session_id: str,
                              stage_execution_id: Optional[str] = None,
                              provider: str = None,
                              max_tokens: Optional[int] = None,
                              interaction_type: Optional[str] = None,
                              mcp_event_id: Optional[str] = None,
                              native_tools_override: Optional[NativeToolsConfig] = None,
                              parallel_metadata: Optional['ParallelExecutionMetadata'] = None) -> LLMConversation:
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
            native_tools_override=native_tools_override,
            parallel_metadata=parallel_metadata
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

