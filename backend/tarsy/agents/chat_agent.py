"""
ChatAgent for handling follow-up chat conversations.

This agent inherits from BaseAgent and is specifically designed for handling
follow-up questions about completed alert investigations. It uses ReAct iteration
strategy and receives MCP server configuration dynamically from the chat context.
"""

from typing import List

from tarsy.agents.base_agent import BaseAgent
from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.constants import IterationStrategy
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class ChatAgent(BaseAgent):
    """
    Built-in agent for handling follow-up chat conversations with ReAct iteration.
    
    Unlike regular agents, ChatAgent does not define default MCP servers.
    Instead, it dynamically receives MCP configuration from ChainContext.mcp,
    ensuring access to the same servers/tools used in the original investigation.
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry
    ):
        """
        Initialize ChatAgent with ReAct iteration strategy.
        
        Args:
            llm_client: Client for LLM interactions
            mcp_client: MCP client for tool access
            mcp_registry: Registry of available MCP servers
        """
        super().__init__(
            llm_client,
            mcp_client,
            mcp_registry,
            iteration_strategy=IterationStrategy.REACT
        )
        self.prompt_builder = PromptBuilder()
    
    def agent_name(self) -> str:
        """
        Return the agent name for identification.
        
        Returns:
            Agent name string
        """
        return "ChatAgent"
    
    def mcp_servers(self) -> List[str]:
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
