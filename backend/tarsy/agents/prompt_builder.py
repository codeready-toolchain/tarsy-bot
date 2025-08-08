"""
Prompt builder for constructing LLM prompts used in agent analysis.

This module centralizes all prompt template logic, making it easier to maintain
and modify prompts without touching business logic in agents.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PromptContext:
    """Context data needed for prompt building."""
    agent_name: str
    alert_data: Dict[str, Any]
    runbook_content: str
    mcp_data: Dict[str, Any]
    mcp_servers: List[str]
    server_guidance: str = ""
    agent_specific_guidance: str = ""
    available_tools: Optional[Dict] = None
    iteration_history: Optional[List[Dict]] = None
    current_iteration: Optional[int] = None
    max_iterations: Optional[int] = None

class PromptBuilder:
    """
    Centralized prompt builder for all agent operations.
    
    This class handles the construction of all prompts used by agents,
    separating template logic from business logic in agents.
    
    This class is stateless and designed to be shared across agent instances.
    """
    
    def __init__(self):
        """Initialize the prompt builder."""
        pass
    
    def build_analysis_prompt(self, context: PromptContext) -> str:
        """
        Build comprehensive analysis prompt for alert analysis.
        
        Args:
            context: Prompt context containing all necessary data
            
        Returns:
            Formatted analysis prompt
        """
        prompt_parts = [
            self._build_context_section(context),
            self._build_alert_section(context.alert_data),
            self._build_runbook_section(context.runbook_content),
            self._build_mcp_data_section(context.mcp_data),
            self._build_agent_specific_analysis_guidance(context),
            self._build_analysis_instructions()
        ]
        
        return "\n\n".join(prompt_parts)
    
    def build_mcp_tool_selection_prompt(self, context: PromptContext) -> str:
        """
        Build MCP tool selection prompt for initial tool selection.
        
        Args:
            context: Prompt context containing all necessary data
            
        Returns:
            Formatted tool selection prompt
        """
        return f"""# MCP Tool Selection Request

Based on the following alert and runbook, determine which MCP tools should be called to gather additional information.

{context.server_guidance}

## Alert Information
{self._build_alert_section(context.alert_data)}

{self._build_runbook_section(context.runbook_content)}

## Available MCP Tools
{json.dumps(context.available_tools, indent=2)}

## Instructions
Analyze the alert and runbook to determine which MCP tools should be called and with what parameters.
Return a JSON list of tool calls in this format:

```json
[
  {{
    "server": "kubernetes",
    "tool": "get_namespace_status",
    "parameters": {{
      "cluster": "cluster_url_here",
      "namespace": "namespace_name_here"
    }},
    "reason": "Need to check namespace status to understand why it's stuck"
  }}
]
```

Focus on gathering the most relevant information to diagnose the issue described in the alert."""
    
    def build_iterative_mcp_tool_selection_prompt(self, context: PromptContext) -> str:
        """
        Build iterative MCP tool selection prompt for follow-up tool selection.
        
        Args:
            context: Prompt context containing all necessary data
            
        Returns:
            Formatted iterative tool selection prompt
        """
        max_iterations = context.max_iterations or 5
        display_max = max_iterations if context.current_iteration <= max_iterations else context.current_iteration
        
        return f"""# Iterative MCP Tool Selection Request (Iteration {context.current_iteration})

You are analyzing a multi-step runbook. Based on the alert, runbook, and previous iterations, determine if more MCP tools need to be called or if you have sufficient information to complete the analysis.

{context.server_guidance}

## Alert Information
{self._build_alert_section(context.alert_data)}

{self._build_runbook_section(context.runbook_content)}

## Available MCP Tools
{json.dumps(context.available_tools, indent=2)}

## Previous Iterations History
{self._format_iteration_history(context.iteration_history)}

## Instructions
Based on the runbook steps and what has been discovered so far, determine if you need to call more MCP tools or if the analysis can be completed.

**IMPORTANT**: You are currently on iteration {context.current_iteration} of {display_max} maximum iterations. Be judicious about continuing - only continue if you genuinely need critical missing information that prevents completing the analysis.

