"""
Base iteration controller interface and shared types.

This module provides the minimal interface and types needed by 
all iteration controller implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..base_agent import BaseAgent


@dataclass
class IterationContext:
    """
    Shared context between agent and iteration controller.
    
    This context contains all the data needed for iteration processing
    and provides a reference back to the agent for accessing shared methods.
    """
    alert_data: Dict[str, Any]
    runbook_content: str
    available_tools: List[Dict[str, Any]]
    session_id: str
    agent: Optional['BaseAgent'] = None


class IterationController(ABC):
    """
    Abstract controller for different iteration processing strategies.
    
    This allows clean separation between ReAct and regular processing flows
    without conditional logic scattered throughout the BaseAgent.
    """
    
    @abstractmethod
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """
        Execute the complete analysis iteration loop.
        
        Args:
            context: Iteration context containing all necessary data
            
        Returns:
            Final analysis result string
        """
        pass