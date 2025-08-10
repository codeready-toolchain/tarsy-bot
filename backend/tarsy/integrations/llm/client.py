"""
Unified LLM client implementation using LangChain.
Handles all LLM providers through LangChain's abstraction.
"""

from typing import Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_xai import ChatXAI

from tarsy.config.settings import Settings
from tarsy.hooks.typed_context import llm_interaction_context
from tarsy.models.llm import LLMMessage
from tarsy.models.interactions import LLMRequest, LLMMessage as TypedLLMMessage, LLMResponse, LLMChoice, LLMUsage
from tarsy.utils.logger import get_module_logger

# Setup logger for this module
logger = get_module_logger(__name__)

# Setup separate logger for LLM communications
llm_comm_logger = get_module_logger("llm.communications")


# LLM Providers mapping using LangChain
LLM_PROVIDERS = {
    "openai": lambda temp, api_key, model: ChatOpenAI(
        model_name=model or "gpt-4-1106-preview", 
        temperature=temp, 
        api_key=api_key
    ),
    "gemini": lambda temp, api_key, model: ChatGoogleGenerativeAI(
        model=model or "gemini-2.5-pro-exp-03-25", 
        temperature=temp, 
        google_api_key=api_key
    ),
    "grok": lambda temp, api_key, model: ChatXAI(
        model_name=model or "grok-3-latest", 
        api_key=api_key, 
        temperature=temp
    ),
}


