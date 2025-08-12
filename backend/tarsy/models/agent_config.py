"""
Agent configuration data models.

This module defines Pydantic models for validating agent and MCP server configurations
loaded from YAML files. These models ensure configuration data integrity and provide
clear validation errors for misconfigured agents.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator
from tarsy.models.masking_config import MaskingConfig
from tarsy.agents.constants import IterationStrategy


class AgentConfigModel(BaseModel):
    """Configuration model for a single agent.
    
    Defines what alert types an agent handles, which MCP servers it uses,
    and any custom instructions for specialized behavior.
    """
    
    model_config = ConfigDict(
        extra='forbid',
        str_strip_whitespace=True
    )
    
    alert_types: List[str] = Field(
        ...,
        description="List of alert types this agent handles",
        min_length=1
    )
    mcp_servers: List[str] = Field(
        ...,
        description="List of MCP server IDs to use for alert processing",
        min_length=1
    )
    custom_instructions: str = Field(
        default="",
        description="Agent-specific instructions for LLM behavior customization"
    )
    iteration_strategy: IterationStrategy = Field(
        default=IterationStrategy.REACT,
        description="Iteration strategy for alert processing (REGULAR or REACT)"
    )


class MCPServerConfigModel(BaseModel):
    """Configuration model for a single MCP server.
    
    Defines how to connect to and use an MCP server, including connection
    parameters and specialized instructions for the server's capabilities.
    """
    
    model_config = ConfigDict(
        extra='forbid',
        str_strip_whitespace=True
    )
    
    server_id: str = Field(
        ...,
        description="Unique server identifier used in agent configurations",
        min_length=1
    )
    server_type: str = Field(
        ...,
        description="Server type categorization (e.g., 'security', 'monitoring', 'kubernetes')",
        min_length=1
    )
    enabled: bool = Field(
        default=True,
        description="Whether this server is enabled for use"
    )
    connection_params: Dict[str, Any] = Field(
        ...,
        description="Server connection parameters (command, args, environment, etc.)"
    )
    instructions: str = Field(
        default="",
        description="Server-specific LLM instructions describing capabilities and usage"
    )
    data_masking: Optional[MaskingConfig] = Field(
        default=None,
        description="Optional data masking configuration for sensitive server data"
    )


class ChainStageConfigModel(BaseModel):
    """Configuration model for a single stage in a chain."""
    
    model_config = ConfigDict(
        extra='forbid',
        str_strip_whitespace=True
    )
    
    name: str = Field(
        ...,
        description="Human-readable stage name",
        min_length=1
    )
    agent: str = Field(
        ...,
        description="Agent identifier (class name or 'ConfigurableAgent:agent-name')",
        min_length=1
    )
    iteration_strategy: Optional[str] = Field(
        None,
        description="Optional iteration strategy override (uses agent's default if not specified)"
    )


class ChainConfigModel(BaseModel):
    """Configuration model for a single chain."""
    
    model_config = ConfigDict(
        extra='forbid',
        str_strip_whitespace=True
    )
    
    alert_types: List[str] = Field(
        ...,
        description="Alert types this chain handles",
        min_length=1
    )
    stages: List[ChainStageConfigModel] = Field(
        ...,
        description="Sequential stages (1+ stages)",
        min_length=1
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of the chain"
    )


class CombinedConfigModel(BaseModel):
    """Root configuration model for the entire config file.
    
    Contains all agent and MCP server configurations, representing the complete
    structure of an agents.yaml configuration file.
    """
    
    model_config = ConfigDict(extra='forbid')
    
    agents: Dict[str, AgentConfigModel] = Field(
        default_factory=dict,
        description="Agent configurations mapped by agent name"
    )
    mcp_servers: Dict[str, MCPServerConfigModel] = Field(
        default_factory=dict,
        description="MCP server configurations mapped by server ID"
    )
    agent_chains: Dict[str, ChainConfigModel] = Field(
        default_factory=dict,
        description="Chain configurations mapped by chain ID"
    )

    @model_validator(mode='after')
    def validate_server_ids(self) -> 'CombinedConfigModel':
        """Validate that MCP server IDs in configs match their dictionary keys."""
        for server_id, server_config in self.mcp_servers.items():
            if server_config.server_id != server_id:
                raise ValueError(
                    f"MCP server key '{server_id}' does not match server_id '{server_config.server_id}'"
                )
        return self 