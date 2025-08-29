"""
LangChain-based prompt builder with template composition.

This module implements the PromptBuilder using LangChain templates
for clean, composable prompt generation.
"""

from typing import Dict, Any, List, Optional, TYPE_CHECKING
from tarsy.utils.logger import get_module_logger

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
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        
        # Use StageContext's built-in previous stages formatting
        previous_stages_context = context.format_previous_stages_context()
        if previous_stages_context == "No previous stage context available.":
            chain_context = "## Previous Stage Data\nNo previous stage data is available for this alert. This is the first stage of analysis."
        else:
            chain_context = f"## Previous Stage Data\n{previous_stages_context}"
        
        # Build question
        question = ANALYSIS_QUESTION_TEMPLATE.format(
            alert_type=context.chain_context.alert_type,
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
        available_tools_dict = {"tools": [tool for tool in context.available_tools.tools]}
        
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(available_tools_dict),
            question=question,
            history_text=history_text
        )
    
    def build_stage_analysis_react_prompt(self, context: 'StageContext', react_history: Optional[List[str]] = None) -> str:
        """Build stage analysis ReAct prompt."""
        logger.debug("Building stage analysis ReAct prompt")
        # Build question components using StageContext properties directly
        alert_section = self.alert_component.format(context.alert_data)
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
            alert_type=context.chain_context.alert_type,
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
        available_tools_dict = {"tools": [tool for tool in context.available_tools.tools]}
        
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(available_tools_dict),
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
        
        alert_section = self.alert_component.format(context.alert_data)
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
    
    # ============ Helper Methods (Keep Current Logic) ============
    
    def _build_context_section(self, context: 'StageContext') -> str:
        """Build the context section using template."""
        server_list = ", ".join(context.mcp_servers)
        return CONTEXT_SECTION_TEMPLATE.format(
            agent_name=context.agent_name,
            server_list=server_list
        )

    def _format_available_actions(self, available_tools: Dict[str, Any]) -> str:
        """Format available tools as ReAct actions. EP-0012 clean implementation - MCPTool objects only."""
        if not available_tools or not available_tools.get("tools"):
            return "No tools available."
        
        actions = []
        for tool in available_tools["tools"]:
            # EP-0012 clean implementation: only MCPTool objects, no legacy compatibility
            action_name = f"{tool.server}.{tool.name}"
            description = tool.description
            
            if tool.parameters:
                # MCPTool.parameters is List[Dict[str, Any]]
                param_desc = ', '.join([
                    f"{param.get('name', 'param')}: {param.get('description', 'no description')}" 
                    for param in tool.parameters
                ])
                actions.append(f"{action_name}: {description}\n  Parameters: {param_desc}")
            else:
                actions.append(f"{action_name}: {description}")
        
        return '\n'.join(actions)
    
    def _flatten_react_history(self, react_history: List) -> List[str]:
        """Utility method to flatten react history and ensure all elements are strings."""
        flattened_history = []
        for item in react_history:
            if isinstance(item, list):
                flattened_history.extend(str(subitem) for subitem in item)
            else:
                flattened_history.append(str(item))
        return flattened_history