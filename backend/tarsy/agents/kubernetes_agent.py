"""
Kubernetes specialized agent for handling Kubernetes-related alerts.

This agent inherits from BaseAgent and specializes in Kubernetes operations
by defining specific MCP servers and custom instructions.
"""

from typing import List

from tarsy.utils.logger import get_module_logger

from .base_agent import BaseAgent

logger = get_module_logger(__name__)


class KubernetesAgent(BaseAgent):
    """
    Specialized agent for Kubernetes-related alert analysis.
    
    This agent leverages the kubernetes-server MCP server and provides
    Kubernetes-specific analysis capabilities.
    """
    
    @classmethod
    def mcp_servers(cls) -> List[str]:
        """
        Return the MCP server IDs required for Kubernetes operations.
        
        Returns:
            List containing only the kubernetes-server ID
        """
        return ["kubernetes-server"]
    
    def custom_instructions(self) -> str:
        """
        Return Kubernetes-specific custom instructions.
        
        Currently returns empty as the kubernetes-server instructions
        from the MCP registry provide sufficient guidance.
        
        Returns:
            Empty string (no additional custom instructions)
        """
        return ""
 