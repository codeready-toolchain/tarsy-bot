"""
LangChain-based prompt builder with template composition.

This module implements the new PromptBuilder using LangChain templates
while maintaining backward compatibility with existing APIs.
"""

import json
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from .components import (
    AlertSectionTemplate, 
    RunbookSectionTemplate, 
    ChainContextSectionTemplate
)
from .templates import *

if TYPE_CHECKING:
    from tarsy.models.agent_execution_result import ChainExecutionContext


class PromptBuilder:
    """LangChain-based prompt builder with template composition."""
    
    def __init__(self):
        # Initialize component templates
        self.alert_component = AlertSectionTemplate()
        self.runbook_component = RunbookSectionTemplate()
        self.chain_context_component = ChainContextSectionTemplate()
    
    # ============ Main Prompt Building Methods ============
    
    def build_standard_react_prompt(self, context, react_history: Optional[List[str]] = None) -> str:
        """Build standard ReAct prompt using templates. Used by SimpleReActController."""
        # Build question components
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        chain_context = self.chain_context_component.format(context)
        
        # Build question
        alert_type = context.alert_data.get('alert_type', context.alert_data.get('alert', 'Unknown Alert'))
        question = ANALYSIS_QUESTION_TEMPLATE.format(
            alert_type=alert_type,
            alert_section=alert_section,
            runbook_section=runbook_section,
            chain_context=chain_context
        )
        
        # Build final prompt
        history_text = ""
        if react_history:
            flattened_history = self._flatten_react_history(react_history)
            history_text = "\n".join(flattened_history) + "\n"
        
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(context.available_tools),
            question=question,
            history_text=history_text
        )
    
    def build_stage_analysis_react_prompt(self, context, react_history: Optional[List[str]] = None) -> str:
        """Build ReAct prompt for stage-specific analysis. Used by ReactStageController."""
        # Build question components
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        chain_context = self.chain_context_component.format(context)
        
        # Build question
        alert_type = context.alert_data.get('alert_type', context.alert_data.get('alert', 'Unknown Alert'))
        stage_name = context.stage_name or "analysis"
        question = STAGE_ANALYSIS_QUESTION_TEMPLATE.format(
            alert_type=alert_type,
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
        
        return STANDARD_REACT_PROMPT_TEMPLATE.format(
            available_actions=self._format_available_actions(context.available_tools),
            question=question,
            history_text=history_text
        )
    
    def build_final_analysis_prompt(self, context) -> str:
        """Build prompt for final analysis without ReAct format. Used by ReactFinalAnalysisController."""
        stage_info = ""
        if context.stage_name:
            stage_info = f"\n**Stage:** {context.stage_name}"
            if context.is_final_stage:
                stage_info += " (Final Analysis Stage)"
            if context.previous_stages:
                stage_info += f"\n**Previous Stages:** {', '.join(context.previous_stages)}"
            stage_info += "\n"
        
        context_section = self._build_context_section(context)
        alert_section = self.alert_component.format(context.alert_data)
        runbook_section = self.runbook_component.format(context.runbook_content)
        chain_context = self.chain_context_component.format(context)
        
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
    
    def _build_context_section(self, context) -> str:
        """Build the context section using template."""
        server_list = ", ".join(context.mcp_servers)
        return CONTEXT_SECTION_TEMPLATE.format(
            agent_name=context.agent_name,
            server_list=server_list
        )
    
    def _build_alert_section(self, alert_data) -> str:
        """Backward compatibility method - delegates to alert component."""
        return self.alert_component.format(alert_data)
    
    def _build_runbook_section(self, runbook_content) -> str:
        """Backward compatibility method - delegates to runbook component."""
        return self.runbook_component.format(runbook_content)
        
    def _build_chain_context_section(self, context) -> str:
        """Backward compatibility method - delegates to chain context component."""
        return self.chain_context_component.format(context)
    
    def _format_available_actions(self, available_tools: Dict) -> str:
        """Format available tools as ReAct actions."""
        if not available_tools or not available_tools.get("tools"):
            return "No tools available."
        
        actions = []
        for tool in available_tools["tools"]:
            action_name = f"{tool.get('server', 'unknown')}.{tool.get('name', tool.get('tool', 'unknown'))}"
            description = tool.get('description', 'No description available')
            
            parameters = tool.get('input_schema', {}).get('properties', {})
            if parameters:
                param_desc = ', '.join([f"{k}: {v.get('description', 'no description')}" for k, v in parameters.items()])
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

    # ============ ReAct Response Parsing (Keep Current Logic) ============
    
    def _extract_section_content(self, line: str, prefix: str) -> str:
        """Safely extract content from a line with given prefix, with defensive checks."""
        if not line or not prefix:
            return ""
        
        # Ensure the line is long enough to contain the prefix plus potential content
        if len(line) < len(prefix):
            return ""
        
        # Safely extract content after prefix
        if len(line) > len(prefix):
            return line[len(prefix):].strip()
        
        return ""

    def _is_section_header(self, line: str, section_type: str, found_sections: set) -> bool:
        """Check if line is a valid section header."""
        if not line:
            return False
        
        # For ReAct parsing, allow duplicate actions and thoughts (use latest occurrence)
        # But prevent duplicate final_answer (first one wins)
        if section_type == 'final_answer' and section_type in found_sections:
            return False
            
        if section_type == 'thought':
            return line.startswith('Thought:') or line == 'Thought'
        elif section_type == 'action':
            return line.startswith('Action:')
        elif section_type == 'action_input':
            return line.startswith('Action Input:')
        elif section_type == 'final_answer':
            return line.startswith('Final Answer:')
        
        return False

    def _should_stop_parsing(self, line: str) -> bool:
        """Check if we should stop parsing due to fake content markers."""
        if not line:
            return False
        
        # Stop parsing on fake/hallucinated observations that LLM generates
        # But NOT on legitimate continuation prompts that are part of the conversation
        if line.startswith('[Based on'):
            return True
        
        # Only stop on observations that look like hallucinated tool results
        # Continuation prompts like "Please specify what Action..." should not stop parsing
        if line.startswith('Observation:'):
            # Don't stop if this looks like a continuation prompt
            if 'Please specify' in line or 'what Action you want to take' in line:
                return False
            # Don't stop if this looks like an error continuation 
            if 'Error in reasoning' in line:
                return False
            # This appears to be a real/hallucinated observation - stop parsing
            return True
            
        return False

    def _finalize_current_section(self, parsed: Dict[str, Any], current_section: str, content_lines: List[str]) -> None:
        """Safely finalize the current section by joining content lines."""
        if current_section and content_lines is not None:
            new_content = '\n'.join(content_lines).strip()
            # Only overwrite existing content if new content is not empty
            # This handles cases where duplicate sections have empty content
            if new_content or parsed.get(current_section) is None:
                parsed[current_section] = new_content
    
    def parse_react_response(self, response: str) -> Dict[str, Any]:
        """Parse structured ReAct response into components with robust error handling."""
        # Input validation
        if not response or not isinstance(response, str):
            return {
                'thought': None,
                'action': None,
                'action_input': None,
                'final_answer': None,
                'is_complete': False
            }

        lines = response.strip().split('\n')
        parsed = {
            'thought': None,
            'action': None,
            'action_input': None,
            'final_answer': None,
            'is_complete': False
        }
        
        current_section = None
        content_lines = []  # Always initialize as empty list
        found_sections = set()
        
        try:
            for line in lines:
                # Safely strip line, handle None/empty cases
                line = line.strip() if line else ""
                
                # Skip empty lines when not in a section
                if not line and not current_section:
                    continue
                
                # Check for stop conditions first
                if self._should_stop_parsing(line):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    break
                
                # Handle Final Answer (can appear at any time)
                if self._is_section_header(line, 'final_answer', set()):  # Always allow final_answer
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'final_answer'
                    found_sections.add('final_answer')
                    content_lines = [self._extract_section_content(line, 'Final Answer:')]
                    parsed['is_complete'] = True
                    
                # Handle Thought section  
                elif self._is_section_header(line, 'thought', found_sections):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'thought'
                    found_sections.add('thought')
                    if line.startswith('Thought:'):
                        content_lines = [self._extract_section_content(line, 'Thought:')]
                    else:
                        content_lines = []  # 'Thought' without colon, content on next lines
                    
                # Handle Action section
                elif self._is_section_header(line, 'action', found_sections):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'action'
                    found_sections.add('action')
                    # Clear action_input from found_sections to allow new action_input after new action
                    found_sections.discard('action_input')
                    content_lines = [self._extract_section_content(line, 'Action:')]
                    
                # Handle Action Input section
                elif self._is_section_header(line, 'action_input', found_sections):
                    self._finalize_current_section(parsed, current_section, content_lines)
                    current_section = 'action_input'
                    found_sections.add('action_input')
                    content_lines = [self._extract_section_content(line, 'Action Input:')]
                    
                else:
                    # Only add content if we're in a valid section
                    if current_section and content_lines is not None:
                        content_lines.append(line)
            
            # Handle last section
            self._finalize_current_section(parsed, current_section, content_lines)
            
        except Exception as e:
            # Log the error if needed, but return a safe default structure
            # In a production environment, you might want to add logging here
            pass
        
        return parsed
    
    def get_react_continuation_prompt(self, context_type: str = "general") -> List[str]:
        """Get ReAct continuation prompts for when LLM provides incomplete responses."""
        prompts = {
            "general": "Observation: Choose ONE option: (1) Continue investigating with 'Thought: [reasoning] Action: [tool] Action Input: [params]' then STOP (do NOT generate fake observations) OR (2) Conclude with 'Thought: I have sufficient information Final Answer: [your analysis]'",
            "data_collection": "Observation: Choose ONE option: (1) Continue data collection with 'Thought: [reasoning] Action: [tool] Action Input: [params]' then STOP (do NOT generate fake observations) OR (2) Conclude with 'Thought: I have sufficient data Final Answer: [data summary]'",
            "analysis": "Observation: Choose ONE option: (1) Continue investigating with 'Thought: [reasoning] Action: [tool] Action Input: [params]' then STOP (do NOT generate fake observations) OR (2) Conclude with 'Thought: I have sufficient information Final Answer: [complete analysis]'"
        }
        
        continuation_message = prompts.get(context_type, prompts["general"])
        return [continuation_message, "Thought:"]
    
    def get_react_error_continuation(self, error_message: str) -> List[str]:
        """Get ReAct continuation prompts for error recovery."""
        return [
            f"Observation: Error in reasoning: {error_message}. Please try a different approach.",
            "Thought:"
        ]
    
    def convert_action_to_tool_call(self, action: str, action_input: str) -> Dict[str, Any]:
        """Convert ReAct Action/Action Input to MCP tool call format."""
        if not action:
            raise ValueError("Action cannot be empty")
        
        if '.' not in action:
            raise ValueError(f"Action must be in format 'server.tool', got: {action}")
        
        server, tool = action.split('.', 1)
        
        # Parse action input (could be JSON, YAML-like, or simple parameters)
        parameters = {}
        action_input = action_input.strip()
        
        try:
            # Try JSON first
            if action_input.startswith('{'):
                parameters = json.loads(action_input)
            else:
                # Handle YAML-like format: "apiVersion: v1, kind: Namespace, name: superman-dev"
                # or key=value format
                for part in action_input.split(','):
                    part = part.strip()
                    if ':' in part and '=' not in part:
                        # YAML-like format (key: value)
                        key, value = part.split(':', 1)
                        parameters[key.strip()] = value.strip()
                    elif '=' in part:
                        # key=value format
                        key, value = part.split('=', 1)
                        parameters[key.strip()] = value.strip()
                    else:
                        # Single parameter without format
                        if not parameters:  # Only if we haven't added anything yet
                            parameters['input'] = action_input
                            break
                        
                # If no structured format detected, treat as single input
                if not parameters:
                    parameters['input'] = action_input
                        
        except json.JSONDecodeError:
            # Fallback: try to parse as key: value or key=value
            for part in action_input.split(','):
                part = part.strip()
                if ':' in part:
                    key, value = part.split(':', 1)
                    parameters[key.strip()] = value.strip()
                elif '=' in part:
                    key, value = part.split('=', 1)
                    parameters[key.strip()] = value.strip()
            
            # Ultimate fallback
            if not parameters:
                parameters['input'] = action_input
        except Exception:
            # Ultimate fallback
            parameters['input'] = action_input
        
        return {
            'server': server,
            'tool': tool,
            'parameters': parameters,
            'reason': f'ReAct Action: {action}'
        }

    def format_observation(self, mcp_data: Dict[str, Any]) -> str:
        """Format MCP data as observation text for ReAct."""
        if not mcp_data:
            return "No data returned from the action."
        
        observations = []
        for server, results in mcp_data.items():
            if isinstance(results, list):
                for result in results:
                    if 'result' in result and result['result']:
                        # Format the result nicely
                        if isinstance(result['result'], dict):
                            formatted_result = json.dumps(result['result'], indent=2)
                        else:
                            formatted_result = str(result['result'])
                        observations.append(f"{server}.{result.get('tool', 'unknown')}: {formatted_result}")
                    elif 'error' in result:
                        observations.append(f"{server}.{result.get('tool', 'unknown')} error: {result['error']}")
            else:
                # Legacy format
                observations.append(f"{server}: {json.dumps(results, indent=2)}")
        
        return '\n'.join(observations) if observations else "Action completed but no specific data returned."
