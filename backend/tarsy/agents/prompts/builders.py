"""
LangChain-based prompt builder with template composition.

This module implements the PromptBuilder using LangChain templates
for clean, composable prompt generation.
"""

import json
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
    REACT_SYSTEM_TEMPLATE,
    STAGE_ANALYSIS_QUESTION_TEMPLATE,
    STANDARD_REACT_PROMPT_TEMPLATE,
)
# EP-0014: Import new type-safe parser for thin wrapper methods
from ..parsers.react_parser import ReActParser

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

    # ============ ReAct Response Parsing (EP-0014: Moved to ReActParser) ============
    
    def parse_react_response(self, response: str) -> Dict[str, Any]:
        """
        Parse structured ReAct response into components with robust error handling.
        
        EP-0014: Thin wrapper around type-safe ReActParser for backward compatibility.
        """
        # Use the new type-safe parser and convert to legacy format
        react_response = ReActParser.parse_response(response)
        
        # Convert type-safe response back to legacy dict format
        return {
            'thought': react_response.thought,
            'action': react_response.action,
            'action_input': react_response.action_input,
            'final_answer': react_response.final_answer,
            'is_complete': react_response.is_final_answer  # Map to legacy field name
        }
    
    def get_react_continuation_prompt(self, context_type: str = "general") -> List[str]:
        """
        Get ReAct continuation prompts for when LLM provides incomplete responses.
        
        EP-0014: Thin wrapper around type-safe ReActParser for backward compatibility.
        """
        # Use new parser and convert to legacy list format
        continuation_message = ReActParser.get_continuation_prompt(context_type)
        return [continuation_message, "Thought:"]
    
    def get_react_error_continuation(self, error_message: str) -> List[str]:
        """
        Get ReAct continuation prompts for error recovery.
        
        EP-0014: Thin wrapper around type-safe ReActParser for backward compatibility.
        """
        # Use new parser and convert to legacy list format
        error_continuation = ReActParser.get_error_continuation(error_message)
        return [error_continuation, "Thought:"]
    
    def convert_action_to_tool_call(self, action: str, action_input: str) -> Dict[str, Any]:
        """
        Convert ReAct Action/Action Input to MCP tool call format.
        
        EP-0014: Thin wrapper around type-safe ReActParser for backward compatibility.
        """
        # Use new parser and convert ToolCall to legacy dict format
        tool_call = ReActParser._convert_to_tool_call(action, action_input)
        
        return {
            'server': tool_call.server,
            'tool': tool_call.tool,
            'parameters': tool_call.parameters,
            'reason': tool_call.reason
        }

    def format_observation(self, mcp_data: Dict[str, Any]) -> str:
        """
        Format MCP data as observation text for ReAct.
        
        EP-0014: Thin wrapper around type-safe ReActParser for backward compatibility.
        """
        # Use new parser directly
        return ReActParser.format_observation(mcp_data)