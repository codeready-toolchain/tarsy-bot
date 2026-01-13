"""
Base iteration controller interface and shared types.

This module provides the minimal interface and types needed by 
all iteration controller implementations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from ...models.unified_interactions import LLMConversation, MessageRole
from ..parsers.react_parser import ReActParser

if TYPE_CHECKING:
    from ...agents.prompts import PromptBuilder
    from ...integrations.llm.manager import LLMManager
    from ...models.processing_context import StageContext

class IterationController(ABC):
    """
    Abstract controller for different iteration processing strategies.
    
    This allows clean separation between ReAct and regular processing flows
    without conditional logic scattered throughout the BaseAgent.
    """
    
    # LLM provider override (set by agent for per-stage/per-chain providers)
    _llm_provider_name: Optional[str] = None
    
    # Last conversation (stored for investigation_history generation)
    _last_conversation: Optional['LLMConversation'] = None
    
    def set_llm_provider(self, provider_name: Optional[str]):
        """
        Set the LLM provider override for this controller.
        
        Args:
            provider_name: Name of the LLM provider to use, or None for global default
        """
        self._llm_provider_name = provider_name
    
    def get_llm_provider(self) -> Optional[str]:
        """
        Get the LLM provider override for this controller.
        
        Returns:
            Provider name if set, or None for global default
        """
        return self._llm_provider_name
    
    def get_last_conversation(self) -> Optional['LLMConversation']:
        """
        Get the last conversation from execute_analysis_loop.
        
        Returns:
            LLMConversation if available, None otherwise
        """
        return self._last_conversation
    
    def _get_native_tools_override(self, context: 'StageContext'):
        """
        Extract native tools override from processing context.
        
        Args:
            context: StageContext containing processing alert with optional native tools config
            
        Returns:
            NativeToolsConfig if specified in alert, None otherwise
        """
        alert = getattr(context.chain_context, "processing_alert", None)
        if not alert:
            return None
        
        mcp = getattr(alert, "mcp", None)
        if not mcp:
            return None
        
        return getattr(mcp, "native_tools", None)
    
    def _restore_paused_conversation(
        self, 
        context: 'StageContext',
        logger=None
    ) -> Optional[LLMConversation]:
        """
        Check for paused session state and restore conversation if found.
        
        Uses stage execution_id as the lookup key, which is ALWAYS set before
        agent execution (in both parallel and non-parallel stages). This design
        eliminates naming conflicts and works consistently across all scenarios.
        
        Args:
            context: StageContext containing stage processing data
            logger: Optional logger for debug messages
            
        Returns:
            Restored LLMConversation if resuming from paused state, None otherwise
        """
        # Get execution_id (always set before agent.process_alert() is called)
        stage_execution_id = context.agent.get_current_stage_execution_id()
        if not stage_execution_id:
            # This should never happen in production (execution_id always set before execution)
            if logger:
                logger.error("Agent execution_id not set - cannot restore paused conversation")
            return None
        
        if logger:
            logger.debug(f"Looking up paused state with execution_id: {stage_execution_id}")
        
        # Lookup the stage result by execution_id
        if stage_execution_id not in context.chain_context.stage_outputs:
            return None
        
        stage_result = context.chain_context.stage_outputs[stage_execution_id]
        
        # Validate it's a paused AgentExecutionResult with conversation state
        if not hasattr(stage_result, 'status') or not hasattr(stage_result, 'paused_conversation_state'):
            if logger:
                logger.debug("Stage result missing required fields for restoration")
            return None
        
        # Type-safe status comparison (handle both enum and string values)
        from tarsy.models.constants import StageStatus
        status_value = stage_result.status.value if isinstance(stage_result.status, StageStatus) else stage_result.status
        
        if status_value != StageStatus.PAUSED.value or not stage_result.paused_conversation_state:
            return None
        
        # Restore conversation from paused state
        try:
            conversation = LLMConversation.model_validate(stage_result.paused_conversation_state)
            if logger:
                logger.info(f"Resuming from paused state with {len(conversation.messages)} messages")
            return conversation
        except Exception as e:
            if logger:
                logger.warning(f"Failed to restore conversation history: {e}, starting fresh")
            return None
    
    def _raise_max_iterations_exception(
        self,
        max_iterations: int,
        last_interaction_failed: bool,
        conversation: LLMConversation,
        context: 'StageContext',
        logger=None
    ) -> None:
        """
        Raise appropriate exception when max iterations reached.
        
        Args:
            max_iterations: The maximum iteration count that was reached
            last_interaction_failed: Whether the last LLM interaction failed
            conversation: Current conversation state (for resume)
            context: StageContext containing stage processing data
            logger: Optional logger for messages
            
        Raises:
            MaxIterationsFailureError: If last interaction failed
            SessionPaused: If last interaction succeeded (allows resume)
        """
        from ..exceptions import MaxIterationsFailureError, SessionPaused
        
        if last_interaction_failed:
            if logger:
                logger.error(f"Stage failed: reached maximum iterations ({max_iterations}) with failed last interaction")
            raise MaxIterationsFailureError(
                f"Stage failed: reached maximum iterations ({max_iterations}) and last LLM interaction failed",
                max_iterations=max_iterations,
                context={
                    "session_id": context.session_id,
                    "stage_execution_id": context.agent.get_current_stage_execution_id() if context.agent else None,
                    "stage_name": context.stage_name
                }
            )
        else:
            if logger:
                logger.warning(f"Session paused: reached maximum iterations ({max_iterations}) without final answer")
            raise SessionPaused(
                f"Session paused at maximum iterations ({max_iterations})",
                iteration=max_iterations,
                conversation=conversation,
                context={
                    "session_id": context.session_id,
                    "stage_execution_id": context.agent.get_current_stage_execution_id() if context.agent else None,
                    "stage_name": context.stage_name
                }
            )
    
    @abstractmethod
    def needs_mcp_tools(self) -> bool:
        """
        Determine if this iteration strategy requires MCP tool discovery.
        
        Returns:
            True if MCP tools should be discovered, False otherwise
        """
        pass
    
    @abstractmethod
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """
        Execute analysis loop with clean StageContext.
        
        Args:
            context: StageContext containing all stage processing data
            
        Returns:
            Final analysis result string
        """
        pass
    
    def build_synthesis_conversation(self, conversation: 'LLMConversation') -> str:
        """
        Build investigation history for synthesis strategies.
        
        Default implementation filters conversation to include thoughts and observations
        while excluding system messages and initial alert data.
        
        Excludes:
        - System messages (internal instructions)
        - First user message (alert data - already in context)
        
        Includes:
        - All assistant messages (thoughts, reasoning)
        - All tool observations (user messages with tool results)
        - Final answers
        
        Args:
            conversation: LLM conversation from execute_analysis_loop
            
        Returns:
            Formatted investigation history string for synthesis
        """
        if not hasattr(conversation, 'messages') or not conversation.messages:
            return ""
        
        sections = []
        first_user_seen = False
        
        for message in conversation.messages:
            # Skip system messages
            if message.role == MessageRole.SYSTEM:
                continue
            
            # Skip first user message (alert data)
            if message.role == MessageRole.USER and not first_user_seen:
                first_user_seen = True
                continue
            
            # Include all other messages
            sections.append(f"{message.role.value.upper()}: {message.content}")
        
        return "\n\n".join(sections)

    def create_result_summary(
        self, 
        analysis_result: str, 
        context: 'StageContext'
    ) -> str:
        """
        Create result summary with clean StageContext.
        
        Default implementation provides simple formatting. Individual strategies
        can override this method to provide specialized formatting.
        
        Args:
            analysis_result: Raw analysis text from execute_analysis_loop
            context: StageContext containing all stage processing data
            
        Returns:
            Formatted summary string for this iteration strategy
        """
        if not analysis_result:
            return "No analysis result generated"
        
        return f"## Analysis Result\n\n{analysis_result}"

    def extract_final_analysis(
        self, 
        analysis_result: str, 
        context: 'StageContext'
    ) -> str:
        """
        Extract final analysis with clean StageContext.
        
        This method should extract a concise, user-friendly final analysis
        from the full analysis result for API consumption.
        
        Default implementation returns the analysis result as-is. Individual strategies
        should override this method to extract relevant final analysis.
        
        Args:
            analysis_result: Raw analysis text from execute_analysis_loop
            context: StageContext containing all stage processing data
            
        Returns:
            Clean final analysis string for API/dashboard consumption
        """
        if not analysis_result:
            return "No analysis result generated"
        
        return analysis_result

    def _extract_react_final_analysis(self, analysis_result: str) -> str:
        """
        Extract final analysis from the last assistant message.
        
        Args:
            analysis_result: Last assistant message containing the Final Answer
            
        Returns:
            Extracted final analysis, or the entire message if parsing fails
        """
        if not analysis_result:
            return "No analysis generated"
        
        # Use ReActParser to extract the Final Answer section
        sections = ReActParser._extract_sections(analysis_result)
        
        # If Final Answer was found, return it
        if sections.get('final_answer'):
            final_answer = sections['final_answer'].strip()
            if final_answer:
                return final_answer
        
        # Fallback: Return the entire last assistant message
        # This ensures we always show something even if parsing fails
        return analysis_result
    