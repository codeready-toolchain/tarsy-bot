"""
LangChain-based prompt builder with template composition.

This module implements the PromptBuilder using LangChain templates
for clean, composable prompt generation.
"""

from typing import List, Optional, TYPE_CHECKING
from tarsy.utils.logger import get_module_logger
from tarsy.models.processing_context import ToolWithServer

if TYPE_CHECKING:
    from tarsy.models.processing_context import StageContext
from .components import (
    AlertSectionTemplate, 
    RunbookSectionTemplate
)
from .templates import (
    ANALYSIS_QUESTION_TEMPLATE,
    CONTEXT_SECTION_TEMPLATE,
    FINAL_ANALYSIS_PROMPT_TEMPLATE,
    MCP_SUMMARIZATION_SYSTEM_TEMPLATE,
    MCP_SUMMARIZATION_USER_TEMPLATE,
    REACT_FORMATTING_INSTRUCTIONS,
    REACT_SYSTEM_TEMPLATE,
    STAGE_ANALYSIS_QUESTION_TEMPLATE,
    STANDARD_REACT_PROMPT_TEMPLATE,
)

logger = get_module_logger(__name__)


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
    
    def get_chat_instructions(self) -> str:
        """Get instructions for ChatAgent handling follow-up questions."""
        return """You are an AI SRE assistant helping with follow-up questions about an alert investigation.

The user has reviewed a completed investigation and has a follow-up question.

Guidelines:
1. Reference the investigation history when relevant
2. Use tools to gather fresh data if needed  
3. If the question is ambiguous, ask for clarification in your Final Answer
"""
    
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
    
    def build_chat_user_message(
        self,
        conversation_history: str,
        user_question: str
    ) -> str:
        """
        Build user message for chat that includes conversation history.
        
        This formats the chat prompt by:
        1. Including the complete investigation history
        2. Clearly marking the transition to follow-up chat
        3. Presenting the user's question
        4. Providing instructions for the ReAct loop
        
        Args:
            conversation_history: Formatted investigation history from session
            user_question: User's follow-up question
        
        Returns:
            Formatted user message string for LLM
        """
        return f"""{conversation_history}

================================================================================
FOLLOW-UP CHAT SESSION
================================================================================

The user has reviewed the investigation above and has a follow-up question.

You have access to the same tools that were used in the original investigation
(they are listed in the "Initial Investigation Request" section above).

**User's Follow-up Question:**

{user_question}

**Your Task:**

Answer the user's question using the ReAct format shown in your instructions.
Reference the investigation history when relevant, and use tools to gather 
fresh data if needed.

Begin your ReAct reasoning:
"""
    
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