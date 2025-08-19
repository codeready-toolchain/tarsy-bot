"""
New context architecture for alert processing.

This module contains the clean context models that will replace the current
AlertProcessingData, IterationContext, PromptContext, and ChainExecutionContext
to eliminate duplication and architectural debt.

TEMPORARY MIGRATION PHASE: During migration, this module coexists with old models.
All TEMPORARY conversion utilities will be DELETED in Phase 6 cleanup.
"""

from pydantic import BaseModel, Field
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Union, TYPE_CHECKING
from .agent_execution_result import AgentExecutionResult

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent


class MCPTool(BaseModel):
    """Structured representation of an MCP tool."""
    model_config = {"extra": "forbid"}
    
    server: str = Field(..., description="MCP server name", min_length=1)
    name: str = Field(..., description="Tool name", min_length=1)
    description: str = Field(..., description="Tool description")
    parameters: List[Dict[str, Any]] = Field(default_factory=list, description="Tool parameters schema")


class AvailableTools(BaseModel):
    """
    Available tools with migration safety support.
    
    During migration (Phases 1-5), supports both structured MCPTool objects and
    legacy Dict[str, Any] format. In Phase 6, Union type will be removed and
    only List[MCPTool] will remain.
    """
    model_config = {"extra": "forbid"}
    
    tools: List[Union[MCPTool, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Available tools (supports both MCPTool and legacy format during migration)"
    )
    
    @classmethod
    def from_legacy_format(cls, legacy_tools: List[Dict[str, Any]]) -> 'AvailableTools':
        """
        TEMPORARY: Convert legacy List[Dict] to AvailableTools during migration.
        
        This method will be COMPLETELY REMOVED in Phase 6 cleanup.
        """
        return cls(tools=legacy_tools)
    
    def to_prompt_format(self) -> str:
        """Format tools for prompt inclusion."""
        if not self.tools:
            return "No tools available."
        
        formatted_tools = []
        for tool in self.tools:
            if isinstance(tool, MCPTool):
                # Clean structured format
                formatted_tools.append(f"{tool.server}.{tool.name}: {tool.description}")
            else:
                # Legacy Dict[str, Any] format during migration
                server = tool.get('server', 'unknown')
                name = tool.get('name', 'tool')
                description = tool.get('description', 'No description')
                formatted_tools.append(f"{server}.{name}: {description}")
        
        return "\n".join(formatted_tools)


class ChainContext(BaseModel):
    """
    Context for entire chain processing session.
    
    This replaces AlertProcessingData with cleaner architecture:
    - session_id is always included (no separate parameter passing)
    - stage_outputs has correct type annotation (AgentExecutionResult, not Dict)
    - API-only methods (get_severity, get_environment) removed
    - Stage execution order preserved via Dict insertion order
    """
    model_config = {"extra": "forbid", "frozen": False}
    
    # Core data - session_id is now required field
    alert_type: str = Field(..., description="Type of alert (kubernetes, aws, etc.)", min_length=1)
    alert_data: Dict[str, Any] = Field(..., description="Flexible client alert data", min_length=1)
    session_id: str = Field(..., description="Processing session ID", min_length=1)
    
    # Chain execution state
    current_stage_name: str = Field(..., description="Currently executing stage name", min_length=1)
    stage_outputs: Dict[str, AgentExecutionResult] = Field(
        default_factory=dict,
        description="Results from completed stages (FIXED: correct type annotation)"
    )
    
    # Processing support
    runbook_content: Optional[str] = Field(None, description="Downloaded runbook content")
    chain_id: Optional[str] = Field(None, description="Chain identifier")
    
    def get_original_alert_data(self) -> Dict[str, Any]:
        """Get clean original alert data without processing artifacts."""
        return self.alert_data.copy()
    
    def get_runbook_content(self) -> str:
        """Get downloaded runbook content."""
        return self.runbook_content or ""
    
    def get_previous_stages_results(self) -> List[tuple[str, AgentExecutionResult]]:
        """
        Get completed stage results in execution order.
        
        Returns results as ordered list of (stage_name, result) tuples.
        Dict preserves insertion order (Python 3.7+) so iteration order = execution order.
        """
        return [
            (stage_name, result)
            for stage_name, result in self.stage_outputs.items()
            if result.status.value == "completed"
        ]
    
    def add_stage_result(self, stage_name: str, result: AgentExecutionResult):
        """Add result from a completed stage."""
        self.stage_outputs[stage_name] = result
    
    # NOTE: get_severity() and get_environment() REMOVED
    # These are API formatting methods that belong in AlertService, not processing models


@dataclass
class StageContext:
    """
    Context for single stage execution - eliminates all field duplication.
    
    This replaces IterationContext and PromptContext with clean property-based
    architecture that derives all data from the core references without duplication.
    """
    
    # Core references (no duplication!)
    chain_context: ChainContext
    available_tools: AvailableTools
    agent: 'BaseAgent'
    
    # Convenient derived properties (computed from core references)
    @property
    def alert_data(self) -> Dict[str, Any]:
        """Alert data from chain context."""
        return self.chain_context.get_original_alert_data()
    
    @property
    def runbook_content(self) -> str:
        """Runbook content from chain context."""
        return self.chain_context.get_runbook_content()
    
    @property
    def session_id(self) -> str:
        """Session ID from chain context."""
        return self.chain_context.session_id
    
    @property
    def stage_name(self) -> str:
        """Current stage name from chain context."""
        return self.chain_context.current_stage_name
    
    @property
    def agent_name(self) -> str:
        """Agent class name."""
        return self.agent.__class__.__name__
    
    @property
    def mcp_servers(self) -> List[str]:
        """MCP servers from agent."""
        return self.agent.mcp_servers()
    
    @property
    def previous_stages_results(self) -> List[tuple[str, AgentExecutionResult]]:
        """Previous stage results in execution order."""
        return self.chain_context.get_previous_stages_results()
    
    def has_previous_stages(self) -> bool:
        """Check if there are completed previous stages."""
        return len(self.previous_stages_results) > 0
    
    def format_previous_stages_context(self) -> str:
        """
        Format previous stage results for prompts in execution order.
        
        This replaces ChainExecutionContext.get_formatted_context() with
        proper execution order preservation.
        """
        results = self.previous_stages_results
        if not results:
            return "No previous stage context available."
        
        sections = []
        for stage_name, result in results:  # Iterating over ordered list
            stage_title = result.stage_description or stage_name
            sections.append(f"## Results from '{stage_title}' stage:")
            sections.append(result.result_summary)
            sections.append("")
        
        return "\n".join(sections)


# =============================================================================
# TEMPORARY MIGRATION UTILITIES - WILL BE DELETED IN PHASE 6
# =============================================================================

def convert_legacy_tools_to_available_tools(legacy_tools: List[Dict[str, Any]]) -> AvailableTools:
    """
    TEMPORARY: Convert legacy tools list to AvailableTools.
    
    This function will be COMPLETELY REMOVED in Phase 6 cleanup.
    """
    return AvailableTools.from_legacy_format(legacy_tools)


def create_chain_context_from_alert_processing_data(
    alert_processing_data: Any,  # AlertProcessingData - avoiding import during migration
    session_id: str
) -> ChainContext:
    """
    TEMPORARY: Convert AlertProcessingData to ChainContext.
    
    This function will be COMPLETELY REMOVED in Phase 6 cleanup.
    
    Args:
        alert_processing_data: AlertProcessingData instance
        session_id: Session ID to inject into new context
        
    Returns:
        ChainContext with all data from AlertProcessingData
    """
    return ChainContext(
        alert_type=alert_processing_data.alert_type,
        alert_data=alert_processing_data.alert_data,
        session_id=session_id,  # FIXED: Inject session_id during conversion
        current_stage_name=alert_processing_data.current_stage_name or "unknown",
        stage_outputs=alert_processing_data.stage_outputs,  # Already AgentExecutionResult objects
        runbook_content=alert_processing_data.runbook_content,
        chain_id=alert_processing_data.chain_id
    )


def create_stage_context_from_iteration_context(
    iteration_context: Any,  # IterationContext - avoiding import during migration
    chain_context: ChainContext,
    agent: 'BaseAgent'
) -> StageContext:
    """
    TEMPORARY: Convert IterationContext to StageContext.
    
    This function will be COMPLETELY REMOVED in Phase 6 cleanup.
    
    Args:
        iteration_context: IterationContext instance
        chain_context: ChainContext for the stage
        agent: BaseAgent instance
        
    Returns:
        StageContext with all data from IterationContext
    """
    available_tools = convert_legacy_tools_to_available_tools(iteration_context.available_tools)
    
    return StageContext(
        chain_context=chain_context,
        available_tools=available_tools,
        agent=agent
    )
