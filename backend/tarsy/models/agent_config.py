"""
Agent configuration data models.

This module defines Pydantic models for validating agent and MCP server configurations
loaded from YAML files. These models ensure configuration data integrity and provide
clear validation errors for misconfigured agents.

This module contains all configuration models
(masking, MCP servers, chains, agents) to avoid circular imports.
"""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
from .constants import IterationStrategy


# =============================================================================
# MASKING CONFIGURATION MODELS (moved from masking_config.py)
# =============================================================================

class MaskingPattern(BaseModel):
    """A single masking pattern configuration.
    
    Defines a regex pattern to match sensitive data and the replacement
    text to use when masking.
    """
    
    name: str = Field(..., description="Pattern identifier (e.g., 'security_token')")
    pattern: str = Field(..., description="Regex pattern for matching sensitive data")
    replacement: str = Field(..., description="Replacement text for matches")
    description: str = Field(..., description="Human-readable description of the pattern")
    enabled: bool = Field(True, description="Whether pattern is active")
    
    @field_validator('pattern')
    def validate_regex_pattern(cls, v: str) -> str:
        """Validate that the pattern is a valid regex.
        
        Args:
            v: The regex pattern string
            
        Returns:
            The validated pattern string
            
        Raises:
            ValueError: If the pattern is not a valid regex
        """
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        return v
    
    @field_validator('name')
    def validate_name(cls, v: str) -> str:
        """Validate that the pattern name is not empty.
        
        Args:
            v: The pattern name
            
        Returns:
            The validated pattern name
            
        Raises:
            ValueError: If the name is empty or only whitespace
        """
        if not v or not v.strip():
            raise ValueError("Pattern name cannot be empty")
        return v.strip()


class MaskingConfig(BaseModel):
    """Configuration for data masking on a specific MCP server.
    
    Defines which patterns and pattern groups to apply when masking
    sensitive data from MCP server responses.
    """
    
    enabled: bool = Field(True, description="Whether masking is enabled for this server")
    pattern_groups: List[str] = Field(
        default_factory=list,
        description="List of built-in pattern group names to apply"
    )
    patterns: List[str] = Field(
        default_factory=list,
        description="List of built-in pattern names to apply"
    )
    custom_patterns: Optional[List[MaskingPattern]] = Field(
        None,
        description="Server-specific custom patterns"
    )
    
    @field_validator('pattern_groups')
    def validate_pattern_groups(cls, v: List[str]) -> List[str]:
        """Validate pattern group names are not empty.
        
        Args:
            v: List of pattern group names
            
        Returns:
            The validated list of pattern group names
            
        Raises:
            ValueError: If any group name is empty
        """
        validated_groups = []
        for group in v:
            if not group or not group.strip():
                raise ValueError("Pattern group name cannot be empty")
            validated_groups.append(group.strip())
        return validated_groups
    
    @field_validator('patterns')
    def validate_patterns(cls, v: List[str]) -> List[str]:
        """Validate pattern names are not empty.
        
        Args:
            v: List of pattern names
            
        Returns:
            The validated list of pattern names
            
        Raises:
            ValueError: If any pattern name is empty
        """
        validated_patterns = []
        for pattern in v:
            if not pattern or not pattern.strip():
                raise ValueError("Pattern name cannot be empty")
            validated_patterns.append(pattern.strip())
        return validated_patterns


# =============================================================================
# MCP RESULT SUMMARIZATION CONFIGURATION MODELS 
# =============================================================================

class SummarizationConfig(BaseModel):
    """Configuration for MCP result summarization."""
    
    model_config = ConfigDict(
        extra='forbid',
        str_strip_whitespace=True
    )
    
    enabled: bool = Field(
        default=True,
        description="Whether summarization is enabled for this server"
    )
    size_threshold_tokens: int = Field(
        default=2000,
        description="Token threshold above which results will be summarized",
        ge=100
    )
    summary_max_token_limit: int = Field(
        default=1000,
        description="Maximum tokens allowed in summary",
        ge=50
    )


# =============================================================================
# AGENT CONFIGURATION MODELS
# =============================================================================


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
        description="Iteration strategy for alert processing (REACT, REACT_STAGE, or REACT_FINAL_ANALYSIS)"
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
    summarization: Optional[SummarizationConfig] = Field(
        default_factory=lambda: SummarizationConfig(),
        description="Summarization configuration for large results"
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
    
    chain_id: str = Field(
        ...,
        description="Unique chain identifier",
        min_length=1
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
    def validate_configurable_agent_references(self) -> 'CombinedConfigModel':
        """Validate that ConfigurableAgent references in chain stages exist in agents config."""
        for chain_id, chain_config in self.agent_chains.items():
            for stage in chain_config.stages:
                if stage.agent.startswith("ConfigurableAgent:"):
                    agent_name = stage.agent[len("ConfigurableAgent:"):]
                    if agent_name not in self.agents:
                        raise ValueError(
                            f"Chain '{chain_id}' stage '{stage.name}' references missing configurable agent '{agent_name}'"
                        )
        return self

    @model_validator(mode='after')
    def validate_server_ids(self) -> 'CombinedConfigModel':
        """Validate that MCP server IDs in configs match their dictionary keys."""
        for server_id, server_config in self.mcp_servers.items():
            if server_config.server_id != server_id:
                raise ValueError(
                    f"MCP server key '{server_id}' does not match server_id '{server_config.server_id}'"
                )
        return self 