class LLMClient:
    """Simple LLM client focused purely on communication with LLM providers via LangChain."""
    
    def __init__(self, provider_name: str, config: Dict):
        self.provider_name = provider_name
        self.config = config
        self.model = config.get("model", "default")
        self.api_key = config.get("api_key", "")
        self.temperature = config.get("temperature", 0.3)
        self.llm_client: Optional[BaseChatModel] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the LangChain LLM client."""
        try:
            if self.provider_name in LLM_PROVIDERS:
                if not self.api_key:
                    logger.warning(f"No API key provided for {self.provider_name}")
                    self.available = False
                    return
                
                self.llm_client = LLM_PROVIDERS[self.provider_name](
                    self.temperature, 
                    self.api_key, 
                    self.model
                )
                self.available = True
                logger.info(f"Successfully initialized {self.provider_name} with LangChain")
            else:
                logger.error(f"Unknown LLM provider: {self.provider_name}")
                self.available = False
        except Exception as e:
            logger.error(f"Failed to initialize {self.provider_name}: {str(e)}")
            self.available = False
    
    def _convert_messages(self, messages: List[LLMMessage]) -> List:
        """Convert LLMMessage objects to LangChain message objects."""
        langchain_messages = []
        for msg in messages:
            if msg.role == "system":
                langchain_messages.append(SystemMessage(content=msg.content))
            elif msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                langchain_messages.append(AIMessage(content=msg.content))
        return langchain_messages
    
    async def generate_response(self, messages: List[LLMMessage], session_id: str) -> str:
        """
        Generate a response from the LLM using LangChain with typed interactions.
        
        This is the core method that handles communication with any LLM provider.
        All business logic should be handled by the calling code.
        
        Args:
            messages: List of messages for the conversation
            session_id: Required session ID for timeline logging and tracking
        """
        if not self.available or not self.llm_client:
            raise Exception(f"{self.provider_name} client not available")
        
        # Prepare request data for typed context
        request_data = {
            'messages': messages,
            'model': self.model,
            'provider': self.provider_name,
            'temperature': self.temperature
        }
        
        # Use typed hook context for clean data flow
        async with llm_interaction_context(session_id, request_data) as ctx:
            
            # Get request ID for logging
            request_id = ctx.get_request_id()
            
            # Log the outgoing prompt/messages
            self._log_llm_request(messages, request_id)
            
            try:
                # Execute the LLM call
                langchain_messages = self._convert_messages(messages)
                response = await self.llm_client.ainvoke(langchain_messages)
                
                # Log the response
                self._log_llm_response(response.content, request_id)
                
                # Create typed response
                typed_response = LLMResponse(
                    choices=[
                        LLMChoice(
                            message=TypedLLMMessage(role="assistant", content=response.content),
                            finish_reason="stop"
                        )
                    ],
                    model=self.model,
                    usage=None  # LangChain doesn't provide usage info by default
                )
                
                # Update the interaction with response data
                ctx.interaction.response = typed_response
                ctx.interaction.provider = self.provider_name
                ctx.interaction.model_name = self.model
                
                # Complete the typed context with success
                await ctx.complete_success({})
                
                return response.content
                
            except Exception as e:
                # Log the error (hooks will be triggered automatically by context manager)
                self._log_llm_error(str(e), request_id)
                raise Exception(f"{self.provider_name} API error: {str(e)}")
    
    def _log_llm_request(self, messages: List[LLMMessage], request_id: str):
        """Log the outgoing LLM request."""
        llm_comm_logger.info(f"=== LLM REQUEST [{self.provider_name}] [ID: {request_id}] ===")
        llm_comm_logger.info(f"Request ID: {request_id}")
        llm_comm_logger.info(f"Provider: {self.provider_name}")
        llm_comm_logger.info(f"Model: {self.model}")
        llm_comm_logger.info(f"Temperature: {self.temperature}")
        
        llm_comm_logger.info("--- MESSAGES ---")
        for i, msg in enumerate(messages):
            llm_comm_logger.info(f"Message {i+1} [{msg.role.upper()}]:")
            llm_comm_logger.info(f"{msg.content}")
            llm_comm_logger.info("---")
        
        llm_comm_logger.info(f"=== END REQUEST [ID: {request_id}] ===")
    
    def _log_llm_response(self, response_content: str, request_id: str):
        """Log the LLM response."""
        llm_comm_logger.info(f"=== LLM RESPONSE [{self.provider_name}] [ID: {request_id}] ===")
        llm_comm_logger.info(f"Request ID: {request_id}")
        llm_comm_logger.info(f"Response length: {len(response_content)} characters")
        llm_comm_logger.info("--- RESPONSE CONTENT ---")
        llm_comm_logger.info(response_content)
        llm_comm_logger.info(f"=== END RESPONSE [ID: {request_id}] ===")
    
    def _log_llm_error(self, error_message: str, request_id: str):
        """Log LLM communication errors."""
        llm_comm_logger.error(f"=== LLM ERROR [{self.provider_name}] [ID: {request_id}] ===")
        llm_comm_logger.error(f"Request ID: {request_id}")
        llm_comm_logger.error(f"Error: {error_message}")
        llm_comm_logger.error(f"=== END ERROR [ID: {request_id}] ===")


class LLMManager:
    """Manages multiple LLM providers using LangChain."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.clients: Dict[str, LLMClient] = {}
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize LLM clients using unified implementation."""
        # Initialize each configured LLM provider
        for provider_name in self.settings.llm_providers.keys():
            try:
                config = self.settings.get_llm_config(provider_name)
                
                if not config.get("api_key"):
                    logger.warning(f"Skipping {provider_name}: No API key provided")
                    continue
                
                # Use unified client for all providers
                client = LLMClient(provider_name, config)
                self.clients[provider_name] = client
                logger.info(f"Initialized LLM client: {provider_name}")
                
            except Exception as e:
                logger.error(f"Failed to initialize LLM client {provider_name}: {str(e)}")
    
    def get_client(self, provider: str = None) -> Optional[LLMClient]:
        """Get an LLM client by provider name."""
        if not provider:
            provider = self.settings.default_llm_provider
        
        return self.clients.get(provider)
    
    async def generate_response(self, 
                              messages: List[LLMMessage],
                              session_id: str,
                              provider: str = None) -> str:
        """Generate a response using the specified or default LLM provider.
        
        Args:
            messages: List of messages for the conversation
            session_id: Required session ID for timeline logging and tracking
            provider: Optional provider override (uses default if not specified)
        """
        client = self.get_client(provider)
        if not client:
            available = list(self.clients.keys())
            raise Exception(f"LLM provider not available. Available: {available}")
        
        return await client.generate_response(messages, session_id)

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