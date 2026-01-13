"""
LangChain-based prompt builder with template composition.

This module implements the PromptBuilder using LangChain templates
for clean, composable prompt generation.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from tarsy.models.processing_context import ToolWithServer
from tarsy.models.unified_interactions import LLMConversation, MessageRole
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.models.agent_execution_result import ParallelStageResult
    from tarsy.models.processing_context import StageContext
from .components import AlertSectionTemplate, RunbookSectionTemplate
from .templates import (
    ANALYSIS_QUESTION_TEMPLATE,
    CONTEXT_SECTION_TEMPLATE,
    FINAL_ANALYSIS_PROMPT_TEMPLATE,
    MCP_SUMMARIZATION_SYSTEM_TEMPLATE,
    MCP_SUMMARIZATION_USER_TEMPLATE,
    NATIVE_THINKING_ANALYSIS_TEMPLATE,
    NATIVE_THINKING_SYSTEM_TEMPLATE,
    REACT_FORMATTING_INSTRUCTIONS,
    REACT_SYSTEM_TEMPLATE,
    STAGE_ANALYSIS_QUESTION_TEMPLATE,
    STANDARD_REACT_PROMPT_TEMPLATE,
    SYNTHESIS_PROMPT_TEMPLATE,
)

logger = get_module_logger(__name__)


@dataclass
class ChatExchange:
    """Structured data for a single chat exchange."""
    user_question: str
    conversation: LLMConversation  # Full ReAct conversation for this exchange


class PromptBuilder:
    """LangChain-based prompt builder with template composition."""
    
    def __init__(self):
        # Initialize component templates
        self.alert_component = AlertSectionTemplate()
        self.runbook_component = RunbookSectionTemplate()
    
    # ============ Main Prompt Building Methods ============
    
    def build_standard_react_prompt(self, context: 'StageContext', react_history: Optional[List[str]] = None) -> str:
        """Build standard ReAct prompt."""
        logger.debug("Building ReAct prompt")
        # Build question components using StageContext properties directly
        alert_section = self.alert_component.format(context.chain_context.processing_alert)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        if previous_stages_context == "No previous stage context available.":
            chain_context = "## Previous Stage Data\nNo previous stage data is available for this alert. This is the first stage of analysis."
        else:
            chain_context = f"## Previous Stage Data\n{previous_stages_context}"
        
        # Build question
        question = ANALYSIS_QUESTION_TEMPLATE.format(
            alert_type=context.chain_context.processing_alert.alert_type,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context
        )
        
        # Build final prompt  
        history_text = ""
        if react_history:
            flattened_history = self._flatten_react_history(react_history)
            history_text = "\n".join(flattened_history) + "\n"
        
        # Format available tools from StageContext
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(context.available_tools.tools),
            question=question,
            history_text=history_text
        )
    
    def build_synthesis_prompt(self, context: 'StageContext') -> str:
        """
        Build synthesis prompt for combining parallel investigation results.
        
        Simple prompt that just asks for synthesis - all context (alert, runbook,
        previous results) is in the Previous Stage Data section formatted by StageContext.
        """
        logger.debug("Building synthesis prompt")
        
        # Build alert and runbook sections
        alert_section = self.alert_component.format(context.chain_context.processing_alert)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        # Use StageContext's built-in previous stages formatting (includes parallel results)
        previous_stages_context = context.format_previous_stages_context()
        if previous_stages_context == "No previous stage context available.":
            chain_context = "## Previous Stage Data\nNo previous stage data is available for this alert. This is the first stage of analysis."
        else:
            chain_context = f"## Previous Stage Data\n{previous_stages_context}"
        
        # Build full context with alert, runbook, and previous stages
        full_context = f"""{alert_section}

{runbook_section}

