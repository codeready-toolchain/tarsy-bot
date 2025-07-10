"""
Simplified Alert Service using LangChain SRE Agent.
Replaces the complex custom logic with clean LangChain abstractions.
"""

from typing import Optional, Callable
from app.config.settings import Settings
from app.models.alert import Alert
from app.agents.sre_agent import SREAgent
from app.integrations.mcp.mcp_client import MCPClient
from app.integrations.mcp.mcp_tools import MCPToolkit
from app.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class LangChainAlertService:
    """Simplified alert service using LangChain SRE Agent."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mcp_client = MCPClient(settings)
        self.mcp_toolkit: Optional[MCPToolkit] = None
        self.sre_agent: Optional[SREAgent] = None
    
    async def initialize(self):
        """Initialize the service and all dependencies."""
        try:
            # Initialize MCP client
            await self.mcp_client.initialize()
            
            # Create MCP toolkit
            self.mcp_toolkit = MCPToolkit(self.mcp_client)
            
            # Initialize SRE agent
            self.sre_agent = SREAgent(self.settings)
            await self.sre_agent.initialize(self.mcp_toolkit)
            
            logger.info("LangChain Alert Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize LangChain Alert Service: {str(e)}")
            raise
    
    async def process_alert(self, alert: Alert, progress_callback: Optional[Callable] = None) -> str:
        """Process an alert using the LangChain SRE Agent."""
        if not self.sre_agent:
            raise Exception("SRE Agent not initialized")
        
        try:
            logger.info(f"Processing alert: {alert.alert}")
            
            # Use the SRE agent to process the alert
            result = await self.sre_agent.process_alert(alert, progress_callback)
            
            logger.info(f"Alert processing completed: {alert.alert}")
            return result
            
        except Exception as e:
            error_msg = f"Alert processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if progress_callback:
                await progress_callback(0, error_msg)
            raise Exception(error_msg)
    
    async def close(self):
        """Close all resources."""
        if self.mcp_client:
            await self.mcp_client.close()
        logger.info("LangChain Alert Service closed") 