Return a JSON object in this format:

If more tools are needed:
```json
{{
  "continue": true,
  "reasoning": "Specific explanation of what critical information is missing and why it's needed to complete the runbook steps",
  "tools": [
    {{
      "server": "kubernetes",
      "tool": "tool_name",
      "parameters": {{
        "param1": "value1"
      }},
      "reason": "Why this specific tool call is needed"
    }}
  ]
}}
```

If analysis can be completed:
```json
{{
  "continue": false,  
  "reasoning": "Explanation of what sufficient information has been gathered and why analysis can now be completed"
}}
```

**Default to stopping if you have reasonable data to work with.** The analysis doesn't need to be perfect - it needs to be actionable based on the runbook steps."""
    

    
    def _build_context_section(self, context: PromptContext) -> str:
        """Build the context section of the prompt."""
        server_list = ", ".join(context.mcp_servers)
        
        return f"""# SRE Alert Analysis Request

You are an expert Site Reliability Engineer (SRE) analyzing a system alert using the {context.agent_name}.
This agent specializes in {server_list} operations and has access to domain-specific tools and knowledge.

Your task is to provide a comprehensive analysis of the incident based on:
1. The alert information
2. The associated runbook
3. Real-time system data from MCP servers

Please provide detailed, actionable insights about what's happening and potential next steps."""
    
    def _build_alert_section(self, alert_data: Dict) -> str:
        """
        Build the alert section of the prompt with flexible data support.
        
        Uses LLM-First Processing approach: displays all alert data as key-value pairs
        for intelligent interpretation by the LLM, rather than hardcoding field expectations.
        """
        if not alert_data:
            return "## Alert Details\n\nNo alert data provided."
        
        alert_text = "## Alert Details\n\n"
        
        # Process all alert data dynamically - LLM-First Processing
        for key, value in alert_data.items():
            # Format the key as human-readable
            formatted_key = key.replace('_', ' ').title()
            
            # Handle different value types intelligently
            if isinstance(value, dict):
                # Nested object - format as JSON for LLM interpretation
                formatted_value = f"\n```json\n{json.dumps(value, indent=2)}\n```"
            elif isinstance(value, list):
                # Array - format as JSON for LLM interpretation
                formatted_value = f"\n```json\n{json.dumps(value, indent=2)}\n```"
            elif isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                # Potential JSON string - try to format it
                try:
                    parsed_json = json.loads(value)
                    formatted_value = f"\n```json\n{json.dumps(parsed_json, indent=2)}\n```"
                except json.JSONDecodeError:
                    # Not valid JSON, treat as regular string
                    formatted_value = str(value)
            elif isinstance(value, str) and '\n' in value:
                # Multi-line string (like YAML) - preserve formatting
                formatted_value = f"\n```\n{value}\n```"
            else:
                # Simple value - display as-is
                formatted_value = str(value) if value is not None else "N/A"
            
            alert_text += f"**{formatted_key}:** {formatted_value}\n"
        
        return alert_text.strip()
    
    def _build_runbook_section(self, runbook_content: str) -> str:
        """Build the runbook section of the prompt."""
        return f"""## Runbook Content
```markdown
<!-- RUNBOOK START -->
{runbook_content if runbook_content else 'No runbook available'}
<!-- RUNBOOK END -->
```"""
    
    def _build_mcp_data_section(self, mcp_data: Dict) -> str:
        """Build the MCP data section of the prompt."""
        if not mcp_data:
            return "## System Data (MCP Servers)\n\nNo system data available from MCP servers."
        
        mcp_text = "## System Data (MCP Servers)\n\n"
        
        for server_name, server_data in mcp_data.items():
            mcp_text += f"### {server_name.title()} MCP Server Data\n\n"
            
            if isinstance(server_data, list):
                # Handle list of tool results
                for i, item in enumerate(server_data):
                    tool_name = item.get('tool', f'result_{i+1}')
                    if 'result' in item:
                        mcp_text += f"**{tool_name}_result:**\n```\n{self._format_data(item['result'])}\n```\n\n"
                    elif 'error' in item:
                        mcp_text += f"**{tool_name}_error:** {item['error']}\n\n"
                    else:
                        mcp_text += f"**{tool_name}:**\n```\n{self._format_data(item)}\n```\n\n"
            elif isinstance(server_data, dict):
                # Handle legacy dict format (for backward compatibility)
                for key, value in server_data.items():
                    mcp_text += f"**{key}:**\n```\n{self._format_data(value)}\n```\n\n"
            else:
                # Handle other data types
                mcp_text += f"```\n{self._format_data(server_data)}\n```\n\n"
        
        return mcp_text.strip()
    
    def _build_agent_specific_analysis_guidance(self, context: PromptContext) -> str:
        """Build agent-specific analysis guidance."""
        guidance_parts = []
        
        # Add server-specific guidance if available
        if context.server_guidance:
            guidance_parts.append("## Domain-Specific Analysis Guidance")
            guidance_parts.append(context.server_guidance)
        
        # Add custom agent guidance if available
        if context.agent_specific_guidance:
            guidance_parts.append("### Agent-Specific Guidance")
            guidance_parts.append(context.agent_specific_guidance)
        
        return "\n\n".join(guidance_parts) if guidance_parts else ""
    
    def _build_analysis_instructions(self) -> str:
        """Build the analysis instructions section."""
        return """## Analysis Instructions

Please provide your analysis in the following structured format:

# 🚨 1. QUICK SUMMARY
**Provide a brief, concrete summary (2-3 sentences maximum):**
- What specific resource is affected (include **name**, **type**, **namespace** if applicable)
- What exactly is wrong with it
- Root cause in simple terms

---

# ⚡ 2. RECOMMENDED ACTIONS

## 🔧 Immediate Fix Actions (if any):
**List specific commands that could potentially resolve the issue, in order of priority:**
- Command 1. Explanation of what this does
```command
command here
```
- Command 2. Explanation of what this does
```command
command here
```

## 🔍 Investigation Actions (if needed):
**List commands for further investigation:**
- Command 1. What information this will provide
```command
command here
```
- Command 2. What information this will provide
```command
command here
```

---

## 3. DETAILED ANALYSIS

### Root Cause Analysis:
- What is the primary cause of this alert?
- What evidence from the system data supports this conclusion?
- Technical details and context

### Current System State:
- Detailed state of affected systems and resources
- Any blocked processes or dependencies preventing resolution
- Related system dependencies and interactions

### Impact Assessment:
- Current impact on system functionality
- Potential escalation scenarios
- Affected services or users

### Prevention Measures:
- How can this issue be prevented in the future?
- Monitoring improvements needed
- Process or automation recommendations

### Additional Context:
- Related systems that should be monitored
- Historical patterns or similar incidents
- Any other relevant technical details

Please be specific and reference the actual data provided. Use exact resource names, namespaces, and status information from the system data."""
    
    def _format_data(self, data) -> str:
        """Format data for display in prompt."""
        if isinstance(data, (dict, list)):
            try:
                return json.dumps(data, indent=2, default=str)
            except:
                return str(data)
        return str(data)
    
    def _format_available_tools(self, available_tools: Dict) -> str:
        """Format available tools for display in prompts."""
        if not available_tools:
            return "No tools available."
        return json.dumps(available_tools, indent=2)
    
    def _format_iteration_history(self, iteration_history: List[Dict]) -> str:
        """Format iteration history for display in prompts."""
        if not iteration_history:
            return "No previous iterations."
        
        TOOL_RESULT_TRUNCATION_THRESHOLD = 3000  # Characters before truncating
        
        history_text = ""
        for i, iteration in enumerate(iteration_history, 1):
            history_text += f"### Iteration {i}\n"
            
            # Tools called
            if "tools_called" in iteration and iteration["tools_called"]:
                history_text += "**Tools Called:**\n"
                for tool in iteration["tools_called"]:
                    history_text += f"- {tool.get('server', 'unknown')}.{tool.get('tool', 'unknown')}: {tool.get('reason', 'No reason provided')}\n"
                history_text += "\n"
            
            # Results with actual data content
            if "mcp_data" in iteration and iteration["mcp_data"]:
                history_text += "**Results:**\n"
                for server_name, server_data in iteration["mcp_data"].items():
                    data_count = len(server_data) if isinstance(server_data, list) else 1
                    history_text += f"- **{server_name}**: {data_count} data points collected\n"
                    
                    # Handle both list format (new) and dict format (legacy)
                    if isinstance(server_data, list):
                        # New format: list of results with metadata
                        for item in server_data:
                            tool_name = item.get('tool', 'unknown_tool')
                            params = item.get('parameters', {})
                            
                            # Create a descriptive key for the result
                            if tool_name == 'resources_list' and 'kind' in params or tool_name == 'resources_get' and 'kind' in params:
                                result_key = f"{tool_name}_{params['kind']}_result"
                            else:
                                result_key = f"{tool_name}_result"
                            
                            # Handle both result and error cases
                            if 'result' in item:
                                result = item['result']
                                if result:  # Only show non-empty results
                                    formatted_data = self._format_data({"result": result})
                                    if len(formatted_data) > TOOL_RESULT_TRUNCATION_THRESHOLD:
                                        formatted_data = formatted_data[:TOOL_RESULT_TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                                    history_text += f"  - **{result_key}**:\n```\n{formatted_data}\n```\n"
                            elif 'error' in item:
                                history_text += f"  - **{result_key}_error**: {item['error']}\n"
                    elif isinstance(server_data, dict):
                        # Legacy format: dict with keys like "tool_name_result"
                        for key, value in server_data.items():
                            formatted_data = self._format_data(value)
                            if len(formatted_data) > TOOL_RESULT_TRUNCATION_THRESHOLD:
                                formatted_data = formatted_data[:TOOL_RESULT_TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                            history_text += f"  - **{key}**:\n```\n{formatted_data}\n```\n"
                    else:
                        formatted_data = self._format_data(server_data)
                        if len(formatted_data) > TOOL_RESULT_TRUNCATION_THRESHOLD:
                            formatted_data = formatted_data[:TOOL_RESULT_TRUNCATION_THRESHOLD] + "\n... [truncated for brevity]"
                        history_text += f"```\n{formatted_data}\n```\n"
                history_text += "\n"
            
            # Partial analysis
            if "partial_analysis" in iteration:
                history_text += f"**Partial Analysis:**\n{iteration['partial_analysis']}\n\n"
            
            history_text += "---\n\n"
        
        return history_text.strip()


    def get_general_instructions(self) -> str:
        """
        Get general SRE instructions common to all agents.
        
        Returns:
            General instruction text for system messages
        """
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

    def get_mcp_tool_selection_system_message(self) -> str:
        """Get system message for MCP tool selection."""
        return "You are an expert SRE analyzing alerts. Based on the alert, runbook, and available MCP tools, determine which tools should be called to gather the necessary information for diagnosis. Return only a valid JSON array with no additional text."
    
    def get_iterative_mcp_tool_selection_system_message(self) -> str:
        """Get system message for iterative MCP tool selection."""
        return "You are an expert SRE analyzing alerts through multi-step runbooks. Based on the alert, runbook, available MCP tools, and previous iteration results, determine what tools should be called next or if the analysis is complete. Return only a valid JSON object with no additional text."
    

    # ====================================================================
    # Standard ReAct Framework Methods 
    # ====================================================================

    def build_standard_react_prompt(self, context: PromptContext, react_history: List[str] = None) -> str:
        """Build standard ReAct prompt following the established ReAct pattern."""
        
        # Build the ReAct history from previous iterations
        history_text = ""
        if react_history:
            history_text = "\n".join(react_history) + "\n"
        
        available_actions = self._format_available_actions(context.available_tools)
        action_names = self._get_action_names(context.available_tools)
        
        prompt = f"""Answer the following question as best you can. You have access to the following tools:

{available_actions}

MANDATORY FORMAT - Follow this EXACT structure:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{', '.join(action_names)}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

CRITICAL INSTRUCTIONS:
1. ALWAYS use colons after "Thought:", "Action:", and "Action Input:"
2. For Action Input, provide ONLY parameter values (no YAML, no ```code blocks```, no formatting)
3. STOP immediately after your "Action Input:" line
4. NEVER write "Observation:" - the system provides that

EXAMPLE OF CORRECT FORMAT:
Thought: I need to check the namespace status first.
Action: kubernetes-server.resources_get
Action Input: apiVersion=v1, kind=Namespace, name=superman-dev

EXAMPLE OF INCORRECT FORMAT (DO NOT DO THIS):
Thought
I need to check...
Action: kubernetes-server.resources_get
Action Input:
```yaml
apiVersion: v1
kind: Namespace
name: superman-dev
```
Observation: (fake observation)

RESPONSE OPTIONS:
1. Continue investigating: "Thought: [reasoning] Action: [tool] Action Input: [params]"
2. OR conclude: "Thought: I now know the final answer Final Answer: [analysis]"

Begin!

Question: {self._format_react_question(context)}
{history_text}"""
        
        return prompt

    def _format_available_actions(self, available_tools: Dict) -> str:
        """Format available tools as ReAct actions."""
        if not available_tools or not available_tools.get("tools"):
            return "No tools available."
        
        actions = []
        for tool in available_tools["tools"]:
            action_name = f"{tool.get('server', 'unknown')}.{tool.get('name', tool.get('tool', 'unknown'))}"
            description = tool.get('description', 'No description available')
            
            # Get parameter info from input schema
            parameters = tool.get('input_schema', {}).get('properties', {})
            if parameters:
                param_desc = ', '.join([f"{k}: {v.get('description', 'no description')}" for k, v in parameters.items()])
                actions.append(f"{action_name}: {description}\n  Parameters: {param_desc}")
            else:
                actions.append(f"{action_name}: {description}")
        
        return '\n'.join(actions)

    def _get_action_names(self, available_tools: Dict) -> List[str]:
        """Get list of action names for the ReAct prompt."""
        if not available_tools or not available_tools.get("tools"):
            return ["No tools available"]
        
        return [f"{tool.get('server', 'unknown')}.{tool.get('name', tool.get('tool', 'unknown'))}" 
                for tool in available_tools["tools"]]

    def _format_react_question(self, context: PromptContext) -> str:
        """Format the alert analysis as a ReAct question."""
        alert_type = context.alert_data.get('alert_type', context.alert_data.get('alert', 'Unknown Alert'))
        
        # Create concise question for ReAct
        question = f"""Analyze this {alert_type} alert and provide actionable recommendations.

## Alert Details
{self._build_alert_section(context.alert_data)}

{self._build_runbook_section(context.runbook_content)}

## Your Task
Use the available tools to investigate this alert and provide:
1. Root cause analysis
2. Current system state assessment  
3. Specific remediation steps for human operators
4. Prevention recommendations

Be thorough in your investigation before providing the final answer."""
        
        return question

    # ====================================================================
    # ReAct Response Parsing Methods
    # ====================================================================

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
        """Check if line is a valid section header that hasn't been processed yet."""
        if not line or section_type in found_sections:
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
        return line.startswith('Observation:') or line.startswith('[Based on')

    def _finalize_current_section(self, parsed: Dict[str, Any], current_section: str, content_lines: List[str]) -> None:
        """Safely finalize the current section by joining content lines."""
        if current_section and content_lines is not None:
            parsed[current_section] = '\n'.join(content_lines).strip()

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


# Shared instance since PromptBuilder is stateless
_shared_prompt_builder = PromptBuilder()


def get_prompt_builder() -> PromptBuilder:
    """Get the shared PromptBuilder instance."""
    return _shared_prompt_builder 