{chain_context}"""
        
        # Format with simple synthesis instruction and full context
        return SYNTHESIS_PROMPT_TEMPLATE.format(
            context=full_context,
            history_text=""
        )
    
    def build_stage_analysis_react_prompt(self, context: 'StageContext', react_history: Optional[List[str]] = None) -> str:
        """Build stage analysis ReAct prompt."""
        logger.debug("Building stage analysis ReAct prompt")
        # Build question components using StageContext properties directly
        alert_section = self.alert_component.format(context.chain_context.processing_alert)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        if previous_stages_context == "No previous stage context available.":
            chain_context = "## Previous Stage Data\nNo previous stage data is available for this alert. This is the first stage of analysis."
        else:
            chain_context = f"## Previous Stage Data\n{previous_stages_context}"
        
        # Build question
        stage_name = context.stage_name or "analysis"
        question = STAGE_ANALYSIS_QUESTION_TEMPLATE.format(
            alert_type=context.chain_context.processing_alert.alert_type,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context,
            stage_name=stage_name.upper()
        )
        
        # Build final prompt
        history_text = ""
        if react_history:
            flattened_history = self._flatten_react_history(react_history)
            history_text = "\n".join(flattened_history) + "\n"
        
        # Format available tools from StageContext
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(context.available_tools.tools),
            question=question,
            history_text=history_text
        )
    
    def build_final_analysis_prompt(self, context: 'StageContext') -> str:
        """Build final analysis prompt."""
        logger.debug("Building final analysis prompt")
        stage_info = ""
        if context.stage_name:
            stage_info = f"\n**Stage:** {context.stage_name}"
            stage_info += " (Final Analysis Stage)"  # Could add is_final_stage to StageContext if needed
            stage_info += "\n"
        
        # Build context section manually since we don't have the old helper
        server_list = ", ".join(context.mcp_servers)
        context_section = CONTEXT_SECTION_TEMPLATE.format(
            agent_name=context.agent_name,
            server_list=server_list
        )
        
        alert_section = self.alert_component.format(context.chain_context.processing_alert)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        if previous_stages_context == "No previous stage context available.":
            chain_context = "## Previous Stage Data\nNo previous stage data is available for this alert. This is the first stage of analysis."
        else:
            chain_context = f"## Previous Stage Data\n{previous_stages_context}"
        
        return FINAL_ANALYSIS_PROMPT_TEMPLATE.format(
            stage_info=stage_info,
            context_section=context_section,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context
        )
    
    # ============ System Message Methods ============
    
    def get_enhanced_react_system_message(self, composed_instructions: str, task_focus: str = "investigation and providing recommendations") -> str:
        """Get enhanced ReAct system message using template. Used by ReAct iteration controllers."""
        return REACT_SYSTEM_TEMPLATE.format(
            composed_instructions=composed_instructions,
            react_formatting_instructions=REACT_FORMATTING_INSTRUCTIONS,  # Use the constant
            task_focus=task_focus
        )
    
    def get_general_instructions(self) -> str:
        """Get general SRE instructions. Used for system prompts in Final Analysis (simplified) vs ReAct system prompts (complex)."""
        return """## General SRE Agent Instructions

You are an expert Site Reliability Engineer (SRE) with deep knowledge of:
- Kubernetes and container orchestration
- Cloud infrastructure and services
- Incident response and troubleshooting
- System monitoring and alerting
- GitOps and deployment practices

Analyze alerts thoroughly and provide actionable insights based on:
1. Alert information and context
2. Associated runbook procedures
3. Real-time system data from available tools

Always be specific, reference actual data, and provide clear next steps.
Focus on root cause analysis and sustainable solutions."""
    
    def get_chat_general_instructions(self) -> str:
        """Get general instructions specifically for ChatAgent follow-up conversations."""
        return """## Chat Assistant Instructions

You are an expert Site Reliability Engineer (SRE) assistant helping with follow-up questions about a completed alert investigation.

The user has reviewed the investigation results and has follow-up questions. Your role is to:
- Provide clear, actionable answers based on the investigation history
- Use available tools to gather fresh, real-time data when needed
- Reference specific findings from the original investigation when relevant
- Maintain the same professional SRE communication style
- Be concise but thorough in your responses

You have access to the same tools and systems that were used in the original investigation."""
    
    def get_chat_instructions(self) -> str:
        """Get additional instructions for ChatAgent handling follow-up questions."""
        return """## Response Guidelines

