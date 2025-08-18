"""
Kubernetes specialized agent for handling Kubernetes-related alerts.

This agent inherits from BaseAgent and specializes in Kubernetes operations
by defining specific MCP servers and custom instructions.
"""

from typing import Dict, List

from tarsy.utils.logger import get_module_logger

from .base_agent import BaseAgent

logger = get_module_logger(__name__)


class KubernetesAgent(BaseAgent):
    """
    Specialized agent for Kubernetes-related alert analysis.
    
    This agent leverages the kubernetes-server MCP server and provides
    Kubernetes-specific analysis capabilities.
    """
    
    def mcp_servers(self) -> List[str]:
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
    
    def build_mcp_tool_selection_prompt(self, alert_data: Dict, runbook_content: str, available_tools: Dict) -> str:
        """
        Build Kubernetes-specific tool selection prompt.
        
        This method enhances the default tool selection with Kubernetes-specific guidance.
        """
        # Get the base prompt with server-specific guidance
        base_prompt = super().build_mcp_tool_selection_prompt(alert_data, runbook_content, available_tools)
        
        # Add Kubernetes-specific tool selection hints
        k8s_hints = """
## Kubernetes-Specific Tool Selection Strategy

When analyzing Kubernetes issues, prioritize tools in this order:
1. **Namespace-level resources first** (pods, services, configmaps in specific namespace)
2. **Resource status and events** (describe resources to get events and conditions)
3. **Cluster-level resources only if needed** (nodes, persistent volumes, cluster-wide issues)
4. **Logs last** (pod logs can be large, use only when necessary)

Focus on the specific namespace and resources mentioned in the alert before expanding scope.
"""
        
        return base_prompt + "\n\n" + k8s_hints 