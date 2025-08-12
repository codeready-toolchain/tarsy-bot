"""
Chain processing models for sequential agent workflows.

These models define the structure for chain definitions, stages,
and chain processing metadata.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ChainStageModel:
    """
    Represents a single stage in a processing chain.
    
    Each stage defines an agent to execute and optional strategy override.
    """
    name: str                    # Human-readable stage name
    agent: str                   # Agent identifier (class name or "ConfigurableAgent:agent-name")
    iteration_strategy: Optional[str] = None  # Optional iteration strategy override (uses agent's default if not specified)


@dataclass
class ChainDefinitionModel:
    """
    Complete definition of a processing chain.
    
    Chains map alert types to sequential workflows with multiple stages.
    """
    chain_id: str               # Unique chain identifier  
    alert_types: List[str]      # Alert types this chain handles
    stages: List[ChainStageModel]  # Sequential stages (1+ stages)
    description: Optional[str] = None