1. **Context Awareness**: Reference the investigation history when it provides relevant context
2. **Fresh Data**: Use tools to gather current system state if the question requires up-to-date information
3. **Clarity**: If the question is ambiguous or unclear, ask for clarification in your Final Answer
4. **Specificity**: Always reference actual data and observations, not assumptions
5. **Brevity**: Be concise but complete - users have already read the full investigation"""
    
    # ============ Native Thinking Methods (Gemini-specific) ============
    
    def get_native_thinking_system_message(
        self, 
        composed_instructions: str, 
        task_focus: str = "investigation and providing recommendations"
    ) -> str:
        """
        Get system message for native thinking controller (Gemini-specific).
        
        This is a simplified system message without ReAct format instructions
        since Gemini uses native function calling and internal reasoning.
        
        Args:
            composed_instructions: Combined agent instructions
            task_focus: Focus area for the task
            
        Returns:
            Formatted system message string
        """
        return NATIVE_THINKING_SYSTEM_TEMPLATE.format(
            composed_instructions=composed_instructions,
            task_focus=task_focus
        )
    
    def build_native_thinking_prompt(self, context: 'StageContext') -> str:
        """
        Build analysis prompt for native thinking controller.
        
        This prompt doesn't include ReAct format instructions or tool formatting
        since Gemini receives tools as native function declarations.
        
        Args:
            context: StageContext containing processing data
            
        Returns:
            Formatted user prompt string
        """
        logger.debug("Building native thinking prompt")
        
        # Build question components using StageContext properties
        alert_section = self.alert_component.format(context.chain_context.processing_alert)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        if previous_stages_context == "No previous stage context available.":
            chain_context = "## Previous Stage Data\nNo previous stage data is available for this alert. This is the first stage of analysis."
        else:
            chain_context = f"## Previous Stage Data\n{previous_stages_context}"
        
        # Build and return the native thinking prompt
        return NATIVE_THINKING_ANALYSIS_TEMPLATE.format(
            alert_type=context.chain_context.processing_alert.alert_type,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context
        )
    
    def build_mcp_summarization_system_prompt(self, server_name: str, tool_name: str, max_summary_tokens: int) -> str:
        """Build system prompt for MCP result summarization."""
        return MCP_SUMMARIZATION_SYSTEM_TEMPLATE.format(
            server_name=server_name,
            tool_name=tool_name,
            max_summary_tokens=max_summary_tokens
        )

    def build_mcp_summarization_user_prompt(self, conversation_context: str, server_name: str, 
                                           tool_name: str, result_text: str) -> str:
        """Build user prompt for MCP result summarization with investigation context."""
        return MCP_SUMMARIZATION_USER_TEMPLATE.format(
            conversation_context=conversation_context,
            server_name=server_name,
            tool_name=tool_name,
            result_text=result_text
        )
    
    # ============ Chat Formatting Methods ============
    
    def format_investigation_context(self, conversation: Optional[LLMConversation]) -> str:
        """
        Format investigation conversation as clean historical context.
        
        Extracts user/assistant messages (skips system instructions) and formats
        with clear emoji-based section markers for LLM consumption.
        
        The formatted history includes:
        - Initial investigation request (alert data, runbook, available tools)
        - All ReAct reasoning (Thought/Action cycles)
        - Tool observations (results)
        - Final analysis
        
        Args:
            conversation: LLMConversation from LLMInteraction.conversation field (can be None for cancelled sessions)
            
        Returns:
            Formatted string with investigation context section
        """
        # Handle None conversation (e.g., from cancelled sessions)
        if conversation is None:
            sections = []
            sections.append("═" * 79)
            sections.append("📋 INVESTIGATION CONTEXT")
            sections.append("═" * 79)
            sections.append("")
            sections.append("# Original Investigation")
            sections.append("")
            sections.append("⚠️  This investigation was cancelled before completion.")
            sections.append("")
            sections.append("═" * 79)
            return "\n".join(sections)
        
        sections = []
        sections.append("═" * 79)
        sections.append("📋 INVESTIGATION CONTEXT")
        sections.append("═" * 79)
        sections.append("")
        sections.append("# Original Investigation")
        sections.append("")
        
        for i, msg in enumerate(conversation.messages):
            # Skip system messages - those are instructions we'll re-add for chat
            if msg.role == MessageRole.SYSTEM:
                continue
            
            # Format each message with clear headers
            if msg.role == MessageRole.USER:
                # User messages in investigation are either:
                # - Initial prompt (tools + alert + runbook + task)
                # - Observations (tool results)
                if i == 1:  # First user message after system
                    sections.append("### Initial Investigation Request")
                    sections.append("")
                    sections.append(msg.content)
                    sections.append("")
                else:
                    # Tool result observation
                    sections.append("**Observation:**")
                    sections.append("")
                    sections.append(msg.content)
                    sections.append("")
            
            elif msg.role == MessageRole.ASSISTANT:
                # Assistant messages contain Thought/Action/Final Answer
                sections.append("**Agent Response:**")
                sections.append("")
                sections.append(msg.content)
                sections.append("")
        
        return "\n".join(sections)
    
    def format_chat_history(self, exchanges: List[ChatExchange]) -> str:
        """
        Format previous chat exchanges with full ReAct flows.
        
        Each exchange includes:
        - User's question (clean, from ChatUserMessage)
        - Complete ReAct conversation (Thought/Action/Observation/Final Answer)
        
        Args:
            exchanges: List of previous chat exchanges (ordered chronologically)
            
        Returns:
            Formatted string with chat history section, or empty string if no exchanges
        """
        if not exchanges:
            return ""
        
        sections = []
        sections.append("")
        sections.append("═" * 79)
        sections.append(f"💬 CHAT HISTORY ({len(exchanges)} previous exchange{'s' if len(exchanges) != 1 else ''})")
        sections.append("═" * 79)
        sections.append("")
        
        for i, exchange in enumerate(exchanges, 1):
            sections.append(f"## Exchange {i}")
            sections.append("")
            sections.append("**USER:**")
            sections.append(exchange.user_question)
            sections.append("")
            
            # Format the full ReAct conversation
            # Skip first USER message (contains nested investigation context)
            # Include all ASSISTANT and subsequent USER (observations) messages
            first_user_found = False
            for msg in exchange.conversation.messages:
                if msg.role == MessageRole.SYSTEM:
                    continue
                
                if msg.role == MessageRole.USER:
                    if not first_user_found:
                        # Skip first USER message (has nested context)
                        first_user_found = True
                        continue
                    else:
                        # Observation message
                        sections.append("**Observation:**")
                        sections.append("")
                        sections.append(msg.content)
                        sections.append("")
                
                elif msg.role == MessageRole.ASSISTANT:
                    # Assistant response with ReAct reasoning
                    sections.append("**ASSISTANT:**")
                    sections.append(msg.content)
                    sections.append("")
        
        return "\n".join(sections)
    
    def build_chat_user_message(
        self,
        investigation_context: str,
        user_question: str,
        chat_history: str = ""
    ) -> str:
        """
        Build complete user message for chat with all sections.
        
        Combines sections:
        1. Investigation context (pre-formatted, may already include chat history)
        2. Optional chat history (formatted previous exchanges, if provided separately)
        3. Current task (user's question with instructions)
        
        Note: investigation_context may be either:
        - Just the investigation (when called with separate chat_history), OR
        - Complete context with investigation + chat history (when called from controller)
        
        Args:
            investigation_context: Formatted investigation context (may include chat history)
            user_question: Current user question
            chat_history: Optional formatted previous exchanges (default: empty)
            
        Returns:
            Complete formatted user message for LLM
        """
        result = investigation_context
        result += chat_history  # Already includes separators if non-empty
        
        result += f"""
{"═" * 79}
🎯 CURRENT TASK
{"═" * 79}

**Question:** {user_question}

**Your Task:**
Answer the user's question based on the investigation context above.
- Reference investigation history when relevant
- Use tools to get fresh data if needed
- Provide clear, actionable responses

Begin your response:
"""
        return result
    
    # ============ Helper Methods ============
    
    def _build_context_section(self, context: 'StageContext') -> str:
        """Build the context section using template."""
        server_list = ", ".join(context.mcp_servers)
        return CONTEXT_SECTION_TEMPLATE.format(
            agent_name=context.agent_name,
            server_list=server_list
        )

    def _format_available_actions(self, available_tools: List[ToolWithServer]) -> str:
        """Format available tools with rich JSON Schema information for enhanced LLM guidance."""
        if not available_tools:
            return "No tools available."
        
        actions = []
        
        for i, tool_with_server in enumerate(available_tools, 1):
            tool = tool_with_server.tool
            action_name = f"{tool_with_server.server}.{tool.name}"
            
            # Tool name and description on one line
            actions.append(f"{i}. **{action_name}**: {tool.description or 'No description'}")
            
            # Extract rich parameters from inputSchema
            parameters_info = self._extract_parameters_from_schema(tool.inputSchema or {})
            if parameters_info:
                actions.append("    **Parameters**:")
                for param_info in parameters_info:
                    actions.append(f"    - {param_info}")
            else:
                actions.append("    **Parameters**: None")
            
            # Add empty line between tools (but not after the last tool)
            if i < len(available_tools):
                actions.append("")
        
        return "\n".join(actions)
    
    def _extract_parameters_from_schema(self, input_schema: dict) -> List[str]:
        """Extract rich parameter information from JSON Schema."""
        if not isinstance(input_schema, dict):
            return []
        
        properties = input_schema.get('properties', {})
        required_params = set(input_schema.get('required', []))
        
        param_infos = []
        
        for param_name, param_schema in properties.items():
            if not isinstance(param_schema, dict):
                continue
                
            # Build rich parameter description with better spacing
            parts = [param_name]
            
            # Add space before parentheses for better readability
            if param_name in required_params:
                parts.append(" (required")
            else:
                parts.append(" (optional")
                
            # Add type information
            param_type = param_schema.get('type')
            if param_type:
                parts.append(f", {param_type}")
            
            # Close the parenthesis
            parts[-1] += ")"
            
            # Add description
            description = param_schema.get('description', '')
            if description:
                parts.append(f": {description}")
            else:
                parts.append(": No description")
            
            # Add additional schema information for LLM guidance with consistent formatting
            schema_info = []
            
            # Default value
            if 'default' in param_schema:
                schema_info.append(f"default: {param_schema['default']}")
            
            # Enum values (constrained choices) - show all values  
            if 'enum' in param_schema:
                enum_values = ', '.join(f'"{v}"' for v in param_schema['enum'])
                schema_info.append(f"choices: [{enum_values}]")
            
            # Pattern validation for strings
            if param_type == 'string' and 'pattern' in param_schema:
                schema_info.append(f"pattern: {param_schema['pattern']}")
            
            # Numeric constraints
            if param_type in ['number', 'integer']:
                constraints = []
                if 'minimum' in param_schema:
                    constraints.append(f"min: {param_schema['minimum']}")
                if 'maximum' in param_schema:
                    constraints.append(f"max: {param_schema['maximum']}")
                if constraints:
                    schema_info.extend(constraints)
            
            # Add examples if available
            if 'examples' in param_schema and param_schema['examples']:
                example = param_schema['examples'][0] 
                schema_info.append(f"example: \"{example}\"")
            
            # Append schema information in consistent bracket format
            if schema_info:
                parts.append(f" [{'; '.join(schema_info)}]")
            
            param_infos.append(''.join(parts))
        
        return param_infos
    
    def _flatten_react_history(self, react_history: List) -> List[str]:
        """Utility method to flatten react history and ensure all elements are strings."""
        flattened_history = []
        for item in react_history:
            if isinstance(item, list):
                flattened_history.extend(str(subitem) for subitem in item)
            else:
                flattened_history.append(str(item))
        return flattened_history

    def build_final_analysis_summary_system_prompt(self) -> str:
        """
        Build system prompt for executive summary generation.
        
        Returns:
            System prompt instructing the LLM to generate brief, actionable executive summaries
        """
        return (
            "You are an expert Site Reliability Engineer assistant that creates "
            "concise 1-4 line executive summaries of incident analyses for alert notifications. "
            "Focus on clarity, brevity, and actionable information."
        )

    def build_final_analysis_summary_prompt(self, final_analysis: str) -> str:
        """Build prompt for generating executive summary of an incident analysis."""
        return f"""Generate a 1-4 line executive summary of this incident analysis.

CRITICAL RULES:
- Only summarize what is EXPLICITLY stated in the analysis
- Do NOT infer future actions or recommendations not mentioned
- Do NOT add your own conclusions
- Focus on: what happened, current status, and ONLY stated next steps

Analysis to summarize:

=================================================================================
{final_analysis}
=================================================================================

Executive Summary (1-4 lines, facts only):"""
    
    def format_parallel_stage_results(self, parallel_result: 'ParallelStageResult') -> str:
        """
        Format ParallelStageResult for SynthesisAgent or next stage consumption.
        
        Presents raw investigation results with clear sections and metadata.
        NO pre-analysis or synthesis - that's the next agent's job.
        
        For multi-agent parallelism:
        - Section per agent: "## Kubernetes Investigation", "## VM Investigation"
        
        For replica parallelism:
        - Labeled runs: "## Run 1 (openai)", "## Run 2 (anthropic)", "## Run 3 (gemini)"
        
        Includes metadata: timing, status, LLM provider, iteration strategy, token usage.
        
        Args:
            parallel_result: The parallel stage result to format
            
        Returns:
            Formatted string with parallel stage results and metadata
        """
        sections = []
        
        # Overall summary
        sections.append(f"# Parallel Stage Results: {parallel_result.metadata.parallel_type}")
        sections.append(f"**Status**: {parallel_result.status.value}")
        sections.append("")
        
        # Individual agent results
        for idx, (result, metadata) in enumerate(zip(parallel_result.results, parallel_result.metadata.agent_metadatas, strict=True), 1):
            # Header based on parallel type
            if parallel_result.metadata.parallel_type == "multi_agent":
                sections.append(f"## {metadata.agent_name} Investigation")
            else:  # replica
                sections.append(f"## Run {idx}: {metadata.agent_name}")
            
            sections.append(f"**Provider**: {metadata.llm_provider}")
            sections.append(f"**Status**: {metadata.status.value}")
            sections.append(f"**Duration**: {metadata.duration_ms}ms")
            
            if metadata.error_message:
                sections.append(f"**Error**: {metadata.error_message}")
            
            sections.append("")
            sections.append("### Investigation Result")
            sections.append("")
            
            # Use complete conversation history if available, otherwise result_summary
            content = result.complete_conversation_history or result.result_summary or "No result"
            
            # Wrap the investigation result content with HTML comment boundaries
            # This prevents the content's markdown from breaking our structure
            sections.append("<!-- Investigation Result START -->")
            sections.append(content)
            sections.append("<!-- Investigation Result END -->")
            sections.append("")
        
        return "\n".join(sections)
    
    def build_react_forced_conclusion_prompt(self, iteration_limit: int) -> str:
        """
        Build ReAct-specific forced conclusion prompt at iteration limit.
        
        Args:
            iteration_limit: The iteration count when limit was reached
            
        Returns:
            ReAct-formatted prompt requesting Final Answer
        """
        from tarsy.agents.prompts.templates import (
            FORCED_CONCLUSION_TEMPLATE,
            REACT_FORCED_CONCLUSION_FORMAT,
        )
        
        return FORCED_CONCLUSION_TEMPLATE.format(
            iteration_limit=iteration_limit,
            format_instructions=REACT_FORCED_CONCLUSION_FORMAT
        )
    
    def build_native_thinking_forced_conclusion_prompt(self, iteration_limit: int) -> str:
        """
        Build Native Thinking-specific forced conclusion prompt at iteration limit.
        
        Args:
            iteration_limit: The iteration count when limit was reached
            
        Returns:
            Natural language prompt requesting conclusion
        """
        from tarsy.agents.prompts.templates import (
            FORCED_CONCLUSION_TEMPLATE,
            NATIVE_THINKING_FORCED_CONCLUSION_FORMAT,
        )
        
        return FORCED_CONCLUSION_TEMPLATE.format(
            iteration_limit=iteration_limit,
            format_instructions=NATIVE_THINKING_FORCED_CONCLUSION_FORMAT
        )