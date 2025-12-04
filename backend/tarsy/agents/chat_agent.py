"""
ChatAgent for handling follow-up chat conversations.

This agent inherits from BaseAgent and is specifically designed for handling
follow-up questions about completed alert investigations. It uses ReAct iteration
strategy and receives MCP server configuration dynamically from the chat context.
"""

from typing import List

from tarsy.agents.base_agent import BaseAgent
from tarsy.agents.iteration_controllers.base_controller import IterationController
from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.constants import IterationStrategy
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class ChatAgent(BaseAgent):
    """
    Built-in agent for handling follow-up chat conversations.
    
    Supports both ReAct and NativeThinking iteration strategies, matching
    the strategy used in the parent session's chain configuration.
    
    Unlike regular agents, ChatAgent does not define default MCP servers.
    Instead, it dynamically receives MCP configuration from ChainContext.mcp,
    ensuring access to the same servers/tools used in the original investigation.
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry,
        iteration_strategy: IterationStrategy = IterationStrategy.REACT
    ):
        """
        Initialize ChatAgent with specified iteration strategy.
        
        The strategy should match the parent session's chain configuration
        (typically the last stage's strategy) for consistency.
        
        Args:
            llm_client: Client for LLM interactions
            mcp_client: MCP client for tool access
            mcp_registry: Registry of available MCP servers
            iteration_strategy: Strategy to use (defaults to REACT, but can be
                              NATIVE_THINKING for Gemini sessions)
        """
        super().__init__(
            llm_client,
            mcp_client,
            mcp_registry,
            iteration_strategy=iteration_strategy
        )
        self.prompt_builder = PromptBuilder()
        logger.info(f"ChatAgent initialized with iteration strategy: {iteration_strategy.value}")
    
    def _get_general_instructions(self) -> str:
        """
        Override to provide chat-specific general instructions.
        
        Unlike regular agents (which focus on alert analysis), ChatAgent
        provides instructions focused on handling follow-up conversations
        about completed investigations.
        
        Returns:
            Chat-specific general instruction text
        """
        return self.prompt_builder.get_chat_general_instructions()
    
    def _create_iteration_controller(self, strategy: IterationStrategy) -> IterationController:
        """
        Create chat-specific iteration controller based on strategy.
        
        ChatAgent uses chat-specific controllers that build initial conversation
        with investigation history context.
        
        Args:
            strategy: Iteration strategy (REACT or NATIVE_THINKING)
            
        Returns:
            Chat-specific controller instance (ChatReActController or ChatNativeThinkingController)
        """
        if strategy == IterationStrategy.NATIVE_THINKING:
            from tarsy.agents.iteration_controllers.chat_native_thinking_controller import ChatNativeThinkingController
            logger.info("Using ChatNativeThinkingController for Gemini native thinking")
            return ChatNativeThinkingController(self.llm_client, self._prompt_builder)
        else:
            # Default to ChatReActController for REACT and other strategies
            from tarsy.agents.iteration_controllers.chat_react_controller import ChatReActController
            logger.info("Using ChatReActController for ReAct-based chat")
            return ChatReActController(self.llm_client, self._prompt_builder)
    
    def agent_name(self) -> str:
        """
        Return the agent name for identification.
        
        Returns:
            Agent name string
        """
        return "ChatAgent"
    
    @classmethod
    def mcp_servers(cls) -> List[str]:
        """
        Return empty list - ChatAgent uses dynamic MCP from ChainContext.mcp.
        
        Unlike regular agents (which define default MCP servers), ChatAgent ALWAYS
        uses the MCP configuration from the parent session via ChainContext.mcp.
        
        This ensures chat has access to the EXACT same servers/tools that were
        available during the original investigation - whether those came from:
        - Custom MCP selection in the alert request, OR
        - Default servers from the chain/stage configuration
        
        Returns:
            Empty list (servers configured dynamically via ChainContext)
        """
        return []
    
    def custom_instructions(self) -> str:
        """
        Generate instructions for chat agent.
        
        Note: The conversation history is NOT included here - it's added
        to the first user message by the chat-specific ReAct controller.
        
        Returns:
            Instructions for handling follow-up chat conversations
        """
        return self.prompt_builder.get_chat_instructions()
