"""
New context architecture for alert processing.

This module contains the context models.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from mcp.types import Tool
from pydantic import BaseModel, ConfigDict, Field

from .agent_execution_result import AgentExecutionResult, ParallelStageResult
from .alert import ProcessingAlert
from .constants import IterationStrategy, StageStatus
from .mcp_selection_models import MCPSelectionConfig

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent


@dataclass
class ChatMessageContext:
    """Typed container for chat message context passed to ChatReActController."""
    conversation_history: str
    user_question: str
    chat_id: str


@dataclass
class SessionContextData:
    """Typed container for captured session context."""
    conversation_history: str
    chain_id: str
    captured_at_us: int


class ToolWithServer(BaseModel):
    """Official MCP Tool with server context for action naming."""
    model_config: ConfigDict = ConfigDict(extra="forbid")
    
    server: str = Field(..., description="MCP server name", min_length=1)
    tool: Tool = Field(..., description="Official MCP Tool object with full schema information")


class AvailableTools(BaseModel):
    """
    Available tools for agent processing using official MCP Tool objects.
    
    Uses official mcp.types.Tool with full JSON Schema support for enhanced LLM guidance.
    """
    model_config: ConfigDict = ConfigDict(extra="forbid")
    
    tools: List[ToolWithServer] = Field(
        default_factory=list,
        description="Available MCP tools with server context"
    )


class ChainContext(BaseModel):
    """
    Context for entire chain processing session.
    
    Uses composition to keep ProcessingAlert as a single source of truth
    for alert metadata and client data, while ChainContext manages session
    and execution state.
    
    This design follows the principle: "Different purposes deserve different models"
    - ProcessingAlert = Alert state (metadata + client data)
    - ChainContext = Session state (alert + execution + history)
    """
    model_config: ConfigDict = ConfigDict(extra="forbid", frozen=False)
    
    # === Alert state (composed) ===
    processing_alert: ProcessingAlert = Field(
        ..., 
        description="Complete alert state including metadata and client data"
    )
    
    # === Session state ===
    session_id: str = Field(..., description="Processing session ID", min_length=1)
    current_stage_name: str = Field(..., description="Currently executing stage name", min_length=1)
    stage_outputs: Dict[str, Union[AgentExecutionResult, ParallelStageResult]] = Field(
        default_factory=dict,
        description="Results from completed stages (single or parallel)"
    )
    author: Optional[str] = Field(
        None, 
        description="User or API Client who submitted the alert (from oauth2-proxy X-Forwarded-User header)"
    )
    
    # === MCP Configuration Override ===
    mcp: Optional[MCPSelectionConfig] = Field(
        None,
        description="Optional MCP server/tool selection to override default agent configuration (applies to all stages)"
    )
    
    # === Processing support ===
    runbook_content: Optional[str] = Field(None, description="Downloaded runbook content")
    chain_id: Optional[str] = Field(None, description="Chain identifier")
    
    # === Chat-specific context ===
    chat_context: Optional[ChatMessageContext] = Field(
        None,
        description="Chat-specific context (only present for chat executions)"
    )
    
    @classmethod
    def from_processing_alert(
        cls,
        processing_alert: ProcessingAlert,
        session_id: str,
        current_stage_name: str = "initializing",
        author: Optional[str] = None
    ) -> "ChainContext":
        """
        Create ChainContext from ProcessingAlert.
        
        This is the preferred way to create ChainContext from API alerts.
        
        Args:
            processing_alert: Processed alert with metadata
            session_id: Processing session ID
            current_stage_name: Initial stage name
            author: User or API Client who submitted the alert (optional, from oauth2-proxy X-Forwarded-User header)
            
        Returns:
            ChainContext ready for processing
        """
        return cls(
            processing_alert=processing_alert,
            session_id=session_id,
            current_stage_name=current_stage_name,
            author=author,
            mcp=processing_alert.mcp  # Pass through MCP selection from alert
        )
    
    def get_runbook_content(self) -> str:
        """Get downloaded runbook content."""
        return self.runbook_content or ""
    
    def get_previous_stages_results(self) -> List[tuple[str, Union[AgentExecutionResult, ParallelStageResult]]]:
        """
        Get completed stage results in execution order.
        
        Returns results as ordered list of (stage_name, result) tuples.
        Dict preserves insertion order (Python 3.7+) so iteration order = execution order.
        Includes both single agent and parallel stage results.
        
        Note: stage_outputs keys are execution_ids, but we return (stage_name, result) tuples
        by extracting stage_name from the result object itself.
        """
        return [
            (result.stage_name, result)
            for result in self.stage_outputs.values()
            if (isinstance(result, AgentExecutionResult) and result.status == StageStatus.COMPLETED)
            or (isinstance(result, ParallelStageResult) and result.status == StageStatus.COMPLETED)
        ]
    
    def get_previous_stage_results(self) -> List[tuple[str, Union[AgentExecutionResult, ParallelStageResult]]]:
        """
        Alias for get_previous_stages_results() for consistency.
        
        This method name matches the naming pattern used in the EP document.
        """
        return self.get_previous_stages_results()
    
    def is_parallel_stage(self, stage_name: str) -> bool:
        """
        Check if a stage has parallel execution.
        
        Args:
            stage_name: Name of the stage to check
            
        Returns:
            True if the stage result is a ParallelStageResult, False otherwise
        """
        # Search for result by stage_name (keys are execution_ids)
        for result in self.stage_outputs.values():
            if result.stage_name == stage_name and isinstance(result, ParallelStageResult):
                return True
        return False
    
    def get_last_stage_result(self) -> Optional[Union[AgentExecutionResult, ParallelStageResult]]:
        """
        Get the most recent stage result for automatic synthesis.
        
        Returns:
            The last stage result or None if no stages have completed
        """
        if not self.stage_outputs:
            return None
        # Dict preserves insertion order (Python 3.7+), so last item is most recent
        return list(self.stage_outputs.values())[-1]
    
    def add_stage_result(self, execution_id: str, result: Union[AgentExecutionResult, ParallelStageResult]):
        """Add result from a completed stage (single or parallel), keyed by execution_id."""
        self.stage_outputs[execution_id] = result
    
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
        return self.chain_context.processing_alert.alert_data.copy()
    
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
    def previous_stages_results(self) -> List[tuple[str, Union[AgentExecutionResult, ParallelStageResult]]]:
        """Previous stage results in execution order (includes parallel stages)."""
        return self.chain_context.get_previous_stages_results()
    
    def has_previous_stages(self) -> bool:
        """Check if there are completed previous stages."""
        return len(self.previous_stages_results) > 0
    
    def _is_synthesis_strategy(self) -> bool:
        """Check if current agent uses synthesis strategy."""
        strategy = self.agent.iteration_strategy
        return strategy in [IterationStrategy.SYNTHESIS, IterationStrategy.SYNTHESIS_NATIVE_THINKING]
    
    def format_previous_stages_context(self) -> str:
        """
        Format previous stage results for prompts in execution order.
        Handles both single agent and parallel stage results.
        """
        results = self.previous_stages_results
        if not results:
            return "No previous stage context available."
        
        sections = []
        for stage_name, result in results:  # Iterating over ordered list
            if isinstance(result, ParallelStageResult):
                # Format parallel stage results
                sections.append(f"### Results from parallel stage '{stage_name}':")
                sections.append("")
                sections.append(f"**Parallel Execution Summary**: {result.metadata.successful_count}/{result.metadata.total_count} agents succeeded")
                sections.append("")
                
                # Format each parallel agent's result
                for idx, (agent_result, agent_meta) in enumerate(
                    zip(result.results, result.metadata.agent_metadatas, strict=True),
                    1,
                ):
                    sections.append(f"#### Agent {idx}: {agent_meta.agent_name} ({agent_meta.llm_provider}, {agent_meta.iteration_strategy})")
                    sections.append(f"**Status**: {agent_meta.status.value}")
                    if agent_meta.error_message:
                        sections.append(f"**Error**: {agent_meta.error_message}")
                    sections.append("")
                    
                    # Use investigation_history for synthesis strategies, complete_conversation_history for others
                    if self._is_synthesis_strategy():
                        content = agent_result.investigation_history or agent_result.result_summary or ""
                    else:
                        content = agent_result.complete_conversation_history or agent_result.result_summary or ""
                    
                    # Wrap the analysis result content with HTML comment boundaries
                    sections.append("<!-- Analysis Result START -->")
                    escaped_content = content.replace("-->", "--&gt;").replace("<!--", "&lt;!--")
                    sections.append(escaped_content)
                    sections.append("<!-- Analysis Result END -->")
                    sections.append("")
            else:
                # Format single agent result (existing logic)
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