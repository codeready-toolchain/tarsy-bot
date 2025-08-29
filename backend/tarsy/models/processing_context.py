"""
New context architecture for alert processing.

This module contains the context models.
"""

from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from .agent_execution_result import AgentExecutionResult
from .constants import StageStatus

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent


class MCPTool(BaseModel):
    """Structured representation of an MCP tool."""
    model_config: ConfigDict = ConfigDict(extra="forbid")
    
    server: str = Field(..., description="MCP server name", min_length=1)
    name: str = Field(..., description="Tool name", min_length=1)
    description: str = Field(..., description="Tool description")
    parameters: List[Dict[str, Any]] = Field(default_factory=list, description="Tool parameters schema")


class AvailableTools(BaseModel):
    """
    Available tools for agent processing.
    
    Clean implementation using only structured MCPTool objects.
    """
    model_config: ConfigDict = ConfigDict(extra="forbid")
    
    tools: List[MCPTool] = Field(
        default_factory=list,
        description="Available MCP tools"
    )
    
    def to_prompt_format(self) -> str:
        """Format tools for prompt inclusion."""
        if not self.tools:
            return "No tools available."
        
        formatted_tools = [f"{tool.server}.{tool.name}: {tool.description}" for tool in self.tools]
        return "\n".join(formatted_tools)


class ChainContext(BaseModel):
    """
    Context for entire chain processing session:
    
    - session_id is always included (no separate parameter passing)
    - stage_outputs has correct type annotation (AgentExecutionResult, not Dict)
    - API-only methods (get_severity, get_environment) removed
    - Stage execution order preserved via Dict insertion order
    """
    model_config: ConfigDict = ConfigDict(extra="forbid", frozen=False)
    
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
            if isinstance(result, AgentExecutionResult) and result.status is StageStatus.COMPLETED
        ]
    
    def add_stage_result(self, stage_name: str, result: AgentExecutionResult):
        """Add result from a completed stage."""
        self.stage_outputs[stage_name] = result
    
    def get_runbook_url(self) -> Optional[str]:
        """Extract runbook URL from alert data."""
        return self.alert_data.get('runbook')
    
    def set_chain_context(self, chain_id: str, stage_name: Optional[str] = None):
        """Set chain context information."""
        self.chain_id = chain_id
        if stage_name:
            self.current_stage_name = stage_name
    
    def set_runbook_content(self, content: str):
        """Set downloaded runbook content."""
        self.runbook_content = content


@dataclass
class StageContext:
    """
    Context for single stage execution.
    """
    
    # Core references
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
        """
        results = self.previous_stages_results
        if not results:
            return "No previous stage context available."
        
        sections = []
        for stage_name, result in results:  # Iterating over ordered list
            stage_title = result.stage_description or stage_name
            sections.append(f"### Results from '{stage_title}' stage:")
            sections.append("")
            sections.append("#### Analysis Result")
            sections.append("")
            
            # Use complete conversation history if available, otherwise fall back to result_summary
            # Default to empty string to ensure content is never None
            content = result.complete_conversation_history or result.result_summary or ""
            
            # Remove existing "## Analysis Result" header from content if present
            # Check for header after stripping leading whitespace to handle indented content
            stripped_content = content.lstrip()
            if stripped_content.startswith("## Analysis Result"):
                # Split by lines and skip the header line
                lines = content.split('\n')
                lines = lines[1:]  # Skip the "## Analysis Result" header line
                
                # Skip empty line after header if present
                if lines and lines[0].strip() == "":
                    lines = lines[1:]
                
                content = '\n'.join(lines)
            
            # Wrap the analysis result content with HTML comment boundaries
            sections.append("<!-- Analysis Result START -->")
            escaped_content = content.replace("-->", "--&gt;").replace("<!--", "&lt;!--")
            sections.append(escaped_content)
            sections.append("<!-- Analysis Result END -->")
            sections.append("")
        
        return "\n".join(sections)