"""
Synthesis Agent for synthesizing parallel investigation results.

This agent analyzes and synthesizes results from multiple parallel agent
investigations into a unified analysis with quality-based filtering.
"""

from typing import List

from tarsy.agents.base_agent import BaseAgent
from tarsy.integrations.llm.manager import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.agent_config import IterationStrategy
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class SynthesisAgent(BaseAgent):
    """
    Synthesis agent for combining parallel investigation results.
    
    This agent analyzes results from multiple parallel investigations and
    produces a unified root cause analysis and recommendations. It focuses
    on quality assessment and evidence-based synthesis rather than meta-analysis.
    """

    def __init__(
        self,
        llm_manager: LLMManager,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry,
        iteration_strategy: IterationStrategy = IterationStrategy.SYNTHESIS
    ):
        """
        Initialize the Synthesis Agent.

        Args:
            llm_manager: LLM manager for accessing LLM clients
            mcp_client: Client for MCP server interactions
            mcp_registry: Registry of MCP server configurations
            iteration_strategy: Iteration strategy to use (default: SYNTHESIS)
        """
        super().__init__(
            llm_manager=llm_manager,
            mcp_client=mcp_client,
            mcp_registry=mcp_registry,
            iteration_strategy=iteration_strategy
        )

    @classmethod
    def mcp_servers(cls) -> List[str]:
        """
        Define MCP servers for this agent.
        
        SynthesisAgent performs pure analysis and doesn't need tools.
        
        Returns:
            Empty list - no MCP servers needed
        """
        return []

    def custom_instructions(self) -> str:
        """
        Custom instructions for the Synthesis Agent.
        
        Returns:
            Instructions for synthesizing parallel investigation results
        """
        return """You are an Incident Commander synthesizing results from multiple parallel investigations.

Your task:
1. CRITICALLY EVALUATE each investigation's quality - prioritize results with strong evidence and sound reasoning
2. DISREGARD or deprioritize low-quality results that lack supporting evidence or contain logical errors
3. ANALYZE the original alert using the best available data from parallel investigations
4. INTEGRATE findings from high-quality investigations into a unified understanding
5. RECONCILE conflicting information by assessing which analysis provides better evidence
6. PROVIDE definitive root cause analysis based on the most reliable evidence
7. GENERATE actionable recommendations leveraging insights from the strongest investigations

Focus on solving the original alert/issue, not on meta-analyzing agent performance or comparing approaches.

Use the internet search tool to gather the latest information related to the original alert/issue to help with your task."""

