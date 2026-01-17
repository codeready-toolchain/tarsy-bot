"""
Aggregate configuration for agent execution.

This module provides a unified configuration object that aggregates all execution
parameters (LLM provider, iteration strategy, max iterations, force conclusion, 
MCP servers) resolved from the configuration hierarchy.

This replaces individual parameter passing for cleaner APIs and easier extension.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AgentExecutionConfig:
    """
    Aggregated configuration for agent execution.
    
    Replaces individual parameter passing (llm_provider, iteration_strategy,
    max_iterations, force_conclusion, mcp_servers) for cleaner APIs and easier extension.
    
    All fields are resolved from the configuration hierarchy:
    - parallel_agent → stage → chain → agent → system (lowest precedence)
    
    NOTE: Alert-level MCP override (ChainContext.mcp / MCPSelectionConfig) is handled
    separately in BaseAgent._get_available_tools() and takes precedence over the
    mcp_servers field resolved here.
    
    Attributes:
        llm_provider: Optional LLM provider name for this agent execution
        iteration_strategy: Optional iteration strategy (react, native-thinking, etc.)
        max_iterations: Maximum number of LLM->MCP iteration loops
        force_conclusion: Force conclusion when max iterations reached vs pause
        mcp_servers: Optional list of MCP server IDs to use (None = use agent default)
    """
    
    llm_provider: Optional[str] = None
    iteration_strategy: Optional[str] = None
    max_iterations: Optional[int] = None
    force_conclusion: Optional[bool] = None
    mcp_servers: Optional[List[str]] = None
    
    # Future extensions can be added here without changing method signatures
    # Examples: timeout_seconds, retry_policy, telemetry_config, etc.
